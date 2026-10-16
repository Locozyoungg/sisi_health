"""Text red-flag patterns (en/sw/sheng): every pattern must fire on a fixture and
never on benign text; escalation mapping routes self-harm/abuse to safeguarding
and the cervical-screening bleeding/discharge categories to the urgent script."""

import json

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
        # cervical screening (spec 5.4.1)
        "en-cervical-postcoital-01": "I noticed bleeding after sex last week",
        "en-cervical-postcoital-02": "post-coital bleeding is why I came",
        "en-cervical-intermenstrual-01": "I am bleeding between my periods",
        "en-cervical-intermenstrual-02": "there is spotting mid-cycle for me",
        "en-cervical-postmenopausal-01": "I have bleeding after menopause",
        "en-cervical-postmenopausal-02": "postmenopausal bleeding worries me",
        "en-cervical-discharge-01": "I have unusual discharge that has lasted two weeks",
        "en-cervical-discharge-02": "I have a smelly discharge every day",
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
        # cervical screening (spec 5.4.1)
        "sw-cervical-postcoital-01": "Niliona damu baada ya kujamiiana wiki iliyopita",
        "sw-cervical-postcoital-02": "ngono inaniletea damu kila mara",
        "sw-cervical-intermenstrual-01": "Nina damu kati ya hedhi zangu",
        "sw-cervical-intermenstrual-02": "kutokwa na damu nje ya hedhi zangu",
        "sw-cervical-postmenopausal-01": "Nina damu baada ya kuacha hedhi",
        "sw-cervical-postmenopausal-02": "Nina damu nimekoma hedhi miaka miwili iliyopita",
        "sw-cervical-discharge-01": "Nina maji ya ajabu kwa uke kwa wiki mbili",
        "sw-cervical-discharge-02": "maji yananuka vibaya kwa uke",
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
        # cervical screening (spec 5.4.1)
        "sh-cervical-postcoital-01": "Nimeona damu after sex, inanitisha",
        "sh-cervical-postcoital-02": "sex inaniletea damu kila time",
        "sh-cervical-intermenstrual-01": "Natoa damu hata siko kwa periods zangu",
        "sh-cervical-intermenstrual-02": "natoa damu nje ya periods zangu",
        "sh-cervical-postmenopausal-01": "Natoa damu lakini nilishamaliza periods kitambo",
        "sh-cervical-postmenopausal-02": "damu baada ya kukoma periods zangu",
        "sh-cervical-discharge-01": "discharge inasmell vibaya",
        "sh-cervical-discharge-02": "discharge imekuwa wiki mbili sasa",
    },
}

# Near-miss wording: each text shares vocabulary with its pattern id but must never
# fire it. A false positive here is a real failure — it puts the urgent script (and
# the helplines) in front of an ordinary question, which trains users to ignore it.
NEAR_MISS = {
    "sh-self-harm-01": (
        "nataka kuishi",  # I want to live is not a death wish
        "nataka kuishi maisha yangu normally",
    ),
    "sw-cervical-postmenopausal-01": (
        "Niambie kuhusu kuacha hedhi.",  # menopause education, no bleeding reported
    ),
    "en-cervical-discharge-01": (
        "What does unusual discharge mean?",  # education question, no persistence
        "Can I take antibiotics for the discharge?",
    ),
    "sw-cervical-discharge-01": (
        "Maji ya uke yanamaanisha nini?",  # ordinary vaginal fluid question
    ),
    "sh-cervical-discharge-02": (
        "Niko na discharge ya ajabu, nifanye nini?",  # no smell/persistence cue
    ),
    "en-cervical-postcoital-01": (
        "I bleed a lot during my period but it stops after five days.",
    ),
    "en-cervical-intermenstrual-01": (
        "Is it normal to have irregular periods?",
    ),
}

