"""Non-negotiable 4 (server side): nothing condition-identifying may reach a
notification, SMS, USSD screen or app-switcher surface. This lints every module
level string constant in app/corridor/* plus the school guardian alert against the
same banned-term list the mobile StringsPrivacyTest enforces."""

import importlib
import pkgutil

import app.corridor as corridor_package
from app.school.service import GUARDIAN_ALERT_TEXT

# Mirrored from mobile/app/src/test/kotlin/com/sisi/health/ui/StringsPrivacyTest.kt
BANNED_TERMS = (
    "endometriosis",
    "pcos",
    "polycystic",
    "fibroid",
    "fibroids",
    "cancer",
    "cervical",
    "diagnosis",
    "symptom",
    "period",
    "menstrual",
    "bleeding",
    "pregnancy",
    "pregnant",
    "pain",
)

CORRIDOR_MODULES = (
    "config",
    "consult",
    "education",
    "facilities",
    "referral",
    "reminders",
    "surgery",
    "tracking",
)

# Constants that can reach a delivery surface (SMS / notification / USSD).
DELIVERY_SURFACE = {
    "app.corridor.reminders.GENERIC_REMINDER_TEXT",
    "app.corridor.reminders.MESSAGE_KEY",
    "app.school.service.GUARDIAN_ALERT_TEXT",
}

# The ONLY constant allowed to contain a banned term: the mandatory in-app patient
# education disclaimer (spec 5.4.1 requires this exact sentence). Education content
# is read inside the app by a consenting user — it is never sent by SMS, shown in a
# notification, or rendered on a launcher / app-switcher surface.
ALLOWED_EXEMPTIONS = {
    "app.corridor.education.DISCLAIMER_SENTENCE": "spec 5.4.1 in-app education disclaimer",
}


def string_constants() -> dict[str, str]:
    """Every module-level UPPER_CASE string constant in app/corridor/*.py."""
    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(corridor_package.__path__):
        module = importlib.import_module(f"app.corridor.{info.name}")
        for name, value in vars(module).items():
            if name.isupper() and isinstance(value, str):
                found[f"app.corridor.{info.name}.{name}"] = value
    found["app.school.service.GUARDIAN_ALERT_TEXT"] = GUARDIAN_ALERT_TEXT
    return found


def leaked_terms(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in BANNED_TERMS if term in lowered]


def test_registry_covers_every_corridor_module():
    """A new corridor module may not silently evade this lint."""
    modules = {info.name for info in pkgutil.iter_modules(corridor_package.__path__)}
    assert modules == set(CORRIDOR_MODULES)
    found = string_constants()
    assert len(found) >= 6
    assert set(DELIVERY_SURFACE) <= set(found)


def test_delivery_surface_strings_never_name_a_condition():
    found = string_constants()
    for key in sorted(DELIVERY_SURFACE):
        assert leaked_terms(found[key]) == [], f"{key} leaks: {found[key]!r}"


def test_corridor_strings_never_name_a_condition_outside_the_exemption():
    for key, value in sorted(string_constants().items()):
        if key in ALLOWED_EXEMPTIONS:
            continue
        assert leaked_terms(value) == [], f"{key} leaks condition terms: {value!r}"


def test_exemptions_are_exactly_the_documented_ones():
    """Any new exemption must be a deliberate, reviewed edit to this test."""
    assert set(ALLOWED_EXEMPTIONS) == {"app.corridor.education.DISCLAIMER_SENTENCE"}
    exempt = string_constants()["app.corridor.education.DISCLAIMER_SENTENCE"]
    assert exempt == "A normal symptom check does not replace screening."


def test_guardian_alert_text_is_generic_and_actionable():
    assert leaked_terms(GUARDIAN_ALERT_TEXT) == []
    assert "school nurse" in GUARDIAN_ALERT_TEXT
    assert "clinic" in GUARDIAN_ALERT_TEXT


def test_reminder_wording_and_message_key_are_generic():
    from app.corridor.reminders import GENERIC_REMINDER_TEXT, MESSAGE_KEY

    assert GENERIC_REMINDER_TEXT == "Time for your health check-in."
    assert MESSAGE_KEY == "generic_health_checkin"
    assert leaked_terms(MESSAGE_KEY) == []
    # no codes, no digits (a helpline number in an SMS is an identifying surface)
    assert not any(character.isdigit() for character in GENERIC_REMINDER_TEXT)
