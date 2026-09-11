from fastapi.testclient import TestClient

from app.demo import app

client = TestClient(app)


def test_member_not_found_is_explicit_business_outcome() -> None:
    response = client.get("/member", params={"member_id": "99999"})
    assert response.status_code == 200
    assert 'data-business-outcome="MEMBER_NOT_FOUND"' in response.text


def test_permission_case_has_intervention_marker() -> None:
    response = client.get("/member", params={"member_id": "70000"})
    assert 'data-intervention="PERMISSION_REQUIRED"' in response.text


def test_savings_page_contains_machine_readable_balance() -> None:
    response = client.get("/member/12345/savings")
    assert response.status_code == 200
    assert 'id="savings-balance">4621.77<' in response.text
