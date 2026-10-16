"""SISI Health AI conversation layer (Phase 6, spec 5.2).

SISI supports you and your doctor — it does not diagnose. The deterministic rules
engine owns every risk band; this service only explains what the engine decided,
using retrieved, clinician-reviewable content chunks. Red flags, refusals and the
post-filter are deterministic and run before/after the LLM — never as an LLM judge
(non-negotiable 1).
"""

__version__ = "0.1.0"
