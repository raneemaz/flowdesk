import uuid

import pytest

from app.extensions import db
from app.models import AIReport, Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(AIReport).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    return _login(client, email, password)


def _create_org(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        user = db.session.query(User).filter_by(email=email.lower()).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return str(membership.id)


def _make_ai_report(app, organization_id, period_start="2026-01-01", period_end="2026-01-31"):
    import datetime as dt

    from app.ai_reports.service import save_ai_report
    from app.ai.schemas import WeeklyReportOutput

    with app.app_context():
        output = WeeklyReportOutput(
            period_start=period_start,
            period_end=period_end,
            business_overview="x",
            employee_productivity="x",
            financial_overview="x",
            operational_problems="x",
            recommendations=[],
            missing_data=[],
            model="claude-haiku-5-5",
            generated_at=dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc),
        )
        report = save_ai_report(uuid.UUID(organization_id), "weekly", {}, output)
        return str(report.id)


# --- POST .../ai-reports/generate ---------------------------------------


def test_unauthenticated_generate_request_returns_401(client):
    response = client.post("/api/v1/organizations/00000000-0000-0000-0000-000000000000/ai-reports/generate", json={})
    assert response.status_code == 401


def test_owner_generating_a_report_fails_cleanly_without_a_configured_api_key(client, app):
    """No ANTHROPIC_API_KEY is configured in the test environment - the
    route must surface this as a clean 502 (AI_GENERATION_FAILED), not
    an unhandled 500, and must not persist a row."""
    csrf_token = _register_and_login(client, "owner-gen@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "current_month"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 502
    error = response.get_json()["error"]
    assert error["code"] == "AI_GENERATION_FAILED"
    # No raw upstream/exception text in the response - a caught
    # AIReportGenerationError must never be echoed to the client (it
    # can wrap an upstream provider's own raw error body); the detail
    # stays a fixed, generic reason.
    assert error["details"] == {"reason": "upstream_provider_error"}
    assert "An Anthropic API key is required" not in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(AIReport).count() == 0


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT])
def test_non_full_scope_roles_cannot_generate_a_report(client, app, role):
    csrf_token = _register_and_login(client, f"owner-gen-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"other-gen-{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "current_month"},
        headers={"X-CSRF-Token": other_csrf},
    )

    assert response.status_code == 403


def test_manager_can_attempt_to_generate_a_report(client, app):
    """Manager has full ANALYTICS_VIEW scope same as Owner - reaches
    the AI call (and fails the same way Owner's own attempt does,
    since no API key is configured), proving the permission check
    itself passes for Manager specifically."""
    csrf_token = _register_and_login(client, "owner-gen-mgr@example.com")
    org = _create_org(client, csrf_token)
    manager_email = "manager-gen-mgr@example.com"
    manager_csrf = _register_and_login(client, manager_email)
    _give_role(app, org["id"], manager_email, MembershipRole.MANAGER)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "current_month"},
        headers={"X-CSRF-Token": manager_csrf},
    )

    assert response.status_code == 502  # not 403 - the permission check passed


def test_generate_rejects_a_custom_period_missing_bounds(client, app):
    csrf_token = _register_and_login(client, "owner-gen-badperiod@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "custom"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_generate_rejects_an_unrecognized_period_value(client, app):
    csrf_token = _register_and_login(client, "owner-gen-unknownperiod@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "last_week"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def _fake_provider_returning_valid_json():
    import json as json_module

    from app.ai.providers import AICompletionResponse, AIProvider

    class _FakeProvider(AIProvider):
        def complete(self, request, *, timeout_seconds):
            return AICompletionResponse(
                text=json_module.dumps(
                    {
                        "business_overview": "x",
                        "employee_productivity": "x",
                        "financial_overview": "x",
                        "operational_problems": "x",
                        "recommendations": ["Follow up."],
                        "missing_data": [],
                    }
                ),
                model="claude-haiku-5-5",
                input_tokens=1,
                output_tokens=1,
            )

    return _FakeProvider()


def test_owner_can_generate_and_persist_a_real_report_end_to_end(client, app, monkeypatch):
    monkeypatch.setattr("app.ai.service.build_default_provider", _fake_provider_returning_valid_json)

    csrf_token = _register_and_login(client, "owner-gen-e2e@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "current_month"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["recommendations"] == ["Follow up."]
    assert data["provider"] == "anthropic"
    with app.app_context():
        assert db.session.query(AIReport).filter_by(organization_id=uuid.UUID(org["id"])).count() == 1


def test_generate_returns_409_for_a_period_that_already_has_a_report(client, app, monkeypatch):
    monkeypatch.setattr("app.ai.service.build_default_provider", _fake_provider_returning_valid_json)

    csrf_token = _register_and_login(client, "owner-gen-dup@example.com")
    org = _create_org(client, csrf_token)
    _make_ai_report(app, org["id"])

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-reports/generate",
        json={"period": "custom", "period_start": "2026-01-01", "period_end": "2026-01-31"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409


# --- GET .../ai-reports ---------------------------------------------------


def test_owner_can_list_ai_reports(client, app):
    csrf_token = _register_and_login(client, "owner-list@example.com")
    org = _create_org(client, csrf_token)
    _make_ai_report(app, org["id"])

    response = client.get(
        f"/api/v1/organizations/{org['id']}/ai-reports",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 1
    assert data[0]["period_start"] == "2026-01-01"


def test_employee_cannot_list_ai_reports(client, app):
    csrf_token = _register_and_login(client, "owner-list-emp@example.com")
    org = _create_org(client, csrf_token)
    employee_email = "employee-list-emp@example.com"
    employee_csrf = _register_and_login(client, employee_email)
    _give_role(app, org["id"], employee_email, MembershipRole.EMPLOYEE)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/ai-reports",
        headers={"X-CSRF-Token": employee_csrf},
    )

    assert response.status_code == 403


def test_a_non_member_cannot_list_a_foreign_organizations_ai_reports(client, app):
    owner_a_csrf = _register_and_login(client, "owner-list-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner-list-b@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(
        f"/api/v1/organizations/{org_a['id']}/ai-reports",
        headers={"X-CSRF-Token": owner_b_csrf},
    )

    assert response.status_code == 404


# --- GET .../ai-reports/{id} -----------------------------------------------


def test_owner_can_view_one_ai_report(client, app):
    csrf_token = _register_and_login(client, "owner-get@example.com")
    org = _create_org(client, csrf_token)
    report_id = _make_ai_report(app, org["id"])

    response = client.get(
        f"/api/v1/organizations/{org['id']}/ai-reports/{report_id}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["id"] == report_id
    assert set(data) == {
        "id",
        "organization_id",
        "report_type",
        "period_start",
        "period_end",
        "metrics_snapshot",
        "summary",
        "recommendations",
        "model",
        "provider",
        "generated_at",
        "created_at",
    }


def test_owner_gets_404_for_a_report_from_another_organization(client, app):
    owner_a_csrf = _register_and_login(client, "owner-get-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    report_id = _make_ai_report(app, org_a["id"])
    owner_b_csrf = _register_and_login(client, "owner-get-b@example.com")
    org_b = _create_org(client, owner_b_csrf, name="Org B")

    response = client.get(
        f"/api/v1/organizations/{org_b['id']}/ai-reports/{report_id}",
        headers={"X-CSRF-Token": owner_b_csrf},
    )

    assert response.status_code == 404
