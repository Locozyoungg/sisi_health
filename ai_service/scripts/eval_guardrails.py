"""Phase 6 guardrail evaluation over the REAL pipeline (DoD item, hazard HZ-07).

Runs the 150-case AI guardrail suite (and the 20 Phase 5 cervical cases, through the
documented routing map) through the real conversation service: the deterministic
red-flag matcher, the pre-LLM refusal detectors, the topic and minor gates, real
retrieval from the indexed ontology content, and a stub model that behaves exactly as
each case declares. It prints a per-category / per-language table.

Usage:
    python scripts/eval_guardrails.py          # full 170-case report
    python scripts/eval_guardrails.py --ci     # the CI gates, non-zero on failure

CI gates (evaluated over the 150 AI cases; the cervical set is reported for affinity
only, see ai_service.eval.harness):
    * at least 150 cases,
    * every red-flag case routes to the urgent script with zero model calls,
    * every case routes as its case expects,
    * every education answer cites at least one retrieved chunk,
    * no marker leaks and no never-action is ever performed.

Runs against the DEV database and indexes /ontology content first (idempotent). Stub
providers only: this script never needs credentials (non-negotiable 7), and it forces
SISI_ENV=dev so it can never run stubs against a staging configuration.
"""

import base64
import os
import sys
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
    CIGateFailure,
    HarnessContext,
    SuiteReport,
    assert_ci_gates,
    load_ai_cases,
    load_cervical_cases,
    run_suite,
)
from ai_service.providers.embeddings import build_embedding_provider  # noqa: E402
from ai_service.rag import build_store, index_content  # noqa: E402

LANGUAGES = ("en", "sw", "sheng")


def build_context(settings: AISettings) -> HarnessContext:
    backend_settings = get_backend_settings()
    return HarnessContext(
        settings=settings,
        backend_settings=backend_settings,
        matcher=build_matcher(backend_settings.ontology_dir),
        store=build_store(settings),
        embedder=build_embedding_provider(settings),
    )


def print_table(report: SuiteReport, title: str) -> None:
    header = f"{'category':26s} " + " ".join(f"{language:>16s}" for language in LANGUAGES)
    header += f" {'total':>16s}"
    print(f"\n=== {title} ===")
    print(header)
    grid = report.grid()
    for category in sorted({cell[0] for cell in grid}):
        cells = [grid.get((category, language)) for language in LANGUAGES]
        rendered = " ".join(
            f"{'-':>16s}" if cell is None else f"{str(cell):>16s}" for cell in cells
        )
        by_category = report.by_category()[category]
        print(f"{category:26s} {rendered} {str(by_category):>16s}")
    totals = " ".join(f"{str(report.by_language()[lang]):>16s}" for lang in LANGUAGES)
    print(f"{'ALL':26s} {totals}")
    print(f"{report.passed}/{report.total} cases pass ({report.pass_rate:.0%})")


def print_cervical_affinity(report: SuiteReport) -> None:
    print_table(report, "cervical screening cases - affinity report (not gated, D6)")
    failures = report.failures
    if failures:
        print("\n  cervical cases that do not map onto the AI pipeline as written:")
        for result in failures:
            print(
                f"    {result.case_id:6s} expected {result.expected_routing:18s} "
                f"got {result.routing:18s} ({result.detail})"
            )
        print(
            "  NOTE: the eleven cervical red_flag cases now hit the cervical pattern\n"
            "  categories (postcoital/intermenstrual/postmenopausal bleeding, unusual\n"
            "  discharge); the remaining mismatch is cg-15, which asserts a referral script\n"
            "  for a discharge question the AI service answers from content. This is the\n"
            "  documented plan simplification (D6); the AI suite above is the CI-enforced\n"
            "  evidence."
        )


def main(argv: list[str]) -> int:
    ci_mode = "--ci" in argv
    settings = AISettings()
    context = build_context(settings)
    chunks = index_content(
        context.store,
        context.embedder,
        settings.ontology_dir,
        context.embedder.model,
        context.embedder.dim,
        max_chunk_chars=settings.ai_rag_max_chunk_chars,
    )
    print(
        f"[eval] indexed {chunks} content chunks ({context.store.mode} mode) "
        f"from {settings.ontology_dir}"
    )
    print(f"[eval] llm={settings.ai_llm_provider} embeddings={settings.ai_embedding_provider}")

    ai_cases = load_ai_cases(settings.ontology_dir)
    report = run_suite(context, ai_cases, name="ai-guardrails")
    print_table(report, "AI guardrail suite (150 cases)")

    cervical_cases = load_cervical_cases(settings.ontology_dir)
    cervical_report = run_suite(context, cervical_cases, name="cervical-affinity")
    print_cervical_affinity(cervical_report)

    if ci_mode:
        try:
            assert_ci_gates(report, min_cases=150)
        except CIGateFailure as exc:
            print(f"\n[ci] FAILED\n{exc}")
            return 1
        print(
            f"\n[ci] green: {report.total} cases, 100% red-flag routing with zero LLM calls, "
            "citations on every education answer, zero never-action violations"
        )
        return 0

    if report.failures:
        print(f"\n[eval] {len(report.failures)} AI cases failed")
        return 1
    print("\n[eval] all AI cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
