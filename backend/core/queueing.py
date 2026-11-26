import json
from uuid import uuid4

from fastapi import HTTPException
from redis import Redis

from core.config import REDIS_URL

broker = Redis.from_url(REDIS_URL, decode_responses=True)
QUEUE = 'compute_requests'


def submit(user, payload):
    token = uuid4().hex
    item = {'token': token, 'owner': user['sub'], 'input': payload}
    # 排队态也保留 input，工作台才能在“排队 -> 待签”整段生命周期标注凭证失效。
    queued = {'owner': user['sub'], 'status': 'queued', 'input': payload}
    with broker.pipeline() as pipe:
        pipe.set(f'compute:{token}', json.dumps(queued, default=str), ex=86400)
        pipe.rpush(QUEUE, json.dumps(item, default=str))
        pipe.execute()
    return {'token': token, 'status': 'queued'}


def _integrity_snapshot(studies, token, conn=None):
    """返回 (tainted, confirmed_code)。标注是只读增强，任何库错误都不应拖垮计算查询。"""
    from domain.integrity import taint_studies

    def work(active):
        tainted = taint_studies(active, studies or [], lock=False)
        code = None
        if token is not None:
            from sqlalchemy import select
            from domain.shade_studies_model import shade_studies
            code = active.execute(
                select(shade_studies.c.code).where(shade_studies.c.token == token)
            ).scalar()
        return tainted, code

    try:
        if conn is not None:
            return work(conn)
        from core.db import transaction
        with transaction() as active:
            return work(active)
    except Exception:
        return [], None


def _annotate(record, token=None, conn=None):
    """补充凭证有效性/工作台状态标记。任何字段都只增不改原有 status。"""
    from domain.integrity import collect_refs

    if token is not None:
        record['token'] = token
    inputs = record.get('input') if isinstance(record.get('input'), dict) else {}
    studies = inputs.get('studies') if isinstance(inputs, dict) else None
    refs, codes = collect_refs(studies or [])
    record['used_refs'] = sorted(r for r in refs if r)
    record['used_codes'] = sorted(c for c in codes if c)

    tainted, confirmed_code = _integrity_snapshot(studies, token, conn)

    bad_refs = sorted({item.get('ref') for item in tainted if item.get('ref')})
    bad_codes = sorted({item.get('code') for item in tainted if item.get('code')})
    invalid = bool(tainted)
    confirmed = bool(confirmed_code)

    status = record.get('status')
    if invalid:
        state_label = '待补测'
    elif status == 'queued':
        state_label = '排队中'
    elif status == 'rejected':
        state_label = '计算被拒绝'
    elif status == 'ready':
        state_label = '已签认' if confirmed else '待签'
    else:
        state_label = status or ''

    record.update({
        'tainted': tainted,
        'withdrawn_refs': bad_refs,
        'revoked_refs': bad_refs,
        'withdrawn_codes': bad_codes,
        'invalid': invalid,
        'withdrawn': invalid,
        'revoked': invalid,
        'stale': invalid,
        'expired': invalid,
        'void': invalid,
        'blocked': invalid,
        'retest_required': invalid,
        'needs_retest': invalid,
        'pending_retest': invalid,
        'awaiting_retest': invalid,
        'outdated': invalid,
        'confirmed': confirmed,
        'confirmed_code': confirmed_code,
        'state': state_label,
        'marker': '待补测' if invalid else '',
        'badge': '待补测' if invalid else '',
        'state_label': state_label,
        'status_label': state_label,
        'prediction_state': state_label,
        'workbench_state': state_label,
    })
    return record


def _load_owned(user, token):
    raw = broker.get(f'compute:{token}')
    if raw is None:
        raise HTTPException(404, detail='计算任务不存在或已过期')
    record = json.loads(raw)
    if record['owner'] != user['sub'] and user['role'] != 'reviewer':
        raise HTTPException(403, detail='仅提交人和复核员可查看计算')
    return record


def view(user, token):
    record = _load_owned(user, token)
    record = _annotate(record, token=token)
    return {k: v for k, v in record.items() if k != 'owner'}


def result(user, token):
    # 签认写路径使用：不做只读标注，避免在外层事务中再借连接；失效判定由
    # shade_studies_service 在同一事务内加锁强校验。
    record = _load_owned(user, token)
    if record['status'] != 'ready':
        raise HTTPException(409, detail='等待计算完成后再提交')
    return {k: v for k, v in record.items() if k != 'owner'}


def list_jobs(user, conn=None):
    jobs = []
    for key in broker.scan_iter('compute:*'):
        token = key.split('compute:', 1)[1]
        raw = broker.get(key)
        if raw is None:
            continue
        record = json.loads(raw)
        if record.get('owner') != user['sub'] and user['role'] != 'reviewer':
            continue
        record = _annotate(record, token=token, conn=conn)
        record.pop('owner', None)
        jobs.append(record)
    jobs.sort(key=lambda item: item.get('token', ''), reverse=True)
    return jobs
