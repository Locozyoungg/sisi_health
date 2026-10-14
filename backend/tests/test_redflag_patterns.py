"""Text red-flag patterns (en/sw/sheng): every pattern must fire on a fixture and
never on benign text; escalation mapping routes self-harm/abuse to safeguarding."""

import pytest

from app.config import get_settings
from app.rules.loader import build_matcher

FIXTURES = {
    "en": {
        "en-severe-pain-01": "I have the worst pain of my life in my lower belly",
        "en-severe-pain-02": "sudden sharp pain started this morning",
        "en-severe-pain-03": "the pain is 10 out of 10",
        "en-bleed-dizzy-01": "I am soaking more than one pad every hour",
        "en-bleed-dizzy-02": "my period is bleeding heavily and I feel dizzy",
        "en-bleed-dizzy-03": "I almost passed out in class today",
        "en-self-harm-01": "sometimes I want to hurt myself",
        "en-self-harm-02": "I have been thinking about self harm",
        "en-self-harm-03": "there is no reason to live anymore",
        "en-abuse-01": "my uncle touched me and I am scared",
        "en-abuse-02": "I am afraid of my stepfather",
        "en-pregnancy-minor-01": "am I pregnant? my period is late",
        "en-guardian-risk-01": "my guardian hits me when I come home late",
        "en-guardian-risk-02": "he comes to my bed at night",
    },
    "sw": {
        "sw-severe-pain-01": "nina maumivu makali sana tumboni",
        "sw-severe-pain-02": "maumivu kama kisu",
        "sw-severe-pain-03": "maumivu ni 10 kati ya 10",
        "sw-bleed-dizzy-01": "damu nyingi na naskia kizunguzungu",
        "sw-bleed-dizzy-02": "naweweseka kila asubuhi",
        "sw-bleed-dizzy-03": "pedi inajaa ndani ya saa moja",
        "sw-self-harm-01": "nataka kujiumiza",
        "sw-self-harm-02": "nimefikiria kujiua",
        "sw-self-harm-03": "maisha yamepoteza maana",
        "sw-abuse-01": "alinigusa vibaya shuleni",
        "sw-abuse-02": "namuogopa baba yangu",
        "sw-pregnancy-minor-01": "nafikiri nina mimba",
        "sw-guardian-risk-01": "baba yangu ananipiga",
        "sw-guardian-risk-02": "anakuja chumbani kila usiku",
    },
    "sheng": {
        "sh-severe-pain-01": "maumivu ni mingi sana mpaka siwezi kulala",
        "sh-severe-pain-02": "pain ni 10 out of 10",
        "sh-severe-pain-03": "naskia nitakufa kwa pain",
        "sh-bleed-dizzy-01": "bleed nyingi na naskia dizzy",
        "sh-bleed-dizzy-02": "nilifaint leo asubuhi",
        "sh-self-harm-01": "siwezi kuendelea kuishi",
        "sh-self-harm-02": "life yangu haina maana",
        "sh-abuse-01": "ameforce kitu na mimi nimeogopa",
        "sh-abuse-02": "niko scared ya baba",
        "sh-pregnancy-minor-01": "nadhani niko na mimba",
        "sh-guardian-risk-01": "guardian ananichapa kila siku",
    },
}

BENIGN = {
    "en": "I had a normal period this month, some mild cramps on day one.",
    "sw": "Nilikuwa na period ya kawaida mwezi huu, maumivu kidogo siku ya kwanza.",
    "sheng": "period yangu ilikuja normally, cramps kidogo tu.",
}


@pytest.fixture(scope="module")
def matcher():
    return build_matcher(get_settings().ontology_dir)


@pytest.mark.parametrize("language", ["en", "sw", "sheng"])
def test_every_pattern_matches_its_fixture(matcher, language):
    for pattern_id, text in FIXTURES[language].items():
        hits = matcher.match_text(text)
        matched_ids = {h.pattern_id for h in hits}
        assert pattern_id in matched_ids, f"{language}: {pattern_id} did not match {text!r}"


@pytest.mark.parametrize("language", ["en", "sw", "sheng"])
def test_benign_text_has_no_hits(matcher, language):
    assert matcher.match_text(BENIGN[language]) == []


def test_escalation_mapping():
    matcher = build_matcher(get_settings().ontology_dir)
    urgent = matcher.match_text("the pain is 10 out of 10 right now")
    assert matcher.escalations(urgent) == {"urgent": True, "safeguarding": False}
    safe = matcher.match_text("I want to hurt myself")
    assert matcher.escalations(safe) == {"urgent": True, "safeguarding": True}
    abuse = matcher.match_text("I am afraid of my uncle")
    assert matcher.escalations(abuse) == {"urgent": False, "safeguarding": True}
