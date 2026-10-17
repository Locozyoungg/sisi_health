# USSD load test report

Measured run: 2026-10-17 04:25 UTC against the local dev stack (gateway on
`http://127.0.0.1:8001`, one uvicorn process, dev Postgres). Synthetic phones
and answers only — no patient data and no real phone numbers.

## Result summary

| Metric | Measured |
|---|---|
| Concurrent journeys requested | 1,000 |
| Client TCP pool | 200 connections |
| Total HTTP requests | 6,938 |
| Wall-clock duration | 1295.72 s |
| Throughput | 5.4 req/s |
| p50 latency | 43820.0 ms |
| p95 latency | 391382.7 ms |
| p99 latency | 669046.1 ms |
| Mean latency | 101103.2 ms |
| Slowest request | 905254.4 ms |
| Request errors | 637 (9.18%) |
| Status codes | HTTP 200: 6938 |
| Journeys completed | 363 / 1,000 (36.30%) |
| Result bands | GREEN: 263, ORANGE: 12, RED: 88 |
| Session backend | postgres (forced by SISI_USSD_SESSION_BACKEND=postgres) |

## What the local stack sustained

The run above is the honest measurement on one laptop-class machine with a
single uvicorn process. The gateway endpoint is a synchronous FastAPI handler,
so it executes in the anyio threadpool (default ~40 worker threads) while
1,000 client journeys are in flight. Session backend for this run:
**postgres (forced by SISI_USSD_SESSION_BACKEND=postgres)**.

Every request that reached the gateway answered HTTP 200: there were no server
5xx responses and no tracebacks in the gateway log. The failures are therefore
saturation effects, not flow defects:

- `ConnectTimeout` / `ReadError` — the client's connection pool and the OS
  accept path could not keep 1,000 journeys moving; requests waited far longer
  than the client timeout permitted.
- `expected ... at step N` — at these queue depths more than five minutes
  elapsed between two callbacks of the same journey, so the spec-mandated
  300-second USSD session TTL expired and the journey restarted at the welcome
  screen. Under normal carrier latency this does not happen; it is a symptom of
  driving far more concurrency than one process can serve.

The measured ceiling for this single process is **~9–10 requests/second**. The
cause is CPU in the handler, not the database: `get_flow_engine()` rebuilds the
rule engine (loads and JSON-Schema-validates the 12 rule files plus pydantic
models) and constructs the session store on every request. In isolation that
rebuild measures ~56 ms per callback, so one GIL-bound process cannot exceed
roughly 18 req/s even with zero I/O.

Supplementary runs on the same stack (all completed with 0 request errors and
100% journey completion, so these are the clean sustained-envelope figures):

| Run | Journeys | TCP pool | Throughput | p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| Postgres session store | 20 | 10 | 10.2 req/s | 930 ms | 6.7 s | 14.2 s |
| Postgres session store | 100 | 20 | 9.6 req/s | 5.1 s | 27.7 s | 42.1 s |
| Redis session store | 20 | 10 | 8.6 req/s | 1.2 s | 7.4 s | 12.5 s |

The Redis run is statistically indistinguishable from the Postgres run at this
scale: removing the session DB calls does not lift the ceiling because the
rule-engine rebuild dominates. Redis is still the correct production store (see
below), but the gateway also needs the engine cached per process before it can
approach the 1,000-concurrent target.

Environment note: a Redis listener was reachable on this machine, but the
gateway was started with `SISI_USSD_SESSION_BACKEND=postgres` for the primary
run so the documented A19 fallback is what was measured. The primary run used
port 8001; the Redis comparison used a second gateway process on port 8002 with
`SISI_USSD_SESSION_BACKEND=redis`.

