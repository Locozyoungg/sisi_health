"""The conversation pipeline (spec 5.2).

The ORDER of the steps is the safety property, and every step short-circuits:

    1. deterministic red-flag matcher  -> urgent script + hotlines, model never called
    2. deterministic refusal detectors -> prescription ask, diagnosis/risk ask
    3. topic filter                    -> women's health only
    4. minor gate                      -> procedures hard-gated; sexual-health two-step
    5. retrieval                       -> no approved chunks means no answer
    6. system prompt                   -> engine values + chunk ids only, no identifiers
    7. provider call                   -> recording wrapper makes "never called" testable
    8. post-filter                     -> diagnosis/prescription/dose/band/leak/citation
    9. education + cited chunks (+ the deterministic nurse line for a minor who had sex)

A model answer that fails step 8 is NEVER returned: the user gets a deterministic
refusal text instead, so no unguarded model output can reach a user (HZ-07).
"""

import time
from typing import Annotated, Literal

from app.config import Settings as BackendSettings
from app.rules.redflags import RedFlagMatcher
from pydantic import BaseModel, Field, field_validator

from ai_service.config import AISettings
from ai_service.guardrails import (
    ROUTING_AGE_GATED_MINOR,
    ROUTING_EDUCATION,
    ROUTING_OUT_OF_SCOPE,
    ROUTING_REFUSE_DIAGNOSIS,
    ROUTING_REFUSE_PRESCRIPTION,
    ROUTING_REFUSED,
    ROUTING_URGENT_SCRIPT,
    DiagnosisAskDetector,
    MinorTopicGate,
    PostFilter,
    PrescriptionAskDetector,
    TopicFilter,
    build_urgent_script,
    citations_for,
    minor_no_sex_text,
    minor_nurse_line,
    minor_sex_check_text,
    refusal_text,
)
from ai_service.prompts import build_system_prompt, build_user_message
from ai_service.providers.embeddings import EmbeddingProvider
from ai_service.providers.llm import Completion, LLMProvider
from ai_service.rag import EmbeddingStore, SearchHit

Language = Literal["en", "sw", "sheng"]
Band = Literal["GREEN", "YELLOW", "ORANGE", "RED"]

INDICATOR_ID_RE = r"^[a-z0-9-]{3,64}$"


class AskRequest(BaseModel):
    """The /ask contract. There is deliberately no id, phone, name, or email field:
    the schema physically cannot carry a patient identifier into a prompt (A36)."""

    text: str = Field(min_length=1, max_length=2000)
    language: Language = "en"
    age: int | None = Field(default=None, ge=13, le=120)
    # Two-step answer for a minor's sexual-health question (A38): the app asks the
    # deterministic check question first and re-asks with the reply. Permissive: it is
    # ignored for adults (the minor gate never consumes it), and never an identifier.
    minor_has_sex: bool | None = None
    band: Band | None = None
    indicators: list[Annotated[str, Field(pattern=INDICATOR_ID_RE)]] = Field(default_factory=list)
    urgent: bool = False
    safeguarding: bool = False

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class Citation(BaseModel):
    chunk_id: str
    title: str
    language: str


class AskResponse(BaseModel):
    routing: str
    text: str
    language: str
    citations: list[Citation] = Field(default_factory=list)
    band: str | None = None
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    postfilter_reason: str | None = None


