"""Hosted vs open-weight comparison (DoD item; human task H15 owns the real run).

This is a **STUB RUN**: it drives the full 150-case guardrail suite through the real
pipeline twice with two deterministic stub *profiles* that differ only in per-call
latency and model label, and writes docs/ai-comparison-report.md. Every number it
produces is a mechanical measurement of the pipeline (latency shape, token
accounting, cost arithmetic against the SISI_AI_PRICE_* sheet); model QUALITY —
especially Kiswahili and Sheng — is not measured here and is marked as pending a
human rating (H15). The report carries the exact procedure for the real run.

The profile supplies latency and model label; each case keeps the behaviour it
declares, so the guardrail routing evidence is identical across the two profiles and
the latency/cost comparison stays apples-to-apples.

Usage:
    python scripts/eval_compare.py          # write the report
    python scripts/eval_compare.py --ci     # also assert structure + stub thresholds

Runs against the DEV database and indexes /ontology content first (idempotent).
"""

import base64
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AI_SERVICE_DIR = SCRIPT_DIR.parent
REPO_ROOT = AI_SERVICE_DIR.parent

# Environment pinned BEFORE any app import, exactly like tests/conftest.py.
os.environ["SISI_ENV"] = "dev"
os.environ["SISI_ALLOW_UNVALIDATED_RULES"] = "true"
os.environ["SISI_AI_LLM_PROVIDER"] = "stub"
os.environ["SISI_AI_EMBEDDING_PROVIDER"] = "stub"
os.environ.setdefault("SISI_MASTER_KEY_B64", base64.b64encode(b"t" * 32).decode())
os.environ.setdefault("SISI_AI_INTERNAL_TOKEN", "dev-only-ai-token-change-me")
os.environ.setdefault(
    "SISI_DATABASE_URL", "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi"
)

if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings as get_backend_settings  # noqa: E402
from app.rules.loader import build_matcher  # noqa: E402

from ai_service.config import AISettings  # noqa: E402
from ai_service.eval.harness import (  # noqa: E402
    CaseSpec,
    HarnessContext,
    SuiteReport,
    load_ai_cases,
    run_suite,
)
from ai_service.providers.embeddings import build_embedding_provider  # noqa: E402
from ai_service.providers.llm import LLMProvider, StubProvider  # noqa: E402
from ai_service.rag import build_store, index_content  # noqa: E402

REPORT_PATH = REPO_ROOT / "docs" / "ai-comparison-report.md"
H15_MARKER = "STUB RUN — human rating pending (H15)"
MIN_CASES = 150


@dataclass(frozen=True)
class Profile:
    """One model profile: a stub stand-in for a real deployment target."""

    key: str
    label: str
    latency_ms: int
    model: str
    price_in: float
    price_out: float
    real_provider: str
    real_setup: str


@dataclass(frozen=True)
class ProfileStats:
    profile: Profile
    report: SuiteReport
    latencies: tuple[int, ...]
    model_latencies: tuple[int, ...]
    input_tokens: tuple[int, ...]
    output_tokens: tuple[int, ...]

    @property
    def conversations(self) -> int:
        return len(self.latencies)

    @property
    def model_calls(self) -> int:
        return len(self.model_latencies)

    @property
    def mean_input_tokens(self) -> float:
        return sum(self.input_tokens) / self.conversations if self.conversations else 0.0

    @property
    def mean_output_tokens(self) -> float:
        return sum(self.output_tokens) / self.conversations if self.conversations else 0.0

    @property
    def tokens_per_conversation(self) -> float:
        return self.mean_input_tokens + self.mean_output_tokens

    @property
    def cost_per_1000_usd(self) -> float:
        """USD per 1,000 conversations from the SISI_AI_PRICE_* sheet (A37)."""
        per_conversation = (
            self.mean_input_tokens / 1000.0 * self.profile.price_in
            + self.mean_output_tokens / 1000.0 * self.profile.price_out
        )
        return per_conversation * 1000.0