Interpretation: the 363 completed journeys prove the full protocol end to end
(session state, deterministic assessment, envelope sealing, audit write). The
measurement does **not** show the local single-process stack sustaining 1,000
true-parallel journeys — it sustains roughly 9–10 req/s (about 20–100 in-flight
journeys depending on latency tolerance) and degrades into queueing beyond
that. This is a single-node functional-load result, not a capacity quote, and
it does not model carrier latency or multiple gateway replicas.

Observed errors (all client-side or session-TTL expiry; every request that was
sent returned HTTP 200):

- `ConnectTimeout: ` — 317 journey(s)
- `ReadError: ` — 156 journey(s)
- `step 3: expected 'On a scale of 0 to 10' at step 3` — 69 journey(s)
- `step 1: expected 'How old are you' at step 1` — 64 journey(s)
- `step 2: expected 'SISI keeps your answers' at step 2` — 11 journey(s)

## Appendix: first 1,000-journey attempt (1,000 client sockets)

An earlier attempt opened one TCP connection per journey (1,000 client
sockets, 120-second timeout). It measured 8.1 req/s over 879 s with 324/1,000
journeys completed (32.4%) and 676 errors: 422 ConnectTimeout, 138 ConnectError
("all connection attempts failed"), 110 ReadError, 5 RemoteProtocolError, and
one state drift. p50/p95/p99 were 43.7 s / 191.4 s / 341.4 s. The error mix is
dominated by the client-side connection storm (Windows ephemeral ports and the
accept backlog), which is why the reported run uses a 200-connection pool
instead — still 1,000 concurrent journeys, but a sane socket count.

## Full-scale procedure

Use staging (never production) with the same image tags as the release:

1. Provision Redis and set `SISI_USSD_SESSION_BACKEND=redis` on the gateway
   (the Postgres fallback stays dev-only). Give Redis a 5-minute session TTL
   (`SISI_USSD_SESSION_TTL_SECONDS=300`) and disable persistence for session
   keys — they are ephemeral by design.
2. Run the gateway with more than one worker/process and keep the Caddy TLS
   terminator in front. Size Postgres connections to `workers × pool` and
   monitor `pg_stat_activity`; the session store must not be on the DB hot path.
3. Drive load from a separate host (the generator competes with the gateway for
   CPU otherwise). Point `--base-url` at staging and run one generator process
   per CPU core, each with `--concurrency 250`, to reach 1,000 in-flight
   journeys without a single Python client becoming the bottleneck.
4. Ramp 100 -> 500 -> 1,000 concurrent journeys, holding each for 10 minutes.
   Acceptance gates: 0 request errors, 100% journey completion, p95 < 2 s,
   p99 < 5 s; no Postgres connection-pool exhaustion; Redis p99 < 5 ms.
5. Repeat at the pilot target of 1,000 concurrent students during a school-day
   peak, and replace this report with the measured numbers.
6. Run the same script against the production canary only with synthetic
   numbers and a maintenance window approved by the maintainer.

## Redis recommendation

**Use Redis for USSD session state in staging and production — it is already
the spec decision (spec 2); the Postgres path exists only for dev (A19).**
The fallback turns every one of the ~14 callbacks per journey into a database
read plus a database upsert, which (a) puts a latency spike on shared DB
capacity also used for assessment sealing and audit writes, (b) makes the DB
pool a throughput ceiling under concurrency, and (c) leaves expired
`core.ussd_sessions` rows on disk until they are read again (a 5-minute TTL is
not a deletion schedule). Redis is the right store for short-lived,
key-by-phone-hash session state: native TTL, no table bloat, and no database on
the callback hot path.

The measurements above also show Redis is necessary but not sufficient: at
20-journey load the Redis-backed gateway (8.6 req/s) is no faster than the
Postgres-backed one (10.2 req/s) because the per-request rule-engine rebuild
dominates. **Before the pilot gate, cache the rule engine (and the chosen
session store) once per gateway process** — that is a code change outside this
phase's scope, but without it each additional worker buys only ~10 req/s and
the 1,000-concurrent target is out of reach.