class ConversationService:
    """Deterministic-first conversation service. The LLM is the LAST thing consulted
    and the FIRST thing discarded."""

    def __init__(
        self,
        *,
        settings: AISettings,
        backend_settings: BackendSettings,
        matcher: RedFlagMatcher,
        store: EmbeddingStore,
        embedder: EmbeddingProvider,
        llm: LLMProvider,
    ) -> None:
        self._settings = settings
        self._backend = backend_settings
        self._matcher = matcher
        self._store = store
        self._embedder = embedder
        self._llm = llm
        self._topic_filter = TopicFilter()
        self._minor_gate = MinorTopicGate()
        self._diagnosis_ask = DiagnosisAskDetector()
        self._prescription_ask = PrescriptionAskDetector()
        self._postfilter = PostFilter()

    @property
    def llm(self) -> LLMProvider:
        return self._llm

    @property
    def store(self) -> EmbeddingStore:
        return self._store

    def ask(self, request: AskRequest) -> AskResponse:
        started = time.perf_counter()
        text_value = request.text.strip()
        language = request.language

        # 1. Red flags first, always (spec 3.3): deterministic script, no model call,
        #    and no other state can override it. An engine `urgent`/`safeguarding`
        #    escalation forces the same script even without a text match.
        hits = self._matcher.match_text(text_value)
        if hits or request.urgent or request.safeguarding:
            script = build_urgent_script(
                hits,
                self._backend,
                language=language,
                safeguarding=request.safeguarding,
            )
            return self._respond(request, started, routing=ROUTING_URGENT_SCRIPT, text=script)

        # 2. Deterministic refusals, before the model (D9): a prescription request or
        #    a diagnosis/risk question is never answered conversationally.
        if self._prescription_ask.is_prescription_ask(text_value, language):
            return self._refuse(request, started, ROUTING_REFUSE_PRESCRIPTION)
        if self._diagnosis_ask.is_diagnosis_ask(text_value, language):
            return self._refuse(request, started, ROUTING_REFUSE_DIAGNOSIS)

        # 3. Scope: women's health only.
        if not self._topic_filter.is_womens_health(text_value, language):
            return self._refuse(request, started, ROUTING_OUT_OF_SCOPE)

        # 4. Minor gate (spec 3.2/3.3, A38). Unknown age counts as a minor. Procedure
        #    topics are HARD-gated: generic referral, zero model calls, zero content,
        #    whatever minor_has_sex says. A sexual-health question takes the TWO-STEP —
        #    teenage pregnancy is real, so a minor who has had sex gets age-appropriate
        #    education plus a nurse referral, never a dead end; a minor who has not gets
        #    generic guidance plus the same referral; an unknown answer gets the
        #    deterministic check question so the caller can re-ask with the reply.
        minor_sex_education = False
        if self._minor_gate.applies(request.age):
            if self._minor_gate.is_procedure_gated(text_value, language):
                return self._refuse(request, started, ROUTING_AGE_GATED_MINOR)
            if self._minor_gate.is_sexual_health_gated(text_value, language):
                if request.minor_has_sex is None:
                    return self._respond(
                        request,
                        started,
                        routing=ROUTING_AGE_GATED_MINOR,
                        text=minor_sex_check_text(language),
                    )
                if request.minor_has_sex is False:
                    return self._respond(
                        request,
                        started,
                        routing=ROUTING_AGE_GATED_MINOR,
                        text=minor_no_sex_text(language),
                    )
                minor_sex_education = True

        # 5. Retrieval: no approved content means no answer (never a guess).
        query_vector = self._embedder.embed([text_value])[0]
        hits = self._store.search(
            query_vector,
            language=language,
            model=self._embedder.model,
            top_k=self._settings.ai_rag_top_k,
        )
        if not hits:
            return self._refuse(request, started, ROUTING_REFUSED)

        # 6. Prompt: engine output + chunk ids only. A minor who has had sex additionally
        #    gets one age-framing line (no identifiers, no condition, no medicine).
        system_prompt = build_system_prompt(
            language=language,
            band=request.band,
            indicators=request.indicators,
            hits=hits,
            minor_has_sex=minor_sex_education,
        )
        user_message = build_user_message(text_value)

        # 7. The one and only model call.
        completion = self._llm.complete(
            system=system_prompt,
            user=user_message,
            max_output_tokens=self._settings.ai_max_output_tokens,
            temperature=self._settings.ai_temperature,
        )

        # 8. Post-filter anything the model said. Raw model text is dropped here.
        verdict = self._postfilter.check(completion.text, band=request.band)
        if not verdict["ok"]:
            return self._refuse(
                request,
                started,
                ROUTING_REFUSED,
                completion=completion,
                postfilter_reason=verdict["reason"],
            )

        # 9. Education with the chunks the answer actually cites. For a minor who has had
        #    sex the deterministic nurse referral is appended AFTER the post-filter — the
        #    filter only ever judges model text — and the routing stays `education` with
        #    its citations intact. A refusal never gets the line: it is already referral.
        cited = citations_for(completion.text, hits)
        text_out = completion.text
        if minor_sex_education:
            text_out = f"{text_out}\n\n{minor_nurse_line(language)}"
        return self._respond(
            request,
            started,
            routing=ROUTING_EDUCATION,
            text=text_out,
            citations=cited,
            completion=completion,
        )

    def _refuse(
        self,
        request: AskRequest,
        started: float,
        routing: str,
        *,
        completion: Completion | None = None,
        postfilter_reason: str | None = None,
    ) -> AskResponse:
        """Deterministic refusal: the routing's own text, never model output."""
        return self._respond(
            request,
            started,
            routing=routing,
            text=refusal_text(routing, request.language),
            completion=completion,
            postfilter_reason=postfilter_reason,
        )

    def _respond(
        self,
        request: AskRequest,
        started: float,
        *,
        routing: str,
        text: str,
        citations: list[SearchHit] | None = None,
        completion: Completion | None = None,
        postfilter_reason: str | None = None,
    ) -> AskResponse:
        return AskResponse(
            routing=routing,
            text=text,
            language=request.language,
            citations=[
                Citation(chunk_id=hit.chunk_id, title=hit.title, language=hit.language)
                for hit in (citations or [])
            ],
            band=request.band,
            provider=completion.provider if completion else self._llm.name,
            model=completion.model if completion else self._llm.model,
            input_tokens=completion.input_tokens if completion else 0,
            output_tokens=completion.output_tokens if completion else 0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            postfilter_reason=postfilter_reason,
        )