def percentile(values: tuple[int, ...], fraction: float) -> float:
    """Nearest-rank percentile; deterministic, no statistics dependency."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(fraction * len(ordered))))
    return float(ordered[rank - 1])


def mean(values: tuple[int, ...]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_profiles(settings: AISettings) -> tuple[Profile, Profile]:
    hosted = Profile(
        key="hosted",
        label="hosted API (pilot target)",
        latency_ms=520,
        model="stub-hosted-profile",
        price_in=settings.ai_price_hosted_in,
        price_out=settings.ai_price_hosted_out,
        real_provider="hosted",
        real_setup=(
            "SISI_AI_LLM_PROVIDER=hosted SISI_AI_HOSTED_API_KEY=<key> "
            "SISI_AI_HOSTED_MODEL=<model> (Anthropic-style POST {base}/v1/messages)"
        ),
    )
    openweight = Profile(
        key="openweight",
        label="open-weight on vLLM (target)",
        latency_ms=180,
        model="stub-openweight-profile",
        price_in=settings.ai_price_openweight_in,
        price_out=settings.ai_price_openweight_out,
        real_provider="openweight",
        real_setup=(
            "SISI_AI_LLM_PROVIDER=openweight "
            "SISI_AI_OPENWEIGHT_BASE_URL=http://<gpu-host>:8000/v1 "
            "SISI_AI_OPENWEIGHT_MODEL=<model> (vLLM, OpenAI-compatible)"
        ),
    )
    return hosted, openweight


def run_profile(
    context: HarnessContext, cases: Sequence[CaseSpec], profile: Profile
) -> ProfileStats:
    """Run the suite once with the profile's latency and model label."""

    def factory(behavior: str) -> LLMProvider:
        return StubProvider(behavior, latency_ms=profile.latency_ms, model=profile.model)

    profile_context = HarnessContext(
        settings=context.settings,
        backend_settings=context.backend_settings,
        matcher=context.matcher,
        store=context.store,
        embedder=context.embedder,
        llm_factory=factory,
    )
    report = run_suite(profile_context, cases, name=f"ai-guardrails[{profile.key}]")
    model_results = tuple(result for result in report.results if result.llm_called)
    return ProfileStats(
        profile=profile,
        report=report,
        latencies=tuple(result.latency_ms for result in report.results),
        model_latencies=tuple(result.latency_ms for result in model_results),
        input_tokens=tuple(result.input_tokens for result in report.results),
        output_tokens=tuple(result.output_tokens for result in report.results),
    )