BENIGN = {
    "en": (
        "I had a normal period this month, some mild cramps on day one.",
        "How can I track my cycle?",
    ),
    "sw": (
        "Nilikuwa na period ya kawaida mwezi huu, maumivu kidogo siku ya kwanza.",
        "Nifanye nini kuhusu maumivu ya hedhi shuleni?",
    ),
    "sheng": (
        "period yangu ilikuja normally, cramps kidogo tu.",
        "nataka kuishi maisha yangu normally, niko sawa",  # explicit: wanting to live
        "Nifanye aje ku track periods zangu?",
    ),
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


def test_every_shipped_pattern_has_a_fixture():
    """The sweep above can only prove what the fixtures cover: a pattern id with no
    fixture (or a typo in one) would never be exercised, so it is a failure here."""
    covered = {pattern_id for fixtures in FIXTURES.values() for pattern_id in fixtures}
    for path in sorted((get_settings().ontology_dir / "redflags").glob("patterns.*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document["patterns"]:
            assert entry["id"] in covered, f"{path.name}: {entry['id']} has no fixture"


@pytest.mark.parametrize("language", ["en", "sw", "sheng"])
def test_benign_text_has_no_hits(matcher, language):
    for text in BENIGN[language]:
        assert matcher.match_text(text) == [], text


@pytest.mark.parametrize(("pattern_id", "texts"), sorted(NEAR_MISS.items()))
def test_near_miss_texts_never_fire_their_pattern(matcher, pattern_id, texts):
    for text in texts:
        matched = {h.pattern_id for h in matcher.match_text(text)}
        assert pattern_id not in matched, f"{pattern_id} false-positived on {text!r}"


def test_sheng_self_harm_fires_on_a_death_wish_and_never_on_wanting_to_live(matcher):
    """Regression: the old regex (nataka|siwezi kuendelea)( kuishi| kuishi) read
    "nataka kuishi" (I want to live) as a self-harm signal and showed the child
    helpline script for it."""
    for text in ("siwezi kuendelea kuishi", "nataka kujiua"):
        matched = {h.pattern_id for h in matcher.match_text(text)}
        assert "sh-self-harm-01" in matched, text
    for text in ("nataka kuishi", "nataka kuishi maisha yangu"):
        matched = {h.pattern_id for h in matcher.match_text(text)}
        assert "sh-self-harm-01" not in matched, text


@pytest.mark.parametrize(
    "text",
    [
        "the pain is 10 out of 10 right now",
        "I noticed bleeding after sex last week",
        "I am bleeding between my periods",
        "Nina damu baada ya kuacha hedhi",
        "Natoa damu lakini nilishamaliza periods kitambo",
        "Nina maji ya ajabu kwa uke kwa wiki mbili",
        "I have unusual discharge that has lasted two weeks",
    ],
)
def test_escalation_mapping(matcher, text):
    """Urgent categories force the urgent-care script first; the cervical
    bleeding/discharge categories are urgent but never safeguarding — they route to
    care, not to the safeguarding lead (spec 3.3, 5.4.1)."""
    hits = matcher.match_text(text)
    assert hits, text
    assert matcher.escalations(hits) == {"urgent": True, "safeguarding": False}, text


def test_safeguarding_escalations_stay_separate_from_the_cervical_categories(matcher):
    safe = matcher.match_text("I want to hurt myself")
    assert matcher.escalations(safe) == {"urgent": True, "safeguarding": True}
    abuse = matcher.match_text("I am afraid of my uncle")
    assert matcher.escalations(abuse) == {"urgent": False, "safeguarding": True}


def test_every_cervical_red_flag_case_hits_a_pattern(matcher):
    """The Phase 5 cervical cases that assert `red_flag` must all reach the urgent
    script through this matcher; a case that matched nothing would be answered by
    the assistant instead (spec 5.4.1, 100% red-flag routing gate)."""
    path = get_settings().ontology_dir / "guardrail" / "cervical_guardrail_cases.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    red_flags = [case for case in document["cases"] if case["expected_routing"] == "red_flag"]
    assert len(red_flags) == 11
    for case in red_flags:
        hits = matcher.match_text(case["input"])
        assert hits, f'{case["id"]}: no red-flag pattern matched {case["input"]!r}'
        assert matcher.escalations(hits)["urgent"] is True, case["id"]
