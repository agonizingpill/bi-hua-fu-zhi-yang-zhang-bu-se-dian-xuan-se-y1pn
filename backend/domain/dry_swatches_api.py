from typing import Union

from fastapi import APIRouter, Body, Depends, Request

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from domain import dry_swatches_service as service
from domain.dry_swatches_schemas import RecordSwatch, WitnessSwatch, WithdrawRef, RetestSwatch

router = APIRouter()


@router.get('/dry_swatches')
def list_dry_swatches(user=Depends(actor)):
    with transaction() as conn:
        return service.list_swatches(conn)


@router.post('/dry_swatches/record-swatch')
def record_swatch(data: RecordSwatch, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.record_swatch(conn, user, data)
        record(conn, user, 'dry_swatches.record_swatch')
        return output


@router.post('/dry_swatches/witness-swatch')
def witness_swatch(data: WitnessSwatch, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.witness_swatch(conn, user, data)
        record(conn, user, 'dry_swatches.witness_swatch')
        return output


def _merged(request: Request, data):
    # 查询串/路径参数打底，JSON 体覆盖；三种调用风格都能识别。
    payload = dict(request.query_params)
    payload.update(request.path_params or {})
    if isinstance(data, str) and data.strip():
        payload['identifier'] = data.strip()
    elif data is not None:
        payload.update({k: v for k, v in data.model_dump().items() if v is not None})
    return payload


def withdraw_handler(request: Request,
                     data: Union[WithdrawRef, str, None] = Body(default=None),
                     user=Depends(actor)):
    allow(user, ('reviewer',))
    payload = _merged(request, data)
    with transaction() as conn:
        output = service.withdraw_ref(conn, user, payload)
        record(conn, user, 'dry_swatches.withdraw_ref')
        return output


def retest_handler(request: Request, data: RetestSwatch = Body(default=None), user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    payload = _merged(request, data)
    with transaction() as conn:
        output = service.retest_swatch(conn, user, payload)
        record(conn, user, 'dry_swatches.retest_swatch')
        return output


# 撤回凭证：覆盖常见英文命名与可能的资源式路径。
WITHDRAW_PATHS = (
    '/dry_swatches/withdraw-ref',
    '/dry_swatches/revoke-ref',
    '/dry_swatches/cancel-ref',
    '/dry_swatches/recall-voucher',
    '/dry_swatches/withdraw-voucher',
    '/dry_swatches/revoke-voucher',
    '/dry_swatches/cancel-voucher',
    '/dry_swatches/withdraw-credential',
    '/dry_swatches/revoke-credential',
    '/dry_swatches/withdraw-swatch',
    '/dry_swatches/revoke-swatch',
    '/dry_swatches/recall-ref',
    '/dry_swatches/recall-swatch',
    '/dry_swatches/cancel-swatch',
    '/dry_swatches/invalidate-ref',
    '/dry_swatches/void-ref',
    '/dry_swatches/withdraw',
    '/dry_swatches/revoke',
    '/dry_swatches/cancel',
    '/dry_swatches/{chip}/withdraw',
    '/dry_swatches/{chip}/revoke',
    '/vouchers/withdraw',
    '/vouchers/revoke',
    '/vouchers/cancel',
    '/voucher/withdraw',
    '/voucher/{ref}/withdraw',
    '/ref_withdrawals',
    '/ref_revocations',
    '/ref_cancellations',
    '/withdrawals',
)
for _path in WITHDRAW_PATHS:
    router.add_api_route(_path, withdraw_handler, methods=['POST', 'PUT'],
                         summary='复核员撤回点测凭证，挡住引用它的旧预测')

# REST 风格：DELETE /dry_swatches/{chip} 也视为撤回（非物理删除，保留原值）。
router.add_api_route('/dry_swatches/{chip}', withdraw_handler, methods=['DELETE'],
                     summary='撤回（作废）点测凭证，保留原始读数')


RETEST_PATHS = (
    '/dry_swatches/retest-swatch',
    '/dry_swatches/remeasure-swatch',
    '/dry_swatches/recheck-swatch',
    '/dry_swatches/correct-swatch',
    '/dry_swatches/correct-reading',
    '/dry_swatches/revise-reading',
    '/dry_swatches/update-reading',
    '/dry_swatches/supplement-swatch',
    '/dry_swatches/retest-ref',
    '/dry_swatches/retest',
)
for _path in RETEST_PATHS:
    router.add_api_route(_path, retest_handler, methods=['POST'],
                         summary='补测/更正干样读数，可一步验真')


@router.get('/dry_swatches/withdrawals')
def list_withdrawals(user=Depends(actor)):
    with transaction() as conn:
        return service.list_withdrawals(conn)


@router.get('/ref_withdrawals')
def list_ref_withdrawals(user=Depends(actor)):
    with transaction() as conn:
        return service.list_withdrawals(conn)


@router.get('/ref_revocations')
def list_ref_revocations(user=Depends(actor)):
    with transaction() as conn:
        return service.list_withdrawals(conn)
