from services.execution_os import ExecutionOSService

def test_what_if_contract():
    svc=ExecutionOSService(None)
    # methods are intentionally pure for deterministic contracts
    out=svc._health({'severity':'High'},{'ready_unassigned':0},{'repair_rate_pct':0},{'gaps':[]})
    assert out['score'] == 85
    assert out['label'] == 'Controlled'

def test_quality_empty():
    svc=ExecutionOSService(None)
    out=svc._quality_intelligence([],[])
    assert out['repair_rate_pct'] == 0
    assert out['ndt_failures'] == 0
