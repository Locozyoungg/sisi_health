# Pilot Cost Model

> ## ⚠️ EVERY FIGURE IN THIS MODEL IS A PLACEHOLDER OR AN ESTIMATE
>
> **No price in this document is a quote, and none may be presented as real.**
> The numbers are deliberately round, illustrative values chosen so the
> arithmetic is checkable; they exist to show *what* has to be priced and *how*
> the per-student cost is derived. Substituting real quotes changes the
> `unit_price_usd` column and nothing else.
>
> This is recorded as assumption **A40** in `/docs/assumptions.md`. Confirming
> the quotes is human task **H2** (Africa's Talking, USSD/SMS), **H3**
> (Daraja), **H4** (WhatsApp), **H15** (LLM/embedding), and **H17** (VPS
> provisioning and hosting). Until then, no budget, grant narrative, or
> investor deck may cite these numbers as costs.

**Companion file:** [`cost-model.csv`](./cost-model.csv) — spreadsheet-ready,
same rows, one row per cost line with a `price_status` and
`price_source_to_confirm` column. Open it in any spreadsheet; the columns are
plain numbers so the totals recompute when real quotes are pasted in.

## 1. What the model covers

A single-VPS pilot deployment (spec §2 "Deploy": Docker Compose on one VPS,
Caddy for TLS 1.3), serving the school channel (USSD + WhatsApp), the app
channel, the staff consoles, and the AI education layer. Modelled at two
scales: **1,000 students** and **10,000 students**.

Not modelled (deliberately out of scope for a first pilot budget):
Play Store fees, staff salaries and nurse time, clinician review time, the
third-party penetration test (H8), legal fees, the ethics-approved validation
study (H11), and Jitsi hosting if a provider API is used instead of
self-hosting (H12).

## 2. Volume assumptions (also placeholders)

| Ref | Assumption | Value | Why |
|---|---|---|---|
| V1 | Assessments per student per term | 1 | baseline + follow-up sweeps are separate terms |
| V2 | Months per term | 3 | three terms a year |
| V3 | Share of assessments on USSD | 70% | feature-phone reach is the school channel's point |
| V4 | USSD sessions per completed assessment | 1.4 | abandons and 5-minute resume restarts |
| V5 | Share of assessments on WhatsApp | 30% | smartphone share among pupils and staff |
| V6 | WhatsApp messages per journey | 6 | prompt + 10 answers + result summary |
| V7 | Share of students asking ≥1 AI question per month | 15% | education layer, opt-in by asking |
| V8 | AI questions per asking student | 1 | one conversation per month |
| V9 | Backup size per 1,000 students | 20 GB | **estimate** — measure after the first real term |
| V10 | Backups retained | 30 days | nightly encrypted dumps (retention config) |

Derived quantities at each scale (as in the CSV):

```
assessments/month   = students / V2                →   333  at 1,000 students   |  3,333  at 10,000
USSD sessions/month = assessments × V3 × V4        →   326                    |  3,266
WhatsApp messages   = assessments × V5 × V6        →   599                    |  5,994
AI conversations    = students × V7 × V8 / 1000    →   0.15 (thousand)        |  1.5 (thousand)
```

## 3. The cost lines

| Row | Line | Unit | Unit price (USD) | Status | Source to confirm |
|---|---|---|---|---|---|
| INF-01 | VPS: application + gateway + AI service + Postgres + Caddy | instance-month | 45.00 | PLACEHOLDER | hosting provider quote (H17) |
| INF-02 | Separate database host (10k only) | instance-month | 60.00 | PLACEHOLDER | H17 |
| INF-03 | Encrypted backup storage, 30-day retention | GB-month | 0.023 | PLACEHOLDER | H17 |
| MSG-01 | SMS summary per completed assessment | message | 0.0080 | PLACEHOLDER | Africa's Talking Kenya price list (H2) |
| MSG-02 | USSD session (full journey) | session | 0.0130 | PLACEHOLDER | Africa's Talking / aggregator (H2) |
| MSG-03 | WhatsApp business messages | message | 0.0050 | PLACEHOLDER | BSP / Meta conversation pricing (H4) |
| AI-01 | LLM per 1,000 conversations | 1,000 conversations | **0.00** | PLACEHOLDER — zero until H15 | `SISI_AI_PRICE_HOSTED_IN/OUT`, `SISI_AI_PRICE_OPENWEIGHT_IN/OUT` are 0.0 (assumption A37) |
| AI-02 | Open-weight inference host (GPU), if the vLLM path is deployed | instance-month | 250.00 | PLACEHOLDER | GPU host quote (H15) |
| OPS-01 | USSD shortcode rental / aggregator monthly fee | month | 100.00 | PLACEHOLDER | H2 |
| OPS-02 | Domain + TLS + uptime monitoring | month | 15.00 | PLACEHOLDER | H17 |
| OPS-03 | M-Pesa (Daraja) fees on voucher funding | transaction | 0.00 | PLACEHOLDER | Safaricom tariffs (H3); charge-bearer undecided |

**AI-01 is genuinely zero today**, and that is not an oversight: the eval
harness computes cost per 1,000 conversations from
`SISI_AI_PRICE_*`, which ship as `0.0` placeholders; the comparison report is a
STUB RUN until H15 supplies real provider pricing. The moment a real price is
entered, row AI-01 becomes the largest variable line in the model.

Rows **AI-01 and AI-02 are alternatives**, not additive: deploy either the
hosted API or the open-weight GPU host at pilot scale (spec §2 permits both,
the pilot budget should fund one).

## 4. Monthly cost at each scale

| Row | At 1,000 students | At 10,000 students |
|---|---|---|
| INF-01 VPS | 45.00 | 90.00 |
| INF-02 database host | 0.00 | 60.00 |
| INF-03 backups | 0.69 | 4.60 |
| MSG-01 SMS | 2.66 | 26.66 |
| MSG-02 USSD | 4.24 | 42.46 |
| MSG-03 WhatsApp | 3.00 | 29.97 |
| AI-01 LLM | 0.00 | 0.00 |
| AI-02 GPU host (alternative, included in the 10k column) | 0.00 | 250.00 |
| OPS-01 shortcode | 100.00 | 100.00 |
| OPS-02 domain/TLS/monitoring | 15.00 | 25.00 |
| OPS-03 Daraja | 0.00 | 0.00 |
| **Monthly total** | **170.59** | **628.69** |
| **Per student per month** | **0.17** | **0.06** |
| **Per student per year (×12)** | **2.05** | **0.75** |

With the hosted LLM path instead of the GPU host, the 10,000-student column
would be 628.69 − 250.00 = **378.69**/month (0.04 per student per month) before
real LLM pricing is added.

## 5. What the model shows (and what it does not)

**Shows.** Fixed platform costs dominate at small scale: at 1,000 students,
about 92% of the monthly total is fixed (VPS, shortcode, monitoring), so the
per-student cost falls roughly 3× when the pilot grows tenfold. Channel costs
(SMS/USSD/WhatsApp) are small at these volumes but scale linearly, so they
matter most in a nationwide rollout.

**Does not show.** It is not a price list, not a grant budget, and not evidence
of affordability. The one number that could change the picture by an order of
magnitude is real LLM pricing (AI-01), which is unmeasured by design until H15.

### Sensitivity — the three lines that matter

| Line | If it doubles | Effect at 10,000 students |
|---|---|---|
| AI-01 LLM | pending H15 | unknown until real pricing is entered |
| MSG-01/02 messaging | unit prices ×2 | +69.12/month (+11%) |
| INF-01/02 hosting | instance class ×2 | +150.00/month (+24%) |

## 6. How to replace the placeholders

1. Obtain the quotes listed in `price_source_to_confirm` (H2, H3, H4, H15, H17).
2. Paste them into the `unit_price_usd` column of `cost-model.csv`; recompute
   `monthly_cost_usd_at_*` as `quantity × unit_price`.
3. Update the volume assumptions (§2) from the pilot's measured first term —
   V9 (backup size) in particular is a pure estimate.
4. Re-run the totals, update §4 of this document, and note the change here.

| Date | Change | By |
|---|---|---|
| 2026-10-17 | Initial placeholder model created (A40) | Phase 8 docs |
| | | |
