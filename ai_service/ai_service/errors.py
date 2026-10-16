"""Error hierarchy for the AI service, mapped to the shared JSON envelope by
`ai_service.main`. Messages never echo user text, prompt content, or credentials."""

from typing import Any

from app.core.errors import AppError


class ProviderNotConfigured(AppError):
    """An LLM/embedding backend was selected but its endpoint or credentials are
    missing. Credentials are never invented from a default (non-negotiable 7):
    the provider refuses instead of calling out half-configured."""

    status_code = 503
    code = "provider_not_configured"


class GuardrailRefused(AppError):
    """A deterministic guardrail refused the conversation.

    The conversation pipeline reports refusals as `routing` values on a normal
    response (`refuse_diagnosis`, `refuse_prescription`, `out_of_scope`,
    `age_gated_minor`, `refused`), so a refusal is not an error by itself; this
    exception carries the same routing for callers that need exception semantics,
    and is raised by dependencies that must stop a request outright.
    """

    status_code = 422
    code = "guardrail_refused"

    def __init__(
        self, routing: str, message: str = "", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message or "This request cannot be answered here.", details)
        self.routing = routing
