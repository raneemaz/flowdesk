"""FD-061: the conversational AI assistant's orchestration loop
(FR-041, "retrieves authorized, structured data before answering").
Ties `app.ai.providers`'s tool-use completion shape to
`app.ai_assistant.tools`'s permission-aware tool registry in a bounded
multi-turn loop - the model calls zero or more tools, this module
executes each one with the REAL caller's own scope/role (never a
broader one), feeds the results back, and repeats until the model
stops asking for tools and gives a final text answer.

**"No unapproved writes"** (this task's own title): every tool in
`app.ai_assistant.tools.TOOL_DEFINITIONS` is read-only - there is no
tool that creates, edits, or deletes anything, and the system prompt
below explicitly tells the model it has no such capability. This
isn't a runtime-enforced sandbox around some larger tool surface; it's
simply that no write tool exists for the model to call.

**Stateless, one question in, one answer out** (FR-041's own example
shape: "How many tasks were completed this month?" -> an answer) - no
conversation history is persisted across requests, unlike FD-058's
`AIReport`; a multi-turn tool-use exchange with the AI provider still
happens internally per single HTTP request, but nothing is written to
the database when it's done."""

import json

from app.ai.providers import AIProvider, AIProviderError, complete_with_tools_with_retries
from app.ai_assistant.tools import TOOL_DEFINITIONS, execute_tool
from app.authz.permissions import MembershipRole, PermissionScope
from app.models import Organization

_SYSTEM_PROMPT = """You are FlowDesk's business assistant. Answer the user's question using \
ONLY the provided tools - never invent, estimate, or recall any business fact from outside \
what a tool actually returns to you.

If the user's question implies a reporting period but doesn't name one, use "current_month" \
and say so in your answer - always state which period your answer covers.

If a tool result contains an "error" field, that means the signed-in user's own role doesn't \
have permission to see that information. Tell them plainly that you can't access it for their \
role - never guess a plausible-sounding number instead.

You can only answer questions using the data these tools expose. You cannot create, edit, or \
delete anything, and you cannot perform any financial or administrative action. If asked to do \
something other than answer a question, say that you can only provide information."""

_MAX_ITERATIONS = 5


class AIAssistantError(Exception):
    """Wraps either a provider-level failure (`AIProviderError`) or too
    many tool-use rounds without a final answer - the one error type a
    caller (the route) needs to catch to know "no answer was
    produced"."""


def ask_assistant(
    organization: Organization,
    scope: PermissionScope,
    role: MembershipRole,
    caller_membership_id,
    question: str,
    *,
    provider: AIProvider | None = None,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> str:
    """`organization`/`scope`/`role`/`caller_membership_id` are the
    REAL caller's own already-resolved values (same as
    `app.analytics.routes`'s own `g.current_membership.organization`/
    `g.permission_scope`/`g.current_membership.role`/
    `g.current_membership.id`) - every tool call below is executed
    with exactly these, never anything broader.

    `provider`/`max_tokens`/`timeout_seconds`/`max_retries` default to
    `None`, resolved from `current_app.config` only when actually
    needed - same testability convention
    `app.ai.service.generate_report_for_organization` already
    established."""
    if provider is None:
        from app.ai.providers import build_default_provider

        try:
            provider = build_default_provider()
        except AIProviderError as exc:
            raise AIAssistantError(f"AI provider could not be configured: {exc}") from exc

    if max_tokens is None or timeout_seconds is None or max_retries is None:
        from flask import current_app

        config = current_app.config
        if max_tokens is None:
            max_tokens = config["AI_MAX_TOKENS"]
        if timeout_seconds is None:
            timeout_seconds = config["AI_REQUEST_TIMEOUT_SECONDS"]
        if max_retries is None:
            max_retries = config["AI_MAX_RETRIES"]

    messages: list[dict] = [{"role": "user", "content": question}]

    for _ in range(_MAX_ITERATIONS):
        try:
            response = complete_with_tools_with_retries(
                provider,
                messages,
                system_prompt=_SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        except AIProviderError as exc:
            raise AIAssistantError(f"AI provider call failed: {exc}") from exc

        if not response.tool_uses:
            return response.text or ""

        assistant_content = []
        if response.text:
            assistant_content.append({"type": "text", "text": response.text})
        for tool_use in response.tool_uses:
            assistant_content.append(
                {"type": "tool_use", "id": tool_use.id, "name": tool_use.name, "input": tool_use.input}
            )
        messages.append({"role": "assistant", "content": assistant_content})

        tool_result_content = [
            {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(
                    execute_tool(
                        tool_use.name,
                        tool_use.input,
                        organization=organization,
                        scope=scope,
                        role=role,
                        caller_membership_id=caller_membership_id,
                    ),
                    default=str,
                ),
            }
            for tool_use in response.tool_uses
        ]
        messages.append({"role": "user", "content": tool_result_content})

    raise AIAssistantError("The assistant could not produce an answer within the allowed number of tool calls.")
