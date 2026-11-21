import pytest

from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
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


def test_unauthenticated_ask_request_returns_401(client):
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/ai-assistant/ask", json={"question": "hi"}
    )
    assert response.status_code == 401


def test_a_non_member_cannot_ask_a_foreign_organizations_assistant(client, app):
    owner_a_csrf = _register_and_login(client, "owner-assistant-a@example.com")
    org_a = _create_org(client, owner_a_csrf, name="Org A")
    owner_b_csrf = _register_and_login(client, "owner-assistant-b@example.com")
    _create_org(client, owner_b_csrf, name="Org B")

    response = client.post(
        f"/api/v1/organizations/{org_a['id']}/ai-assistant/ask",
        json={"question": "hi"},
        headers={"X-CSRF-Token": owner_b_csrf},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.ACCOUNTANT, MembershipRole.CUSTOMER_SUPPORT]
)
def test_every_role_can_reach_the_endpoint_and_gets_a_clean_failure_without_an_api_key(client, app, role):
    """Every role has a non-NONE ANALYTICS_VIEW scope, so the route
    itself never 403s any role - confirmed here for all four non-Owner
    roles. No ANTHROPIC_API_KEY is configured in the test environment,
    so every role's attempt fails the same clean way (502), proving
    the route-level gate passed before the AI call itself failed."""
    csrf_token = _register_and_login(client, f"owner-assistant-role-{role.value}@example.com")
    org = _create_org(client, csrf_token)
    other_email = f"other-assistant-role-{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-assistant/ask",
        json={"question": "how many tasks are there?"},
        headers={"X-CSRF-Token": other_csrf},
    )

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "AI_ASSISTANT_FAILED"
    assert response.get_json()["error"]["details"] == {"reason": "upstream_provider_error"}


def test_owner_can_reach_the_endpoint_and_gets_a_clean_failure_without_an_api_key(client, app):
    csrf_token = _register_and_login(client, "owner-assistant-clean@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-assistant/ask",
        json={"question": "how many tasks are there?"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 502


def test_ask_rejects_an_empty_question(client, app):
    csrf_token = _register_and_login(client, "owner-assistant-empty@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-assistant/ask",
        json={"question": ""},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_ask_rejects_a_missing_question_field(client, app):
    csrf_token = _register_and_login(client, "owner-assistant-missing@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-assistant/ask",
        json={},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_ask_requires_csrf_token(client, app):
    csrf_token = _register_and_login(client, "owner-assistant-csrf@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(f"/api/v1/organizations/{org['id']}/ai-assistant/ask", json={"question": "hi"})

    assert response.status_code == 403


def test_ask_answers_for_real_with_a_fake_provider_end_to_end(client, app, monkeypatch):
    import json as json_module

    from app.ai.providers import AICompletionResponse, AIProvider

    class _FakeProvider(AIProvider):
        def complete(self, request, *, timeout_seconds):
            raise NotImplementedError

        def complete_with_tools(self, messages, *, system_prompt, tools, max_tokens, timeout_seconds):
            from app.ai.providers import AIToolCompletionResponse

            return AIToolCompletionResponse(
                text="You have 0 active tasks this month.", tool_uses=[], model="claude-haiku-5-5", input_tokens=1, output_tokens=1
            )

    monkeypatch.setattr("app.ai.providers.build_default_provider", lambda: _FakeProvider())

    csrf_token = _register_and_login(client, "owner-assistant-e2e@example.com")
    org = _create_org(client, csrf_token)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/ai-assistant/ask",
        json={"question": "how many active tasks do we have?"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["answer"] == "You have 0 active tasks this month."
