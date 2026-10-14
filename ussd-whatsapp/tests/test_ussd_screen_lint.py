"""USSD screen lint (spec 5.3 DoD): every screen ≤160 chars INCLUDING the
footer; no condition names anywhere; back/exit footer on every interactive
screen; SMS wording is generic."""

from gateway.flows.screens import (
    FOOTER_EN,
    FOOTER_SW,
    SCREEN_LIMIT,
    SCREENS,
    SMS_SUMMARY,
)

# Terms that must never appear in any channel string (non-negotiable 4).
FORBIDDEN = [
    "endometriosis",
    "pcos",
    "polycystic",
    "fibroid",
    "fibroids",
    "cancer",
    "cervical",
    "diagnosis",
    "symptom",
]


def test_every_screen_within_160_chars_with_footer():
    for lang, screens in SCREENS.items():
        footer = FOOTER_SW if lang == "sw" else FOOTER_EN
        for key, body in screens.items():
            if key in {
                "result_green",
                "result_yellow",
                "result_orange",
                "result_red",
                "age_blocked",
                "exit",
                "timeout",
            }:
                continue  # final screens carry no footer, but must still fit alone
            with_footer = body + "\n" + footer
            assert len(with_footer) <= SCREEN_LIMIT, (
                f"{lang}/{key}: {len(with_footer)} chars (limit {SCREEN_LIMIT})"
            )


def test_no_screen_exceeds_160_without_footer():
    for lang, screens in SCREENS.items():
        for key, body in screens.items():
            assert len(body) <= SCREEN_LIMIT, f"{lang}/{key}: {len(body)} chars"


def test_no_condition_names_anywhere():
    for lang, screens in SCREENS.items():
        for key, body in screens.items():
            lowered = body.lower()
            for term in FORBIDDEN:
                assert term not in lowered, f"{lang}/{key} leaks '{term}'"


def test_no_scores_or_conditions_in_sms():
    lowered = SMS_SUMMARY.lower()
    for term in FORBIDDEN:
        assert term not in lowered
    assert "red" not in lowered and "orange" not in lowered and "yellow" not in lowered


def test_footer_is_compact():
    assert len(FOOTER_EN) <= 16
    assert len(FOOTER_SW) <= 16