def render_report(
    settings: AISettings,
    stats: tuple[ProfileStats, ...],
    *,
    chunks: int,
    mode: str,
    generated_at: str,
) -> str:
    hosted, openweight = stats
    lines: list[str] = []
    lines.append("# AI conversation layer — hosted vs open-weight comparison")
    lines.append("")
    lines.append("**STUB RUN.** This report was generated by `ai_service/scripts/eval_compare.py`")
    lines.append("with the deterministic stub providers: no model server was contacted and no")
    lines.append("credential exists on the authoring machine (non-negotiable 7). Every number")
    lines.append("below is a mechanical measurement of the *pipeline* — latency shape, token")
    lines.append("accounting and cost arithmetic — not a measurement of model quality. Do not")
    lines.append("cite it as evidence about a real model's answers. The real run is task H15.")
    lines.append("")
    lines.append(f"- Generated (UTC): {generated_at}")
    lines.append(f"- Suite: {hosted.report.total} AI guardrail cases through the real pipeline")
    lines.append(
        f"- Content library: {chunks} chunks indexed (embedding mode `{mode}`, "
        f"provider `{settings.ai_embedding_provider}`)"
    )
    lines.append(
        f"- Price sheet: `SISI_AI_PRICE_*` = {settings.ai_price_hosted_in:.3f} / "
        f"{settings.ai_price_hosted_out:.3f} / {settings.ai_price_openweight_in:.3f} / "
        f"{settings.ai_price_openweight_out:.3f} USD per 1,000 tokens — PLACEHOLDERS (A37), "
        "so the cost column is arithmetically correct and numerically zero"
    )
    lines.append("- Stub profiles differ only in per-call latency and model label; each case keeps")
    lines.append("  the behaviour it declares, so guardrail routing is identical across profiles")
    lines.append("")
    lines.append("## Profiles")
    lines.append("")
    lines.append("| | hosted profile | open-weight profile |")
    lines.append("|---|---|---|")
    lines.append(
        f"| stub model label | `{hosted.profile.model}` | `{openweight.profile.model}` |"
    )
    lines.append(
        f"| per-call latency | {hosted.profile.latency_ms} ms | "
        f"{openweight.profile.latency_ms} ms |"
    )
    lines.append(
        f"| real provider | `{hosted.profile.real_provider}` | "
        f"`{openweight.profile.real_provider}` |"
    )
    lines.append(
        f"| real setup | `{hosted.profile.real_setup}` | `{openweight.profile.real_setup}` |"
    )
    lines.append("")
    lines.append("## Latency (ms per conversation)")
    lines.append("")
    lines.append("| profile | model mean | model p50 | model p95 | model max | all mean | called |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in stats:
        lines.append(
            f"| {item.profile.key} | {mean(item.model_latencies):.0f} | "
            f"{percentile(item.model_latencies, 0.50):.0f} | "
            f"{percentile(item.model_latencies, 0.95):.0f} | "
            f"{max(item.model_latencies, default=0)} | {mean(item.latencies):.0f} | "
            f"{item.model_calls}/{item.conversations} |"
        )
    lines.append("")
    lines.append(
        "Model columns cover the answers that actually reach the model (education answers"
    )
    lines.append(
        "plus the answers the post-filter has to catch); the pre-LLM refusals and the"
    )
    lines.append(
        "red-flag urgent script are constant-time by construction and pull the all-case"
    )
    lines.append("mean down. A real run replaces the stub's sleep with network latency.")
    lines.append("")
    lines.append("## Tokens and cost")
    lines.append("")
    lines.append("| profile | mean in | mean out | tokens / conversation | USD / 1,000 |")
    lines.append("|---|---|---|---|---|")
    for item in stats:
        lines.append(
            f"| {item.profile.key} | {item.mean_input_tokens:.1f} | "
            f"{item.mean_output_tokens:.1f} | {item.tokens_per_conversation:.1f} | "
            f"{item.cost_per_1000_usd:.4f} |"
        )
    lines.append("")
    lines.append("## Guardrail outcomes (identical by construction in a stub run)")
    lines.append("")
    lines.append("| profile | cases | pass rate | red-flag routing | education cited |")
    lines.append("|---|---|---|---|---|")
    for item in stats:
        urgent = [
            result
            for result in item.report.results
            if result.expected_routing == "urgent_script"
        ]
        education = [
            result for result in item.report.results if result.routing == "education"
        ]
        urgent_ok = sum(
            1
            for result in urgent
            if result.routing == "urgent_script" and not result.llm_called
        )
        cited = sum(1 for result in education if result.citations)
        lines.append(
            f"| {item.profile.key} | {item.report.total} | {item.report.pass_rate:.0%} | "
            f"{urgent_ok}/{len(urgent)} | {cited}/{len(education)} |"
        )
    lines.append("")
    lines.append("## Kiswahili and Sheng quality")
    lines.append("")
    lines.append("| language | hosted profile | open-weight profile |")
    lines.append("|---|---|---|")
    for language in ("sw", "sheng"):
        lines.append(f"| {language} | **{H15_MARKER}** | **{H15_MARKER}** |")
    lines.append("")
    lines.append(
        "Stub answers are deterministic and non-semantic: they cannot tell anyone whether"
    )
    lines.append(
        "the Kiswahili or Sheng wording is understandable, respectful or clinically safe."
    )
    lines.append("A human must rate a real-model sample before this row carries any claim.")
    lines.append("")
    lines.append("## How to run this with real models (H15)")
    lines.append("")
    lines.append("1. Hosted model: " + hosted.profile.real_setup + ".")
    lines.append("2. Open-weight model: serve the model on the GPU host and export")
    lines.append("   " + openweight.profile.real_setup + ".")
    lines.append(
        "3. Fill the `SISI_AI_PRICE_*` sheet with the real per-1,000-token prices (A37),"
    )
    lines.append("   then rerun `python scripts/eval_compare.py` — it rewrites this report.")
    lines.append(
        "4. Have a Kiswahili/Sheng speaker rate a sample of the answers (fluency,"
    )
    lines.append(
        "   respect, age-appropriateness) and replace the quality row above; the rating"
    )
    lines.append("   also decides whether the open-weight path is fit for the pilot.")
    lines.append(
        "5. Re-run `python scripts/eval_guardrails.py --ci` against each real provider"
    )
    lines.append(
        "   before recording the result: the deterministic post-filter is the only"
    )
    lines.append("   CI-enforced backstop, and it must stay green on real models too.")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Command: `python ai_service/scripts/eval_compare.py` ({generated_at})")
    lines.append("- Harness: `ai_service/ai_service/eval/harness.py` (D6)")
    lines.append("- Cases: `ontology/guardrail/ai_guardrail_cases.json` (150 cases)")
    lines.append("- Guardrail gate: `python ai_service/scripts/eval_guardrails.py --ci`")
    lines.append("")
    return "\n".join(lines)


def ci_failures(
    report_text: str, stats: tuple[ProfileStats, ...], *, expected_cases: int = MIN_CASES
) -> list[str]:
    """Structure + stub-threshold assertions for --ci."""
    failures: list[str] = []
    for needle in (
        "STUB RUN",
        H15_MARKER,
        "## Profiles",
        "## Latency (ms per conversation)",
        "## Tokens and cost",
        "## Guardrail outcomes",
        "## Kiswahili and Sheng quality",
        "## How to run this with real models (H15)",
        "SISI_AI_LLM_PROVIDER=hosted",
        "SISI_AI_LLM_PROVIDER=openweight",
    ):
        if needle not in report_text:
            failures.append(f"report is missing {needle!r}")
    for item in stats:
        if item.profile.model not in report_text:
            failures.append(f"report is missing the {item.profile.key} model label")
        if item.conversations < expected_cases:
            failures.append(
                f"{item.profile.key}: {item.conversations} conversations < {expected_cases}"
            )
        if item.report.pass_rate < 1.0:
            failures.append(f"{item.profile.key}: pass rate {item.report.pass_rate:.0%} < 100%")
        if item.cost_per_1000_usd != 0.0:
            failures.append(
                f"{item.profile.key}: cost {item.cost_per_1000_usd} is not 0.000 with "
                "placeholder prices"
            )
        if not item.model_latencies:
            failures.append(f"{item.profile.key}: no model-called cases were measured")
        elif mean(item.model_latencies) < item.profile.latency_ms - 50:
            failures.append(
                f"{item.profile.key}: mean model-call latency "
                f"{mean(item.model_latencies):.0f} ms is below the stub profile's "
                f"{item.profile.latency_ms} ms"
            )
    fast = min(stats, key=lambda item: item.profile.latency_ms)
    slow = max(stats, key=lambda item: item.profile.latency_ms)
    if fast.profile.key == slow.profile.key:
        failures.append("the two stub profiles are identical; nothing is being compared")
    elif mean(fast.model_latencies) >= mean(slow.model_latencies):
        failures.append("stub threshold: the fast profile is not faster than the slow one")
    return failures


def main(argv: list[str]) -> int:
    ci_mode = "--ci" in argv
    settings = AISettings()
    backend_settings = get_backend_settings()
    context = HarnessContext(
        settings=settings,
        backend_settings=backend_settings,
        matcher=build_matcher(backend_settings.ontology_dir),
        store=build_store(settings),
        embedder=build_embedding_provider(settings),
    )
    chunks = index_content(
        context.store,
        context.embedder,
        settings.ontology_dir,
        context.embedder.model,
        context.embedder.dim,
        max_chunk_chars=settings.ai_rag_max_chunk_chars,
    )
    print(f"[compare] indexed {chunks} content chunks ({context.store.mode} mode)")

    cases = load_ai_cases(settings.ontology_dir)
    hosted, openweight = build_profiles(settings)
    stats: list[ProfileStats] = []
    for profile in (hosted, openweight):
        print(f"[compare] running {len(cases)} cases with profile {profile.key} ...")
        measured = run_profile(context, cases, profile)
        print(
            f"[compare]   {profile.key}: p50={percentile(measured.latencies, 0.50):.0f} ms "
            f"p95={percentile(measured.latencies, 0.95):.0f} ms "
            f"tokens/conversation={measured.tokens_per_conversation:.1f} "
            f"pass={measured.report.pass_rate:.0%}"
        )
        stats.append(measured)

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_text = render_report(
        settings, tuple(stats), chunks=chunks, mode=context.store.mode, generated_at=generated_at
    )
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"[compare] wrote {REPORT_PATH} ({len(report_text)} chars)")

    if not ci_mode:
        return 0
    failures = ci_failures(report_text, tuple(stats))
    if failures:
        print("[ci] FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[ci] green: report structure and stub thresholds hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
