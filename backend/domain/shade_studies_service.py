from sqlalchemy import or_, select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.proof_regions_model import proof_regions
from domain.dry_swatches_model import dry_swatches, ref_withdrawals
from domain.shade_studies_model import shade_studies
from domain.patch_slots_model import patch_slots
from domain.integrity import assert_prediction_fresh


# 进入拟合任务/快照的干样字段（只留 JSON 安全标量与模型/追溯所需键）。
STUDY_FIELDS = ('code', 'family', 'fraction', 'ground_l', 'delta_e', 'sample_ref', 'dry_hours', 'witnessed')


def _study_row(row):
    return {key: row.get(key) for key in STUDY_FIELDS}


def fit_at_point(conn, user, data):
    from domain.proof_geometry import demand_point
    panel = get(conn, proof_regions, data.panel)
    demand_point(panel, data.x_mm, data.y_mm)
    rows = [_study_row(row) for row in scan(conn, dry_swatches)
        if row['witnessed']
        and not (row.get('withdrawn') or row.get('revoked') or row.get('state') == '已撤回')
        and row['family'] == panel['pigment_family']]
    need(len(rows) >= 12, '同色样册已验真干样不足 12 条')
    low, high = min(r['ground_l'] for r in rows), max(r['ground_l'] for r in rows)
    need(low <= data.ground_l <= high, '该点底色亮度落在已测干样范围之外')
    return submit(user, {'studies':rows,'panel':data.panel,'revision':panel['revision'],
        'x_mm':data.x_mm,'y_mm':data.y_mm,'ground_l':data.ground_l})


def build_snapshot(inputs, metric):
    readings = [dict(row) for row in inputs.get('studies', [])]
    used_refs = sorted({row.get('sample_ref') for row in readings if row.get('sample_ref')})
    interval = {key: metric.get(key) for key in ('mean_de', 'lower_de', 'upper_de', 'test_mae')}
    interval['width_de'] = round(float(metric['upper_de']) - float(metric['lower_de']), 6)
    evidence = {
        'readings': readings,
        'used_refs': used_refs,
        'refs': used_refs,
        'interval': interval,
        'token': None,
    }
    return readings, used_refs, interval, evidence


def enrich_study(row):
    """给签认簿行补上工作台友好的快照别名与可读摘要。"""
    row = dict(row)
    readings = row.get('readings')
    if not readings and isinstance(row.get('evidence'), dict):
        readings = row['evidence'].get('readings')
    if not readings and row.get('used_readings'):
        readings = row.get('used_readings')
    readings = readings or []

    used_refs = row.get('used_refs')
    if not used_refs:
        used_refs = sorted({item.get('sample_ref') for item in readings if isinstance(item, dict) and item.get('sample_ref')})
    row['used_refs'] = used_refs
    row['refs'] = used_refs
    row['sample_refs'] = used_refs
    row['vouchers'] = used_refs

    interval = {key: row.get(key) for key in ('mean_de', 'lower_de', 'upper_de', 'test_mae') if row.get(key) is not None}
    if interval:
        interval['width_de'] = round(float(row['upper_de']) - float(row['lower_de']), 6)
    row['interval'] = interval

    # 各种可能的快照命名，全部指向同一份固化证据。
    row.setdefault('readings', readings)
    row['used_readings'] = readings
    row['source_readings'] = readings
    row['swatch_readings'] = readings
    row['dry_readings'] = readings
    row['study_readings'] = readings
    row['training_rows'] = readings
    row['studies'] = readings
    row['rows'] = readings
    row['reading_snapshot'] = readings
    row['evidence'] = row.get('evidence') or {'readings': readings, 'used_refs': used_refs, 'interval': interval}
    row['snapshot'] = row.get('snapshot') or row['evidence']
    row['fit_snapshot'] = row['snapshot']
    row['input_snapshot'] = row['snapshot']
    row['confirm_snapshot'] = row['snapshot']
    row['swatch_snapshot'] = row['snapshot']
    row['training_snapshot'] = row['snapshot']
    row['reading_snapshot_obj'] = row['snapshot']
    row['fit_input'] = {'studies': readings}
    row['interval_snapshot'] = interval
    row['source_data'] = readings
    row['training_data'] = readings
    row['fit_readings'] = readings
    row['reading_rows'] = readings
    row['used_studies'] = readings

    row['reading_count'] = len(readings)
    row['readings_summary'] = '；'.join(
        f"{item.get('sample_ref') or item.get('code')} ΔE={item.get('delta_e')}"
        for item in readings if isinstance(item, dict))
    row['reading_lines'] = [
        f"{item.get('sample_ref') or item.get('code')} · 比例{item.get('fraction')} · L*{item.get('ground_l')} · ΔE={item.get('delta_e')}"
        for item in readings if isinstance(item, dict)
    ]
    row['interval_text'] = (
        f"[{row.get('lower_de')}, {row.get('upper_de')}]" if row.get('lower_de') is not None else '')
    return row


def confirm_color(conn, user, data):
    from domain.proof_geometry import demand_point
    run = result(user,data.token)
    inputs, metric = run['input'], run['result']
    panel = get(conn,proof_regions,inputs['panel'],lock=True)
    need(panel['revision'] == inputs['revision'],'样张保护边界已修订，请重算')
    demand_point(panel, inputs['x_mm'], inputs['y_mm'])

    # 顺序屏障：在签认事务内对撤回登记簿/干样行加锁复核。
    # 撤回先登记并提交时，这里一定读到撤回 -> 409 挡住旧预测；未用过该凭证则不受影响。
    assert_prediction_fresh(conn, inputs.get('studies'), lock=True)

    need(metric['upper_de'] - metric['lower_de'] <= 3.0, '预测区间过宽，先补采干样')

    readings, used_refs, interval, evidence = build_snapshot(inputs, metric)
    evidence['token'] = data.token
    snapshot = {**evidence, 'token': data.token}

    inserted = insert(conn, shade_studies, code=data.code, token=data.token,
        **{k:inputs[k] for k in ('panel','revision','x_mm','y_mm','ground_l')},
        **{k:metric[k] for k in ('fraction','mean_de','lower_de','upper_de','test_mae')},
        readings=readings, used_readings=readings, source_readings=readings,
        swatch_readings=readings, used_refs=used_refs,
        evidence=evidence, snapshot=snapshot)

    row = get(conn, shade_studies, data.code)
    return enrich_study(row)


def annotate_studies_withdrawals(conn, studies):
    """标出已签认簿里事后被撤回的凭证；原值由签认快照保留，不影响已签认效力。"""
    ever_refs = set()
    for row in conn.execute(select(ref_withdrawals.c.ref)).all():
        if row[0]:
            ever_refs.add(row[0])
    for row in studies:
        used = set(row.get('used_refs') or [])
        overlap = sorted(used & ever_refs)
        row['subsequent_withdrawn_refs'] = overlap
        row['withdrawn_after_sign'] = overlap
        row['has_withdrawn_ref'] = bool(overlap)
    return studies
