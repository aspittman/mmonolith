from services.shared.product_research import build_bundle as _build
from . import SERVICE_ID

def build_bundle(org, rows, domains, run_key, **kwargs):
    return _build(SERVICE_ID, org, rows, domains, run_key, **kwargs)
