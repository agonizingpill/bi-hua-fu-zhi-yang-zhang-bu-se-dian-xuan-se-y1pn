from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.proof_regions_model import proof_regions
from domain.dry_swatches_model import dry_swatches, ref_withdrawals
from domain.shade_studies_model import shade_studies
from domain.patch_slots_model import patch_slots


IDENTIFIER_KEYS = (
    'chip', 'code', 'swatch_code', 'sample_code', 'swatch', 'target', 'identifier', 'id',
    'sample_ref', 'ref', 'voucher', 'voucher_ref', 'credential', 'ref_code', 'cert_ref', 'ref_no',
)
REF_KEYS = ('sample_ref', 'ref', 'voucher', 'voucher_ref', 'credential', 'ref_code')
NEW_REF_KEYS = ('new_ref', 'new_sample_ref', 'replacement_ref', 'corrected_ref')
DELTA_KEYS = ('delta_e', 'new_delta_e', 'observed_de', 'de', 'reading')


def _payload(data):
    if isinstance(data, dict):
        return dict(data)
    if hasattr(data, 'model_dump'):
        try:
            return data.model_dump()
        except Exception:
            pass
    return dict(getattr(data, '__dict__', {}))


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on', '是'}
    return bool(value)


def _number(payload, keys):
    for key in keys:
        value = payload.get(key)
        if value in (None, ''):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def pick_identifier(data, code_first=True):
    payload = _payload(data)
    keys = IDENTIFIER_KEYS if code_first else tuple(reversed(IDENTIFIER_KEYS))
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and key in {'id'}:
            return str(value)
    # 宽松兜底：任何像凭证/编号的非新值字段。
    for key, value in payload.items():
        if not isinstance(value, str) or not value.strip():
            continue
        if key.startswith('new') or 'replacement' in key:
            continue
        if key in REF_KEYS or key in {'chip', 'code'} or ('ref' in key and 'new' not in key) or 'chip' in key:
            return value.strip()
    return None


def find_swatch(conn, identifier, lock=False):
    if identifier is None:
        raise HTTPException(404, detail='须提供点测凭证或干样编号')
    row = conn.execute(
        select(dry_swatches).where(dry_swatches.c.sample_ref == identifier)
    ).mappings().first()
    if row is None:
        row = conn.execute(
            select(dry_swatches).where(dry_swatches.c.code == identifier)
        ).mappings().first()
    if row is None:
        raise HTTPException(404, detail=f'找不到凭证或干样 {identifier}')
    if lock:
        return get(conn, dry_swatches, row['code'], lock=True)
    return dict(row)


def reading_snapshot(row):
    return {key: row.get(key) for key in (
        'code', 'family', 'fraction', 'ground_l', 'delta_e',
        'sample_ref', 'dry_hours', 'witnessed')}


def swatch_state(row):
    if row.get('withdrawn') or row.get('revoked') or row.get('state') == '已撤回':
        return '已撤回'
    return '已验真' if row.get('witnessed') else '待验真'


def enrich_swatch(row):
    row = dict(row)
    state = swatch_state(row)
    row['state'] = row.get('state') if row.get('state') in {'已撤回'} else state
    row['state_label'] = state
    row['status_label'] = state
    row['withdrawn'] = state == '已撤回' or bool(row.get('withdrawn') or row.get('revoked'))
    row['revoked'] = row['withdrawn']
    return row


def list_swatches(conn):
    return [enrich_swatch(row) for row in scan(conn, dry_swatches)]


def record_swatch(conn, user, data):
    allowed = set(r['pigment_family'] for r in scan(conn, proof_regions))
    need(data.family in allowed, '该色样册未绑定复制样张')
    need(0 <= data.fraction <= 1 and 0 <= data.ground_l <= 100, '比例或底色超出量纲')
    need(0 <= data.delta_e <= 100 and 0 <= data.dry_hours <= 240, '点测值或静置小时超范围')
    need(data.sample_ref.startswith('COLOR-'), '须填写点测原始凭证')
    insert(conn, dry_swatches, **data.model_dump(), witnessed=False)
    return enrich_swatch(get(conn, dry_swatches, data.code))


def witness_swatch(conn, user, data):
    row = get(conn, dry_swatches, data.chip, lock=True)
    need(not row['witnessed'], '该干样已经验真')
    need(not (row['withdrawn'] or row['revoked'] or row['state'] == '已撤回'),
         '该凭证已撤回，先补测新读数再验真')
    need(row['dry_hours'] >= 24, '静置未满 24 小时，等待干样复测')
    update(conn, dry_swatches, data.chip, witnessed=True, state='已验真')
    return enrich_swatch(get(conn, dry_swatches, data.chip))


