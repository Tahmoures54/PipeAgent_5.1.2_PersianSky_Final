from datetime import date, timedelta
from services.execution_intelligence import ExecutionIntelligence


def test_what_if_is_transparent():
    x=ExecutionIntelligence.what_if(100,20,4,2,1)
    assert x['ndt_queue_after_extra_shift']==17
    assert x['constraint_dependency'] is True
    assert x['test_recovery_priority'] is True
    assert 'not a schedule promise' in x['message']
