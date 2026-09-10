from services.product_commercial import PLANS, plan_for_license_type, has_feature, ValueEngine
from db.models import Project, PredictionRun


def test_license_to_plan_mapping():
    assert plan_for_license_type('trial') == 'pilot'
    assert plan_for_license_type('1year') == 'professional'
    assert plan_for_license_type('unlimited') == 'enterprise'


def test_enterprise_features_are_not_available_on_pilot():
    assert has_feature({'type': 'trial'}, 'integrations') is False
    assert has_feature({'type': 'unlimited'}, 'integrations') is True
    assert has_feature({'type': 'unlimited'}, 'sso') is True


def test_value_report_is_read_only(db_manager):
    with db_manager.session_scope() as s:
        p = Project(project_code='VAL-TEST', title='Value Test')
        s.add(p); s.flush(); pid = p.id
        before = s.query(PredictionRun).filter_by(project_id=pid).count()
    ValueEngine(db_manager).calculate(pid)
    with db_manager.session_scope() as s:
        after = s.query(PredictionRun).filter_by(project_id=pid).count()
    assert before == after == 0
