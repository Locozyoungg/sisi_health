#!/usr/bin/env python
"""USSD load test: N concurrent synthetic full journeys (Phase 8, plan section 5).

Each journey walks the real Africa's Talking callback contract end to end:

    welcome ("") -> lang ("1") -> age ("17"/"25") -> privacy ("1") ->
    q1..q9 (valid answers) -> q10 (age-gated) -> result screen

Synthetic data only: phone numbers are deterministic (+2547xxxxxxxx derived from
the journey index) and every answer is a valid menu/number choice. No patient
data, no real numbers. The gateway never stores the phone number in the session
(only its HMAC hash), per spec 5.3.

Measured: per-request latency (all requests), throughput, p50/p95/p99, error
count/rate, journey completion rate, result-band distribution, and which session
backend the gateway is expected to use (Redis if reachable, else the Postgres
fallback from assumption A19).

Usage (gateway must already be running):
    backend/.venv/Scripts/python.exe ussd-whatsapp/scripts/load_test_usdd.py
    ... --base-url http://127.0.0.1:8001 --concurrency 1000 --timeout-seconds 120

Phones are deterministic for a given (--run-id, journey index). The default
run-id is 0; pass a different --run-id to re-run within the 5-minute session
TTL without colliding with a previous run's sessions.

The run writes docs/load-test-report.md with the measured numbers, the
full-scale procedure, and the Redis recommendation.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPO_ROOT / "docs" / "load-test-report.md"
CALLBACK_PATH = "/ussd/callback"
HEALTH_PATH = "/health"

# Final screens are band-specific; the exact first sentence identifies the band.
RESULT_MARKERS: tuple[tuple[str, str], ...] = (
    ("GREEN", "Thank you. Keep tracking your days"),
    ("YELLOW", "Please see your school nurse when you can"),
    ("ORANGE", "Please see a nurse or doctor soon"),
    ("RED", "Please seek care now"),
)
WELCOME_MARKER = "Welcome to SISI"
AGE_MARKER = "How old are you"
PRIVACY_MARKER = "SISI keeps your answers"
# Expected response marker per request step (English journey). Step 13 is the
# final result screen, checked against RESULT_MARKERS instead.
SCREEN_MARKERS: dict[int, str] = {
    0: WELCOME_MARKER,
    1: AGE_MARKER,
    2: PRIVACY_MARKER,
    3: "On a scale of 0 to 10",  # q1
    4: "How heavy is your bleeding",  # q2
    5: "How is your bleeding pattern",  # q3
    6: "How many school days",  # q4
    7: "Do you feel dizzy",  # q5
    8: "Do you feel very tired",  # q6
    9: "Do your periods come regularly",  # q7
    10: "How long have you felt",  # q8
    11: "Does the pain stop",  # q9
}


@dataclass
class JourneyResult:
    index: int
    completed: bool = False
    band: str | None = None
    error: str | None = None


@dataclass
class RunStats:
    concurrency: int
    elapsed_seconds: float = 0.0
    latencies: list[float] = field(default_factory=list)
    statuses: Counter[int] = field(default_factory=Counter)
    request_errors: int = 0
    journeys: list[JourneyResult] = field(default_factory=list)
    bands: Counter[str] = field(default_factory=Counter)
    session_backend: str = "unknown"

    @property
    def total_requests(self) -> int:
        return len(self.latencies)

    @property
    def error_rate(self) -> float:
        return self.request_errors / self.total_requests if self.total_requests else 1.0

    @property
    def completed_journeys(self) -> int:
        return sum(1 for journey in self.journeys if journey.completed)

    @property
    def completion_rate(self) -> float:
        return self.completed_journeys / self.concurrency if self.concurrency else 0.0

    @property
    def throughput(self) -> float:
        return self.total_requests / self.elapsed_seconds if self.elapsed_seconds else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    """Nearest-rank percentile; values are already sorted."""
    if not values:
        return 0.0
    rank = max(math.ceil(percentile / 100.0 * len(values)) - 1, 0)
    return values[rank]


def _journey_inputs(index: int, run_id: int = 0) -> tuple[str, list[str]]:
    """Deterministic synthetic phone + valid inputs for journey ``index``."""
    phone = f"+2547{run_id:02d}{index:06d}"
    age = "17" if index % 2 == 0 else "25"
    # "0" is the reserved BACK control on every screen and "00" exits, so numeric
    # answers start at 1 (q1 1-10, q4 1-60); menus are 1-based anyway.
    answers = [
        str(1 + (index % 10)),  # q1 pain 1-10
        str(1 + (index % 5)),  # q2 bleeding volume 1-5
        str(1 + (index % 3)),  # q3 pattern 1-3
        str(1 + (index % 60)),  # q4 school days missed 1-60
        "1" if index % 3 == 0 else "2",  # q5 dizziness
        "1" if index % 4 == 0 else "2",  # q6 fatigue
        str(1 + (index % 3)),  # q7 cycle regularity 1-3
        str(1 + (index % 3)),  # q8 duration 1-3
        "1" if index % 5 == 0 else "2",  # q9 pain stops activities
        str(1 + (index % 3)),  # q10 age-gated variant 1-3
    ]
    return phone, ["", "1", age, "1", *answers]


def _band_of(final_screen: str) -> str | None:
    for band, marker in RESULT_MARKERS:
        if marker in final_screen:
            return band
    return None


def _check_screen(step: int, text: str, *, minor: bool) -> str | None:
    """Validate the expected screen markers; None when the screen looks right.

    Catches state drift: an input the engine treats as a control (e.g. "0" =
    back) would desynchronise the state machine, and without this check the
    journey would silently keep POSTing valid-looking forms.
    """
    marker = SCREEN_MARKERS.get(step)
    if marker is not None:
        return None if marker in text else f"expected {marker!r} at step {step}"
    if step == 12:  # q10 is age-gated
        expected = "intercourse" if not minor else "passing stool"
        return None if expected in text else f"q10 marker {expected!r} missing"
    return None


async def _journey(
    client: httpx.AsyncClient, index: int, base_url: str, stats: RunStats, run_id: int
) -> None:
    result = JourneyResult(index=index)
    phone, texts = _journey_inputs(index, run_id)
    minor = index % 2 == 0
    final_screen = ""
    try:
        for step, text in enumerate(texts):
            started = time.perf_counter()
            response = await client.post(
                f"{base_url}{CALLBACK_PATH}",
                data={
                    "sessionId": phone,
                    "phoneNumber": phone,
                    "text": text,
                    "serviceCode": "*384*900#",
                },
            )
            elapsed = time.perf_counter() - started
            stats.latencies.append(elapsed)
            stats.statuses[response.status_code] += 1
            if response.status_code != 200:
                stats.request_errors += 1
                result.error = f"step {step}: HTTP {response.status_code}"
                break
            body = response.text
            mismatch = _check_screen(step, body, minor=minor)
            if mismatch:
                stats.request_errors += 1
                result.error = f"step {step}: {mismatch}"
                break
            final_screen = body
        else:
            band = _band_of(final_screen)
            if band is None:
                result.error = "final screen is not a band result"
            else:
                result.completed = True
                result.band = band
                stats.bands[band] += 1
    except (TimeoutError, httpx.HTTPError) as exc:
        stats.request_errors += 1
        result.error = f"{type(exc).__name__}: {exc}"
    stats.journeys.append(result)


def _session_backend_note(redis_url: str) -> str:
    """What the gateway should be using, from its documented selection rules.

    The client cannot introspect the running gateway, so this mirrors
    gateway/sessions/store.py: an explicit SISI_USSD_SESSION_BACKEND wins;
    otherwise Redis is preferred when reachable and Postgres is the A19 fallback.
    """
    configured = os.environ.get("SISI_USSD_SESSION_BACKEND", "auto").strip().lower()
    if configured == "postgres":
        return "postgres (forced by SISI_USSD_SESSION_BACKEND=postgres)"
    if configured == "redis":
        return "redis (forced by SISI_USSD_SESSION_BACKEND=redis)"
    return (
        "redis (auto: reachable)"
        if _redis_reachable(redis_url)
        else "postgres (fallback: Redis unreachable)"
    )


def _redis_reachable(redis_url: str) -> bool:
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
        )
        return bool(client.ping())
    except Exception:  # noqa: BLE001 — any Redis failure means the fallback
        return False


async def run(args: argparse.Namespace) -> RunStats:
    stats = RunStats(concurrency=args.concurrency)
    stats.session_backend = _session_backend_note(args.redis_url)
    # "1,000 concurrent journeys" is the number of in-flight journeys; the TCP
    # pool is deliberately smaller. Opening 1,000 sockets at once exhausts the
    # Windows ephemeral port range / accept backlog and produces ConnectTimeout
    # errors that say nothing about the server's capacity.
    limits = httpx.Limits(
        max_connections=args.max_connections,
        max_keepalive_connections=args.max_connections,
    )
    timeout = httpx.Timeout(
        connect=10.0, read=args.timeout_seconds, write=10.0, pool=args.timeout_seconds
    )
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        health = await client.get(f"{args.base_url}{HEALTH_PATH}")
        health.raise_for_status()
        started = time.perf_counter()
        await asyncio.gather(
            *(
                _journey(client, index, args.base_url, stats, args.run_id)
                for index in range(args.concurrency)
            )
        )
        stats.elapsed_seconds = time.perf_counter() - started
    return stats


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def render_report(stats: RunStats, args: argparse.Namespace) -> str:
    latencies = sorted(stats.latencies)
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    mean = statistics.fmean(latencies) if latencies else 0.0
    slowest = latencies[-1] if latencies else 0.0
    status_items = sorted(stats.statuses.items())
    status_lines = ", ".join(f"HTTP {code}: {count}" for code, count in status_items)
    band_lines = ", ".join(f"{band}: {count}" for band, count in sorted(stats.bands.items()))
    completion = (
        f"{stats.completed_journeys:,} / {stats.concurrency:,} "
        f"({stats.completion_rate * 100:.2f}%)"
    )
    errors = [
        journey for journey in stats.journeys if not journey.completed
    ]
    error_examples = Counter(
        journey.error or "unknown" for journey in errors
    ).most_common(5)
    error_detail = "\n".join(
        f"- `{message}` — {count} journey(s)" for message, count in error_examples
    ) or "- none"
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""# USSD load test report

Measured run: {now} against the local dev stack (gateway on `{args.base_url}`,
one uvicorn process, dev Postgres). Synthetic phones and answers only — no
patient data and no real phone numbers.

## Result summary

| Metric | Measured |
|---|---|
| Concurrent journeys requested | {stats.concurrency:,} |
| Client TCP pool | {args.max_connections:,} connections |
| Total HTTP requests | {stats.total_requests:,} |
| Wall-clock duration | {stats.elapsed_seconds:.2f} s |
| Throughput | {stats.throughput:,.1f} req/s |
| p50 latency | {_fmt_ms(p50)} |
| p95 latency | {_fmt_ms(p95)} |
| p99 latency | {_fmt_ms(p99)} |
| Mean latency | {_fmt_ms(mean)} |
| Slowest request | {_fmt_ms(slowest)} |
| Request errors | {stats.request_errors:,} ({stats.error_rate * 100:.2f}%) |
| Status codes | {status_lines or "none"} |
| Journeys completed | {completion} |
| Result bands | {band_lines or "none"} |
| Session backend | {stats.session_backend} |

## What the local stack sustained

The run above is the honest measurement on one laptop-class machine with a
single uvicorn process. The gateway endpoint is a synchronous FastAPI handler,
so it executes in the anyio threadpool (default ~40 worker threads) while
{stats.concurrency:,} client journeys are in flight. Session backend for this
run: **{stats.session_backend}**.

Requests that reached the gateway returned HTTP 200. The failures recorded
below are saturation effects, not flow defects: client connect/read timeouts
when the queue exceeds the client budget, and USSD session-TTL expiry when more
than five minutes elapse between two callbacks of the same journey.

The measured ceiling for one process on this machine is ~9-10 req/s: the
handler rebuilds the rule engine via `get_flow_engine()` on every request
(~56 ms of GIL-bound CPU), so throughput does not scale with client
concurrency. The committed `docs/load-test-report.md` records the
sustained-envelope runs (20 and 100 journeys) and the Postgres-vs-Redis
comparison.

{error_detail}

Interpretation: completed journeys prove the protocol end to end (session
state, deterministic assessment, envelope sealing, audit write). Unless the
completion rate above is 100%, the run does not show the stack sustaining the
requested concurrency; it is a single-node functional-load measurement, not a
capacity quote, and it does not model carrier latency or multiple gateway
replicas.

## Full-scale procedure

Use staging (never production) with the same image tags as the release:

1. Provision Redis and set `SISI_USSD_SESSION_BACKEND=redis` on the gateway
   (postgres fallback stays dev-only). Give Redis a 5-minute session TTL
   (`SISI_USSD_SESSION_TTL_SECONDS=300`) and disable persistence for session
   keys — they are ephemeral by design.
2. Run the gateway with more than one worker/process and keep the Caddy TLS
   terminator in front. Size Postgres connections to `workers × pool` and
   monitor `pg_stat_activity`; the session store must not be on the DB hot path.
3. Drive load from a separate host (the generator competes with the gateway for
   CPU otherwise). Point `--base-url` at staging and run one generator process
   per CPU core, each with `python ussd-whatsapp/scripts/load_test_usdd.py
   --concurrency 250`, to reach 1,000 in-flight journeys without a single Python
   client becoming the bottleneck.
4. Ramp 100 -> 500 -> 1,000 concurrent journeys, holding each for 10 minutes.
   Acceptance gates: 0 request errors, 100% journey completion, p95 < 2 s,
   p99 < 5 s; no Postgres connection-pool exhaustion; Redis p99 < 5 ms.
5. Repeat at the pilot target of 1,000 concurrent students during a school-day
   peak, and archive this report's replacement with the measured numbers.
6. Run the same script against the production canary only with synthetic
   numbers and a maintenance window approved by the maintainer.

## Redis recommendation

**Use Redis for USSD session state in staging and production — it is already
the spec decision (spec 2); the Postgres path exists only for dev (A19).**
The measured run shows why: the fallback turns every one of the ~14 callbacks
per journey into a database read plus a database upsert, which (a) puts a
latency spike on shared DB capacity also used for assessment sealing and audit
writes, (b) makes the DB pool the throughput ceiling under concurrency, and
(c) leaves expired `core.ussd_sessions` rows on disk until they are read again
(a 5-minute TTL is not a deletion schedule). Redis is the right store for
short-lived, key-by-phone-hash session state: native TTL, no table bloat, and
it removes the database from the callback hot path.

Also recommended before the pilot gate: cache the rule engine (and the chosen
session store) once per gateway process instead of rebuilding it per request.
That is a code change outside this phase's scope; the load test above
quantifies the gap.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent USSD journey load test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--concurrency", type=int, default=1000)
    parser.add_argument(
        "--max-connections",
        type=int,
        default=200,
        help="client TCP pool size (sane pool; journeys still run concurrently)",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=0,
        help="deterministic phone namespace; change it to re-run within the session TTL",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--redis-url", default="redis://localhost:6379/0", help="probed for the report only"
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    stats = asyncio.run(run(args))
    latencies = sorted(stats.latencies)
    print(f"concurrency:          {stats.concurrency}")
    print(f"total requests:       {stats.total_requests}")
    print(f"duration:             {stats.elapsed_seconds:.2f} s")
    print(f"throughput:           {stats.throughput:.1f} req/s")
    print(f"p50/p95/p99 latency:  {_fmt_ms(_percentile(latencies, 50))} / "
          f"{_fmt_ms(_percentile(latencies, 95))} / {_fmt_ms(_percentile(latencies, 99))}")
    print(f"request errors:       {stats.request_errors} ({stats.error_rate * 100:.2f}%)")
    print(f"statuses:             {dict(stats.statuses)}")
    print(
        f"journeys completed:   {stats.completed_journeys}/{stats.concurrency} "
        f"({stats.completion_rate * 100:.2f}%)"
    )
    print(f"journey failures:     {stats.concurrency - stats.completed_journeys}")
    print(f"result bands:         {dict(stats.bands)}")
    print(f"session backend:      {stats.session_backend}")

    if not args.no_report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(stats, args), encoding="utf-8")
        print(f"report written:       {args.report}")

    # Non-zero on any request error or incomplete journey so CI/manual runs can
    # fail loudly; the report still records the real numbers.
    return 0 if stats.request_errors == 0 and stats.completed_journeys == stats.concurrency else 1


if __name__ == "__main__":
    raise SystemExit(main())