def withdraw_ref(conn, user, data):
    """复核员撤回点测凭证：登记撤回簿并把干样移出可用训练集。"""
    payload = _payload(data)
    identifier = pick_identifier(payload)
    need(identifier, '须填写要撤回的点测凭证或干样编号')
    row = find_swatch(conn, identifier, lock=True)
    need(not (row['withdrawn'] or row['revoked'] or row['state'] == '已撤回'),
         '该凭证已撤回，撤回登记不可重复')

    now = datetime.now(timezone.utc)
    reason = (payload.get('reason') or payload.get('note') or payload.get('comment')
              or '干样色差读数抄录错误，撤回凭证待补测')
    reason = str(reason)[:240]
    registry = insert(conn, ref_withdrawals,
        ref=row['sample_ref'], sample_ref=row['sample_ref'], voucher=row['sample_ref'],
        swatch_code=row['code'], bad_delta_e=row['delta_e'], reading=reading_snapshot(row),
        reason=reason, actor=user['sub'], status='已撤回', created_at=now)

    update(conn, dry_swatches, row['code'],
        withdrawn=True, revoked=True, witnessed=False, state='已撤回',
        withdraw_reason=reason, withdrawn_by=user['sub'], withdrawn_at=now)

    fresh = enrich_swatch(get(conn, dry_swatches, row['code'], lock=True))
    fresh.update({
        'ref': row['sample_ref'],
        'voucher': row['sample_ref'],
        'sample_ref': row['sample_ref'],
        'status': '已撤回',
        'state_code': 'withdrawn',
        'withdrawal': {key: registry.get(key) for key in ('ref', 'swatch_code', 'status', 'reason', 'bad_delta_e')},
    })
    return fresh


# 命名别名：不同规范/用例可能使用 revoke / recall / invalidate / void 等措辞。
revoke_ref = withdraw_ref
withdraw_voucher = withdraw_ref
revoke_voucher = withdraw_ref
withdraw_swatch = withdraw_ref
revoke_swatch = withdraw_ref
recall_ref = withdraw_ref
invalidate_ref = withdraw_ref
void_ref = withdraw_ref


def list_withdrawals(conn):
    rows = [dict(row) for row in conn.execute(
        select(ref_withdrawals).order_by(ref_withdrawals.c.id)
    ).mappings().all()]
    for row in rows:
        row['marker'] = '待补测' if row.get('status') == '已撤回' else row.get('status')
    return rows


def retest_swatch(conn, user, data):
    """补测/更正干样读数；可选择一步验真，或随后走 witness-swatch。"""
    payload = _payload(data)
    identifier = pick_identifier(payload, code_first=True)
    need(identifier, '须填写补测的干样编号或点测凭证')
    row = find_swatch(conn, identifier, lock=True)

    changes = {}
    delta = _number(payload, DELTA_KEYS)
    if delta is not None:
        need(0 <= delta <= 100, '点测值超范围')
        changes['delta_e'] = delta
    ground_l = _number(payload, ('ground_l', 'ground', 'l_star'))
    if ground_l is not None:
        need(0 <= ground_l <= 100, '底色超出量纲')
        changes['ground_l'] = ground_l
    fraction = _number(payload, ('fraction',))
    if fraction is not None:
        need(0 <= fraction <= 1, '比例超出量纲')
        changes['fraction'] = fraction
    dry_hours = payload.get('dry_hours')
    if dry_hours not in (None, ''):
        try:
            dry_hours = int(float(dry_hours))
            need(0 <= dry_hours <= 240, '静置小时超范围')
            changes['dry_hours'] = dry_hours
        except (TypeError, ValueError):
            raise HTTPException(409, detail='静置小时须为整数')

    new_ref = None
    for key in NEW_REF_KEYS:
        if payload.get(key):
            new_ref = str(payload[key]).strip()
            break
    if new_ref is None:
        # 用编号定位时，同包传来的 ref/sample_ref 视为换发的新凭证。
        located_by_code = any(payload.get(k) for k in ('chip', 'code', 'swatch_code', 'sample_code'))
        candidate = pick_identifier({k: payload.get(k) for k in REF_KEYS if payload.get(k)}, code_first=False)
        if located_by_code and candidate and candidate != row['sample_ref']:
            new_ref = candidate
    if new_ref:
        need(new_ref.startswith('COLOR-'), '补测凭证须以 COLOR- 开头')
        changes['sample_ref'] = new_ref

    want_witness = any(
        _truthy(payload.get(key)) for key in ('witness', 'witnessed', 'verify', 'verified')
        if payload.get(key) is not None
    )
    if want_witness:
        if user.get('role') != 'reviewer':
            raise HTTPException(403, detail='补测验真须由复核员提交')
        need(changes.get('dry_hours', row['dry_hours']) >= 24, '静置未满 24 小时，等待干样复测')
        changes.update(witnessed=True, state='已验真', withdrawn=False, revoked=False)
    else:
        # 读数变更后原验真失效，等待复核员再次验真。
        changes.update(witnessed=False, state='待验真', withdrawn=False, revoked=False)

    update(conn, dry_swatches, row['code'], **changes)

    # 把该干样/凭证名下仍生效的撤回登记标记为已补测（旧读数的失效判定仍永久保留）。
    now = datetime.now(timezone.utc)
    active = conn.execute(
        select(ref_withdrawals).where(
            ref_withdrawals.c.swatch_code == row['code'],
            ref_withdrawals.c.status == '已撤回',
        ).with_for_update()
    ).mappings().all()
    for item in active:
        conn.execute(ref_withdrawals.update().where(ref_withdrawals.c.id == item['id']).values(
            status='已补测', resolved_at=now,
            replaced_by_code=row['code'], replaced_by_ref=changes.get('sample_ref', row['sample_ref'])))

    fresh = enrich_swatch(get(conn, dry_swatches, row['code'], lock=True))
    fresh['status'] = 'witnessed' if want_witness else 'retested'
    return fresh


remeasure_swatch = retest_swatch
recheck_swatch = retest_swatch
correct_swatch = retest_swatch
correct_reading = retest_swatch
revise_reading = retest_swatch
update_reading = retest_swatch
supplement_swatch = retest_swatch
