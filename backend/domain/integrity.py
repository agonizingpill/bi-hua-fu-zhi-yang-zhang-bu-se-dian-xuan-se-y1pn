"""凭证撤回与预测有效性判定。

一条拟合任务的 input['studies'] 是排队时快照的干样行；训练集与留出验证集合起来
恰好是全部入模行（见 domain.learning.calculate 的等分划分），所以只要快照中任一
干样的点测凭证被撤回，无论它落在训练折还是留出折，预测都失效。

判定同时兼容两种补测方式：
1. 旧凭证永久撤回，补测登记新干样/新凭证 —— 新快照不含旧凭证，自然放行；
2. 同一干样改录新读数 —— 旧预测快照里的旧 ΔE 与撤回登记簿/当前读数对不上新值，
   仍判失效；用新读数重新拟合出的新快照与当前读数一致，放行。
"""
from math import isclose

from sqlalchemy import or_, select

from core.records import need
from domain.dry_swatches_model import dry_swatches, ref_withdrawals

REF_KEYS = ('sample_ref', 'ref', 'voucher_ref', 'voucher', 'credential', 'ref_code', 'cert_ref')
CODE_KEYS = ('code', 'chip', 'swatch_code', 'sample_code', 'swatch')
DELTA_KEYS = ('delta_e', 'new_delta_e', 'observed_de', 'de', 'reading')

WITHDRAWN_STATES = {'已撤回', 'withdrawn', 'revoked', 'void'}
ACTIVE_WITHDRAW = {'已撤回', 'withdrawn', 'revoked', 'void', 'active'}


def first_value(row, keys):
    if not isinstance(row, dict):
        return None
    for key in keys:
        value = row.get(key)
        if value not in (None, ''):
            return value
    return None


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def study_ref(study):
    value = first_value(study, REF_KEYS)
    return str(value) if value is not None else None


def study_code(study):
    value = first_value(study, CODE_KEYS)
    return str(value) if value is not None else None


def study_delta(study):
    return as_float(first_value(study, DELTA_KEYS))


def collect_refs(studies):
    refs, codes = set(), set()
    for study in studies or []:
        ref, code = study_ref(study), study_code(study)
        if ref:
            refs.add(ref)
        if code:
            codes.add(code)
    return refs, codes


def _withdrawal_matches(withdrawal, ref, code):
    if code and withdrawal.get('swatch_code') == code:
        return True
    if not ref:
        return False
    return ref in {withdrawal.get('ref'), withdrawal.get('sample_ref'), withdrawal.get('voucher')}


def taint_studies(conn, studies, lock=False):
    """返回快照中已失效干样的描述列表；空列表表示预测仍可用。

    加锁顺序固定为“先锁 dry_swatches 行（撤回操作也先锁同一行），再普通读登记簿”，
    这样撤回先提交时签认的当前读一定看到撤回标记；签认先锁住干样行时撤回只能等待，
    不会形成 InnoDB 间隙锁与行锁的循环等待。
    """
    studies = [study for study in (studies or []) if isinstance(study, dict)]
    if not studies:
        return []
    refs, codes = collect_refs(studies)

    # 1) 先取干样行（锁路径上的串行点）。
    swatch_rows = []
    if codes:
        query = select(dry_swatches).where(dry_swatches.c.code.in_(sorted(codes)))
        if lock:
            query = query.with_for_update()
        swatch_rows.extend(dict(row) for row in conn.execute(query).mappings().all())
    if refs:
        query = select(dry_swatches).where(dry_swatches.c.sample_ref.in_(sorted(refs)))
        if lock:
            query = query.with_for_update()
        known_codes = {row['code'] for row in swatch_rows}
        for row in conn.execute(query).mappings().all():
            if row['code'] not in known_codes:
                swatch_rows.append(dict(row))
    by_code = {row['code']: row for row in swatch_rows}
    by_ref = {row['sample_ref']: row for row in swatch_rows}

    # 2) 登记簿用普通一致读（此时才建立读视图，能看到已提交的撤回登记）。
    withdrawals = []
    conditions = []
    if refs:
        conditions += [
            ref_withdrawals.c.ref.in_(refs),
            ref_withdrawals.c.sample_ref.in_(refs),
            ref_withdrawals.c.voucher.in_(refs),
        ]
    if codes:
        conditions.append(ref_withdrawals.c.swatch_code.in_(codes))
    if conditions:
        query = select(ref_withdrawals).where(or_(*conditions))
        withdrawals = [dict(row) for row in conn.execute(query).mappings().all()]

    tainted = []
    for study in studies:
        ref, code, delta = study_ref(study), study_code(study), study_delta(study)
        swatch = by_code.get(code) if code else None
        if swatch is None and ref:
            swatch = by_ref.get(ref)
        reasons = []

        if swatch is not None and (
            swatch.get('withdrawn') or swatch.get('revoked')
            or swatch.get('state') in WITHDRAWN_STATES
        ):
            reasons.append('该凭证已撤回')

        for withdrawal in withdrawals:
            if not _withdrawal_matches(withdrawal, ref, code):
                continue
            bad = withdrawal.get('bad_delta_e')
            status = withdrawal.get('status') or '已撤回'
            active = status in ACTIVE_WITHDRAW
            if bad is not None and delta is not None:
                if isclose(float(bad), float(delta), rel_tol=1e-9, abs_tol=1e-6):
                    reasons.append('预测使用了撤回登记时的旧读数')
            elif active:
                reasons.append('该凭证已撤回')

        # 补测改了读数后，任何基于旧快照读数的预测都必须重算。
        if swatch is not None and delta is not None and swatch.get('delta_e') is not None:
            if not isclose(float(swatch['delta_e']), delta, rel_tol=1e-9, abs_tol=1e-6):
                reasons.append('干样读数已补测更新，旧预测失效')

        if reasons:
            unique = list(dict.fromkeys(reasons))
            tainted.append({
                'code': code or (swatch or {}).get('code'),
                'ref': ref or (swatch or {}).get('sample_ref'),
                'sample_ref': ref or (swatch or {}).get('sample_ref'),
                'delta_e': delta,
                'reasons': unique,
                'reason': '；'.join(unique),
            })
    return tainted


def freshness_message(tainted):
    labels = []
    for item in tainted:
        label = item.get('ref') or item.get('code') or '未知凭证'
        if item.get('code') and item.get('ref'):
            label = f"{item['ref']}（{item['code']}）"
        if label not in labels:
            labels.append(label)
    joined = '、'.join(labels[:6]) + ('…' if len(labels) > 6 else '')
    return (f'拟合所用点测凭证 {joined} 已撤回，本预测已失效'
            '（训练或留出验证引用了该凭证），该预测在工作台标记为待补测；'
            '请补测验真并用新读数重算（重新计算）后再凭新拟合任务签认。'
            '未使用该凭证的预测不受影响，可照常签认。')


def assert_prediction_fresh(conn, studies, lock=True):
    tainted = taint_studies(conn, studies, lock=lock)
    need(not tainted, freshness_message(tainted))
    return tainted
