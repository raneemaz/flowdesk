import pytest

from app.ai.providers import AICompletionResponse, AIProvider, AIProviderTimeoutError, AIToolCompletionResponse, AIToolUse
from app.ai_assistant.service import AIAssistantError, ask_assistant
from app.authz.permissions import MembershipRole, PermissionScope
from app.extensions import db
from app.models import Membership, MembershipStatus, Organization, Task, TaskStatus, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Task).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_org_with_owner(slug):
    org = Organization(name="Acme Inc", slug=slug, timezone="UTC")
    db.session.add(org)
    db.session.commit()
    user = User(name="Owner", email=f"{slug}@example.com")
    user.set_password("correct horse battery")
    db.session.add(user)
    db.session.commit()
    membership = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
    db.session.add(membership)
    db.session.commit()
    return org, membership


class _ScriptedProvider(AIProvider):
    """Returns each entry in `script` in order, one per call to
    complete_with_tools - lets a test drive a specific multi-round
    tool-use conversation deterministically."""

    def __init__(self, script: list[AIToolCompletionResponse]):
        self._script = list(script)
        self.calls = 0
        self.messages_seen: list[list[dict]] = []

    def complete(self, request, *, timeout_seconds):
        raise NotImplementedError

    def complete_with_tools(self, messages, *, system_prompt, tools, max_tokens, timeout_seconds):
        self.messages_seen.append(messages)
        response = self._script[self.calls]
        self.calls += 1
        return response


class _AlwaysFailsProvider(AIProvider):
    def complete(self, request, *, timeout_seconds):
        raise NotImplementedError

    def complete_with_tools(self, messages, *, system_prompt, tools, max_tokens, timeout_seconds):
        raise AIProviderTimeoutError("provider is down")


def test_ask_assistant_returns_the_final_text_when_no_tool_is_needed(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-notool")
        provider = _ScriptedProvider(
            [AIToolCompletionResponse(text="Hello!", tool_uses=[], model="m", input_tokens=1, output_tokens=1)]
        )

        answer = ask_assistant(
            org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "hi", provider=provider,
            max_tokens=100, timeout_seconds=5, max_retries=0,
        )

        assert answer == "Hello!"
        assert provider.calls == 1


def test_ask_assistant_executes_a_real_tool_call_and_feeds_the_result_back(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-tool")
        db.session.add(Task(organization_id=org.id, creator_membership_id=owner.id, title="t", status=TaskStatus.TODO))
        db.session.commit()

        provider = _ScriptedProvider(
            [
                AIToolCompletionResponse(
                    text=None,
                    tool_uses=[AIToolUse(id="t1", name="get_overview_metrics", input={"period": "current_month"})],
                    model="m",
                    input_tokens=1,
                    output_tokens=1,
                ),
                AIToolCompletionResponse(
                    text="You have 1 active task this month.", tool_uses=[], model="m", input_tokens=1, output_tokens=1
                ),
            ]
        )

        answer = ask_assistant(
            org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "how many active tasks?", provider=provider,
            max_tokens=100, timeout_seconds=5, max_retries=0,
        )

        assert answer == "You have 1 active task this month."
        assert provider.calls == 2
        # The second call must have received the real tool result,
        # proving it was actually executed (not skipped/faked).
        second_call_messages = provider.messages_seen[1]
        tool_result_message = second_call_messages[-1]
        assert tool_result_message["role"] == "user"
        tool_result_block = tool_result_message["content"][0]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["tool_use_id"] == "t1"
        assert '"active_tasks": 1' in tool_result_block["content"]


def test_ask_assistant_feeds_a_permission_denied_tool_result_back_without_crashing(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-denied")
        provider = _ScriptedProvider(
            [
                AIToolCompletionResponse(
                    text=None,
                    tool_uses=[AIToolUse(id="t1", name="get_overview_metrics", input={"period": "current_month"})],
                    model="m",
                    input_tokens=1,
                    output_tokens=1,
                ),
                AIToolCompletionResponse(
                    text="I can't access that information for your role.", tool_uses=[], model="m", input_tokens=1, output_tokens=1
                ),
            ]
        )

        # OWN/Employee is not allowed to call get_overview_metrics (FULL
        # only) - the tool call must come back as an error, not raise.
        answer = ask_assistant(
            org, PermissionScope.OWN, MembershipRole.EMPLOYEE, owner.id, "what's our overview?", provider=provider,
            max_tokens=100, timeout_seconds=5, max_retries=0,
        )

        assert answer == "I can't access that information for your role."
        tool_result_block = provider.messages_seen[1][-1]["content"][0]
        assert '"error"' in tool_result_block["content"]


def test_ask_assistant_raises_after_too_many_tool_use_rounds(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-toomany")
        # Always asks for another tool call, never gives a final answer.
        infinite_tool_use = AIToolCompletionResponse(
            text=None,
            tool_uses=[AIToolUse(id="t1", name="get_overview_metrics", input={"period": "current_month"})],
            model="m",
            input_tokens=1,
            output_tokens=1,
        )
        provider = _ScriptedProvider([infinite_tool_use] * 10)

        with pytest.raises(AIAssistantError):
            ask_assistant(
                org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "loop forever", provider=provider,
                max_tokens=100, timeout_seconds=5, max_retries=0,
            )


def test_ask_assistant_wraps_a_provider_failure(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-failure")

        with pytest.raises(AIAssistantError):
            ask_assistant(
                org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "hi",
                provider=_AlwaysFailsProvider(), max_tokens=100, timeout_seconds=5, max_retries=0,
            )


def test_ask_assistant_wraps_a_misconfigured_default_provider(app):
    """No ANTHROPIC_API_KEY configured (the real default in tests)."""
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-noapikey")

        with pytest.raises(AIAssistantError):
            ask_assistant(org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "hi")


def test_ask_assistant_returns_empty_string_not_none_when_the_model_gives_no_text(app):
    with app.app_context():
        org, owner = _make_org_with_owner("org-assistant-notext")
        provider = _ScriptedProvider(
            [AIToolCompletionResponse(text=None, tool_uses=[], model="m", input_tokens=1, output_tokens=1)]
        )

        answer = ask_assistant(
            org, PermissionScope.FULL, MembershipRole.OWNER, owner.id, "hi", provider=provider,
            max_tokens=100, timeout_seconds=5, max_retries=0,
        )

        assert answer == ""
