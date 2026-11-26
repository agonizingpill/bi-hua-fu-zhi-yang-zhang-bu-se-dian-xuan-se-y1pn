from fastapi import APIRouter, Depends

from core.auth import actor
from core.db import transaction
from core.queueing import list_jobs, view
from core.records import scan
from domain.dry_swatches_model import dry_swatches
from domain.dry_swatches_service import enrich_swatch
from domain.shade_studies_model import shade_studies
from domain.shade_studies_service import enrich_study, annotate_studies_withdrawals

router = APIRouter()


def build_workbench(conn, user):
    studies = [enrich_study(row) for row in scan(conn, shade_studies)]
    studies = annotate_studies_withdrawals(conn, studies)
    swatches = [enrich_swatch(row) for row in scan(conn, dry_swatches)]
    predictions = list_jobs(user, conn=conn)
    pending = [job['token'] for job in predictions if job.get('retest_required')]
    return {
        'studies': studies,
        'shade_studies': studies,
        'swatches': swatches,
        'dry_swatches': swatches,
        'predictions': predictions,
        'jobs': predictions,
        'pending_retest': pending,
        'pending_retest_tokens': pending,
        'pending_retest_count': len(pending),
        'counts': {
            'studies': len(studies),
            'swatches': len(swatches),
            'predictions': len(predictions),
            'pending_retest': len(pending),
        },
    }


@router.get('/workbench')
def workbench(user=Depends(actor)):
    with transaction() as conn:
        return build_workbench(conn, user)


@router.get('/workbench/predictions')
def workbench_predictions(user=Depends(actor)):
    return list_jobs(user)


@router.get('/predictions')
def predictions(user=Depends(actor)):
    return list_jobs(user)


@router.get('/predictions/{token}')
def prediction_detail(token: str, user=Depends(actor)):
    return view(user, token)


@router.get('/predictions/{token}/validity')
def prediction_validity(token: str, user=Depends(actor)):
    data = view(user, token)
    return {
        'token': token,
        'valid': not data.get('invalid'),
        'invalid': data.get('invalid'),
        'stale': data.get('stale'),
        'retest_required': data.get('retest_required'),
        'state_label': data.get('state_label'),
        'marker': data.get('marker'),
        'withdrawn_refs': data.get('withdrawn_refs'),
        'used_refs': data.get('used_refs'),
    }


@router.get('/compute/{token}/validity')
def compute_validity(token: str, user=Depends(actor)):
    return prediction_validity(token, user)


@router.get('/shade_studies/prediction/{token}')
def shade_prediction(token: str, user=Depends(actor)):
    return view(user, token)
