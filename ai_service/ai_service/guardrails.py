"""Deterministic guardrails (spec 5.2, decision D9, hazards HZ-07/HZ-08).

Every check here is a keyword/pattern list per language — there is NO LLM judge in
the safety path. The pipeline runs them in a fixed order (red flags first, always
before the model), and the post-filter runs on whatever the model returns, so a
misbehaving or adversarial model cannot produce a diagnosis claim, a prescription,
a band contradiction, a prompt leak, or an uncited answer that reaches a user.

English patterns are evaluated for every language because Kiswahili and Sheng
speakers code-switch; the sw/sheng lists are additive, never restrictive.
"""

import re
from collections.abc import Iterable, Sequence
from typing import TypedDict

from app.config import Settings as BackendSettings
from app.rules.redflags import SAFEGUARDING_CATEGORIES, RedFlagHit

from ai_service.prompts import LEAK_SENTINEL
from ai_service.rag import SearchHit, chunk_ids, hits_by_id

MINOR_AGE = 18

LANGUAGES = ("en", "sw", "sheng")

ROUTING_URGENT_SCRIPT = "urgent_script"
ROUTING_EDUCATION = "education"
ROUTING_REFUSE_DIAGNOSIS = "refuse_diagnosis"
ROUTING_REFUSE_PRESCRIPTION = "refuse_prescription"
ROUTING_OUT_OF_SCOPE = "out_of_scope"
ROUTING_AGE_GATED_MINOR = "age_gated_minor"
ROUTING_REFUSED = "refused"

ROUTINGS = (
    ROUTING_URGENT_SCRIPT,
    ROUTING_EDUCATION,
    ROUTING_REFUSE_DIAGNOSIS,
    ROUTING_REFUSE_PRESCRIPTION,
    ROUTING_OUT_OF_SCOPE,
    ROUTING_AGE_GATED_MINOR,
    ROUTING_REFUSED,
)

VIOLATION_DIAGNOSIS_CLAIM = "diagnosis_claim"
VIOLATION_PRESCRIPTION = "prescription"
VIOLATION_DRUG_DOSE = "drug_dose"
VIOLATION_BAND_MISMATCH = "band_mismatch"
VIOLATION_PROMPT_LEAK = "prompt_leak"
VIOLATION_MISSING_CITATION = "missing_citation"
VIOLATION_OFF_TOPIC_ANSWER = "off_topic_answer"

VIOLATIONS = (
    VIOLATION_DIAGNOSIS_CLAIM,
    VIOLATION_PRESCRIPTION,
    VIOLATION_DRUG_DOSE,
    VIOLATION_BAND_MISMATCH,
    VIOLATION_PROMPT_LEAK,
    VIOLATION_MISSING_CITATION,
    VIOLATION_OFF_TOPIC_ANSWER,
)

# Topic breadth gate: women's health only (spec 5.2). Kept generous — the failure
# mode we prefer is answering, with the post-filter as backstop.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "period",
        "periods",
        "menstruation",
        "menstrual",
        "menses",
        "monthly bleeding",
        "cycle",
        "cramps",
        "cramping",
        "bleed",
        "bleeding",
        "spotting",
        "blood",
        "discharge",
        "vagina",
        "vaginal",
        "vulva",
        "womb",
        "uterus",
        "uterine",
        "cervix",
        "cervical",
        "ovary",
        "ovaries",
        "ovarian",
        "endometriosis",
        "endo",
        "pcos",
        "polycystic",
        "fibroid",
        "fibroids",
        "hormone",
        "hormonal",
        "hpv",
        "pap smear",
        "pap",
        "smear",
        "screening",
        "cancer",
        "tumour",
        "tumor",
        "breast",
        "menopause",
        "perimenopause",
        "contraception",
        "contraceptive",
        "birth control",
        "family planning",
        "pregnancy",
        "pregnant",
        "antenatal",
        "postnatal",
        "sex",
        "sexual",
        "intercourse",
        "std",
        "sti",
        "hiv",
        "infection",
        "itch",
        "itching",
        "pain",
        "painful",
        "belly",
        "tummy",
        "abdomen",
        "abdominal",
        "pelvis",
        "pelvic",
        "urine",
        "urinary",
        "pee",
        "sanitary",
        "pad",
        "pads",
        "tampon",
        "fertility",
        "infertility",
        "puberty",
        "body changes",
        # 18+ topics are still women's-health topics: they must survive the scope
        # gate so the minor gate (which runs after it) can route them, not the
        # out-of-scope refusal.
        "abortion",
        "termination of pregnancy",
        "sterilisation",
        "sterilization",
        "tubal ligation",
        "vasectomy",
        "hysterectomy",
        "ivf",
        "in vitro",
        "surrogacy",
    ),
    "sw": (
        "hedhi",
        "kupata hedhi",
        "kuacha hedhi",
        "damu",
        "kutokwa na damu",
        "maji",
        "maji ya uke",
        "uke",
        "ukeni",
        "kizazi",
        "tumbo la uzazi",
        "shingo ya kizazi",
        "ovari",
        "pcos",
        "ovari zenye uvimbe",
        "ugonjwa wa ovari zenye uvimbe",
        "endometriosis",
        "fibroidi",
        "homoni",
        "saratani",
        "kansa",
        "matiti",
        "pap",
        "screening",
        "uchunguzi",
        "uzazi wa mpango",
        "kinga ya mimba",
        "vidonge vya uzazi",
        "mimba",
        "ujauzito",
        "mjamzito",
        "zinaa",
        "ugonjwa wa zinaa",
        "ngono",
        "maumivu",
        "tumbo",
        "maambukizi",
        "kuwasha",
        "kuwasha ukeni",
        "kujikuna",
        "mkojo",
        "uzazi",
        "pedi",
        "taulo",
        # adult topics (see the en list): scope-pass so the minor gate can route them
        "kutoa mimba",
        "kuondoa mimba",
        "kuharibu mimba",
        "kufunga uzazi",
        "kupasua kizazi",
    ),
    "sheng": (
        "periods",
        "damu",
        "maji",
        "uke",
        "kizazi",
        "ball",
        "mimba",
        "preggo",
        "pcos",
        "screening",
        "cancer",
        "pain",
        "cramps",
        "kupimwa",
    ),
}

# 18+ topics: a minor (age unknown or < 18) is routed to a nurse instead of served
# (spec 3.2/3.3 — age-appropriate wording; never a dead end, always a human).
#
# The vocabulary has two families with different consequences (A38, maintainer decision
# 2026-10-16):
#   * procedures — decisions no child can take and no child-facing surface explains.
#     HARD-gated: generic nurse referral, zero model calls, zero content, whatever the
#     two-step answer says.
#   * sexual-health questions (sex, painful sex, intercourse, body questions about sex)
#     — a teenager may genuinely have them. These take the TWO-STEP instead: an unknown
#     answer returns the deterministic per-language check question, "no" returns generic
#     guidance plus the nurse referral, and "yes" is served as age-appropriate education
#     with the same referral appended after the post-filter. Teenage pregnancy is real: a
#     minor who has had sex gets education plus a human, never a dead end.
MINOR_PROCEDURE_KEYWORDS: tuple[str, ...] = (
    "abortion",
    "abort",
    "terminate the pregnancy",
    "termination of pregnancy",
    "kutoa mimba",
    "kuondoa mimba",
    "kuharibu mimba",
    "kupasua mimba",
    "sterilisation",
    "sterilization",
    "tubal ligation",
    "kufunga uzazi",
    "kuzuia uzazi milele",
    "vasectomy",
    "hysterectomy",
    "kutoa kizazi",
    "kupasua kizazi",
    "hormone replacement",
    "hrt",
    "ivf",
    "in vitro",
    "fertility treatment",
    "matibabu ya uzazi",
    "kuzaa kwa msaada",
    "egg freezing",
    "surrogacy",
    "18+",
)

MINOR_SEXUAL_HEALTH_KEYWORDS: tuple[str, ...] = (
    "sex",
    "sexual",
    "sexually",
    "intercourse",
    "penetration",
    "ngono",
    "kujamiiana",
    "kufanya mapenzi",
    "kushiriki ngono",
    "zinaa",
    "ugonjwa wa zinaa",
    "kutombana",
)

# The full minor-gated vocabulary (both families): the language-blind union answers the
# single "is this text minor-gated at all?" question.
MINOR_GATED_KEYWORDS: tuple[str, ...] = MINOR_PROCEDURE_KEYWORDS + MINOR_SEXUAL_HEALTH_KEYWORDS

# "Do I have X / am I at risk" — a risk statement belongs to the engine, so an
# explicit diagnosis or risk question is answered with a refusal, never by the model.
DIAGNOSIS_ASK_PATTERNS: tuple[str, ...] = (
    r"\bdo i have\b",
    r"\bhave i (got|caught|developed)\b",
    r"\bwhat('s| is) wrong with me\b",
    r"\bwhat (disease|condition|illness|infection|sickness) do i have\b",
    r"\bdiagnose me\b",
    r"\bam i (sick|infected|positive|negative)\b",
    r"\bam i (low|high|at) risk\b",
    r"\bam i\b[^.?!]{0,30}\brisk\b",
    r"\bis it (cancer|serious|dangerous|an infection|a tumour|a tumor)\b",
    r"\bis this (cancer|serious|dangerous|an infection)\b",
    r"\bdo you think i have\b",
    r"\bcould i have\b",
    r"\bshould i (be|get) screen(ed)?\b",
    r"\bwhat('s| is) my risk\b",
    r"\bni(ko|na) na (ugonjwa|saratani|kansa|maambukizi|hatari)\b",
    r"\bnina (ugonjwa|saratani|kansa|maambukizi|hatari|hatari ndogo)\b",
    r"\bje,? ni(na|ko)\b[^.?!]{0,40}\b(ugonjwa|saratani|kansa|hatari)\b",
    r"\bniko na (cancer|endometriosis|pcos|fibroids?|infection)\b",
    r"\bnaweza kuwa na (ugonjwa|saratani|kansa|cancer|maambukizi)\b",
    r"\bnina ugonjwa gani\b",
    r"\bwhat condition do i have\b",
)

# "Give me a medicine" — caught BEFORE the model (D9); the drug/dose post-filter is
# the backstop for anything that slips through.
PRESCRIPTION_ASK_PATTERNS: tuple[str, ...] = (
    r"\bprescri(be|ption|bing)\b",
    r"\bwhat (medicine|medication|drug|drugs|pill|pills|tablet|tablets|antibiotic|antibiotics)\b",
    r"\bwhich (medicine|medication|drug|antibiotic|painkiller|pain killer|pill|tablet)\b",
    r"\b(what|how much|how many) (mg|ml|dose|tablets?|pills?)\b",
    r"\b(can|should|could) i (take|use|buy|get|swallow) (some |any )?"
    r"(medicine|medication|drugs?|antibiotics?|painkillers?|pain killers?|pills?|tablets?|"
    r"paracetamol|ibuprofen|panadol|amoxicillin|metronidazole)\b",
    r"\b(i want|i need|give me|get me) (some |a )?"
    r"(medicine|medication|drugs?|antibiotics?|dawa|vidonge)\b",
    r"\bwhat should i take\b",
    r"\btreat (it|this|the pain|the infection) with (medicine|antibiotics|drugs|dawa)\b",
    r"\bdawa gani\b",
    r"\bvidonge gani\b",
    r"\b(ni|ni)pe (dawa|vidonge)\b",
    r"\bnipatie (dawa|vidonge|medicine)\b",
    r"\bninunue (dawa|vidonge)\b",
    r"\bnitumie (dawa|vidonge)\b",
    r"\bnichukue (dawa|vidonge)\b",
    r"\bnile (dawa|vidonge)\b",
    r"\bnimeze (dawa|vidonge)\b",
    r"\bdawa ya\b",
    r"\bnunua dawa\b",
)

# Misbehaviour markers the post-filter must catch (HZ-07 controls).
DIAGNOSIS_CLAIM_PATTERNS: tuple[str, ...] = (
    r"\byou (do not|don't|dont) have\b",
    r"\byou (definitely|certainly|clearly|probably|likely|maybe|might|may) have\b",
    r"\byou have (endometriosis|pcos|polycystic|fibroids?|cancer|cervical cancer|"
    r"an? (infection|st[i]?d|tumou?r|cyst)|hpv|a hormonal imbalance)\b",
    r"\byou (are|'re) (suffering|infected|positive|negative)\b",
    # "the result means" alone is a content heading, not a claim: require a
    # condition-ish consequence in the same sentence
    r"\b(your|the) (diagnosis|test results?|results?)\b[^.!?]{0,12}\b(is|are|shows?|means|"
    r"confirms?|indicates?)\b[^.!?]{0,40}\b(you have|positive|negative|endometriosis|pcos|"
    r"fibroids?|cancer|infection|hpv|st[i]?d|abnormal)\b",
    r"\bthis (means|shows) you have\b",
    r"\bi can (confirm|tell you|see that)\b",
    r"\bi diagnose\b",
    r"\bni (ugonjwa wa|saratani|kansa)\b",
    r"\buna (ugonjwa|saratani|kansa|maambukizi|endometriosis|pcos|fibroidi)\b",
    r"\bhuna (ugonjwa|saratani|kansa|maambukizi)\b",
    r"\bwewe ni mgonjwa\b",
    r"\bukweli ni kwamba una\b",
)

PRESCRIPTION_PATTERNS: tuple[str, ...] = (
    r"\btake\b[^.!?]{0,24}\b(tablets?|pills?|capsules?|medicine|medication|ibuprofen|"
    r"paracetamol|panadol|amoxicillin|metronidazole|antibiotics?|dawa)\b",
    r"\bi (recommend|suggest|advise) (taking|using|that you take)\b",
    r"\byou should (take|use|start) (some |a |the )?(medicine|medication|antibiotics?|"
    r"painkillers?|pills?|tablets?|dawa)\b",
    r"\b(nile|kula|meza|chukua) (dawa|vidonge)\b",
    r"\bnakushauri (kutumia|kunywa|kula) (dawa|vidonge)\b",
    r"\bnimekupa (dawa|vidonge)\b",
    r"\bdawa ya (maumivu|ugonjwa)\b",
)

# digits + unit: the drug/dose backstop (post-filter). Deliberately narrow — plain
# numbers ("1-2 pads") are not a dose, and a false refusal on self-care advice is
# worse than useless.
DRUG_DOSE_PATTERNS: tuple[str, ...] = (
    r"\b\d{1,4}(\.\d+)?\s*(mg|ml|mcg|µg|mg/ml|iu|tablets?|pills?|capsules?|drops?)\b",
)

BAND_TOKEN_PATTERNS: tuple[str, ...] = (
    r"\b(GREEN|YELLOW|ORANGE|RED|NOT_ENOUGH_DATA)\b",
)

PROMPT_LEAK_PATTERNS: tuple[str, ...] = (
    LEAK_SENTINEL,  # the prompt template's own header (prompts.SYSTEM_PROMPT_TEMPLATE)
    r"STUB_MARKER_PROMPT_LEAK",
    r"\bsystem prompt\b",
    r"\bas an AI language model\b",
    r"\bmy instructions say\b",
)

OFF_TOPIC_PATTERNS: tuple[str, ...] = (
    r"\brecipe\b",
    r"\bchapati\b",
    r"\bnyama choma\b",
    r"\bfootball\b",
    r"\bpremier league\b",
    r"\bbetting\b",
    r"\bgambl(e|ing)\b",
    r"\blottery\b",
    r"\bpolitics?\b",
    r"\belection\b",
    r"\bpresident\b",
    r"\bmovie\b",
    r"\bsong\b",
    r"\bjoke\b",
    r"\bhomework\b",
    r"\bhoroscope\b",
    r"\bsiasa\b",
    r"\bmpira\b",
    r"\bmziki\b",
    r"\bsinema\b",
)

CITATION_PATTERN = r"\b[a-z0-9][a-z0-9-]*#\d+\b"

# Deterministic refusal texts. They never contain a condition name, a band, or a
# medicine — a refusal is not an answer (non-negotiable 4 applies to every channel).
REFUSAL_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        ROUTING_REFUSE_DIAGNOSIS: (
            "I cannot tell you whether you have any condition, and I cannot say what "
            "your own risk is — that is not something this app or I can decide. Only a "
            "health worker who examines you can. Please talk to your school nurse or "
            "visit a health facility; bring a trusted adult if you can."
        ),
        ROUTING_REFUSE_PRESCRIPTION: (
            "I cannot recommend any medicine or dose. Giving medicine without seeing "
            "you would be unsafe. Please talk to a school nurse, a pharmacist or a "
            "health worker about what you are feeling — they can check and advise you."
        ),
        ROUTING_OUT_OF_SCOPE: (
            "I can only help with women's health questions — periods, pain, bleeding, "
            "discharge, infections, screening, and similar topics. Please ask me one of "
            "those, or talk to your school nurse or a health worker."
        ),
        ROUTING_AGE_GATED_MINOR: (
            "That topic is for adults. Please talk to your school nurse or a health "
            "worker — they can listen and help you decide what to do next, and they can "
            "bring in a trusted adult with you if you want."
        ),
        ROUTING_REFUSED: (
            "I could not find approved information I can safely share for that. Please "
            "talk to your school nurse or a health worker — they can help you directly."
        ),
    },
    "sw": {
        # NOTE: this refusal must never contain the "una ugonjwa" sequence — the
        # post-filter's Kiswahili diagnosis-claim pattern matches it, so a refusal
        # that used it would be rejected by our own filter (test_guardrails.py).
        ROUTING_REFUSE_DIAGNOSIS: (
            "Huwezi kujua ugonjwa wako kutoka kwa dalili pekee, na mimi siwezi "
            "kukwambia kwamba unayo — hilo halina jibu langu wala la programu hii. "
            "Dalili zako zinahitaji kuchunguzwa na mhudumu wa afya. Tafadhali ongea na "
            "nesi wa shule yako au nenda kwa kituo cha afya; nenda na mtu unayemwamini "
            "kama unaweza."
        ),
        ROUTING_REFUSE_PRESCRIPTION: (
            "Siwezi kupendekeza dawa yoyote au kipimo chake. Kutoa dawa bila "
            "kukuchunguza si salama. Tafadhali ongea na nesi wa shule, mfamasia au "
            "mhudumu wa afya kuhusu unachohisi — wanaweza kukuchunguza na kukushauri."
        ),
        ROUTING_OUT_OF_SCOPE: (
            "Naweza kusaidia tu na maswali ya afya ya wanawake — hedhi, maumivu, damu, "
            "maji, maambukizi, uchunguzi na mada kama hizo. Tafadhali niulize mojawapo, "
            "au ongea na nesi wa shule au mhudumu wa afya."
        ),
        ROUTING_AGE_GATED_MINOR: (
            "Mada hii ni ya watu wazima. Tafadhali ongea na nesi wa shule au mhudumu wa "
            "afya — wanaweza kukusikiliza na kukusaidia kuamua cha kufanya, na "
            "wanaweza kumleta mtu unayemwamini kama unataka."
        ),
        ROUTING_REFUSED: (
            "Sikupata taarifa zilizoidhinishwa ambazo naweza kukupa kwa usalama kuhusu "
            "hilo. Tafadhali ongea na nesi wa shule au mhudumu wa afya — wanaweza "
            "kukusaidia moja kwa moja."
        ),
    },
    "sheng": {
        ROUTING_REFUSE_DIAGNOSIS: (
            "Sikwezi kukuambia kama uko na condition yoyote, na sikwezi kusema risk "
            "yako ni gani — hiyo si kitu mie ama app hii inaweza kuamua. Ni medic "
            "anayekucheck ndio anajua. Tafadhali ongea na nurse wa school ama nenda "
            "clinic; enda na mtu unamtrust kama unaweza."
        ),
        ROUTING_REFUSE_PRESCRIPTION: (
            "Sikwezi kurecommend dawa yoyote ama dose. Kutoa dawa bila kukucheki si "
            "safe. Tafadhali ongea na nurse wa school, pharmacist ama medic kuhusu "
            "unaskia — wanaweza kukucheck na kukushow."
        ),
        ROUTING_OUT_OF_SCOPE: (
            "Naweza kusaidia tu na maswali ya health ya wanawake — periods, pain, damu, "
            "maji, infections, screening na topics kama hizo. Tafadhali niulize moja "
            "ya hizo, ama ongea na nurse wa school ama medic."
        ),
        ROUTING_AGE_GATED_MINOR: (
            "Hii topic ni ya adults. Tafadhali ongea na nurse wa school ama medic — "
            "wanaweza kuskiza na kukusaidia kuamua next step, na wanaweza kucome na "
            "mtu unamtrust kama unataka."
        ),
        ROUTING_REFUSED: (
            "Sikupata info iliyoidhinishwa ambayo naweza kukushow safely kuhusu hiyo. "
            "Tafadhali ongea na nurse wa school ama medic — wanaweza kukusaidia moja "
            "kwa moja."
        ),
    },
}

# The minor sexual-health two-step (A38, maintainer decision 2026-10-16). All three
# templates are per language, deterministic, and generic: no condition name, no band,
# no medicine, no digits — and each must survive the post-filter it is served beside
# (test_guardrails.py). The "no" and "yes" paths share ONE referral sentence so the two
# cannot drift apart.
MINOR_SEX_CHECK_TEXTS: dict[str, str] = {
    "en": (
        "Have you ever had sex? Reply yes or no — I want to give you the right guidance."
    ),
    "sw": (
        "Je, umewahi kufanya ngono? Jibu ndiyo au hapana — nataka kukupa mwongozo "
        "unaofaa."
    ),
    "sheng": (
        "Umewahi kufanya sex? Reply yes or no — nataka kukupa mwongozo unaofaa."
    ),
}

# Generic guidance WITHOUT sexual content, served when the minor answered "no".
MINOR_NO_SEX_TEXTS: dict[str, str] = {
    "en": (
        "Period and body questions are best discussed with your school nurse or a "
        "trusted adult at the clinic."
    ),
    "sw": (
        "Maswali kuhusu hedhi na mwili wako ni bora kuyajadili na nesi wa shule yako au "
        "mtu mzima unayemwamini kwenye kituo cha afya."
    ),
    "sheng": (
        "Maswali kuhusu periods na body yako ni bora kuongea na nurse wa school ama "
        "mtu mzima unamtrust kwenye clinic."
    ),
}

# The deterministic nurse-referral sentence: appended to the generic "no" guidance, and
# appended to the model's education answer AFTER the post-filter for a minor who
# answered "yes" (the filter only ever judges model text).
MINOR_YES_NURSE_LINE: dict[str, str] = {
    "en": "Please talk to your school nurse or visit a clinic.",
    "sw": "Tafadhali ongea na nesi wa shule yako au tembelea kituo cha afya.",
    "sheng": "Tafadhali ongea na nurse wa school ama enda clinic.",
}

URGENT_SCRIPTS: dict[str, str] = {
    "en": (
        "This needs care TODAY. Do not wait to see whether it gets better.\n\n"
        "1. Go to the nearest health facility now, or ask your school nurse to see you "
        "today. Take someone you trust with you if you can.\n"
        "2. If you cannot travel, call the child helpline {helpline_child} — free, 24 "
        "hours — and tell them what is happening.\n"
        "3. If someone is hurting you or has hurt you, the GBV helpline "
        "{helpline_gbv} can help you too.\n\n"
        "This is not a diagnosis. A health worker will check you and decide what care "
        "you need."
    ),
    "sw": (
        "Hii inahitaji matibabu LEO. Usisubiri kuona kama itapungua.\n\n"
        "1. Nenda kwa kituo cha afya kilicho karibu sasa, au mwambie nesi wa shule "
        "yako akuchunguze leo. Nenda na mtu unayemwamini kama unaweza.\n"
        "2. Kama huwezi kusafiri, piga simu kwa mstari wa watoto {helpline_child} — "
        "bila malipo, saa 24 — uwaambie kinachotokea.\n"
        "3. Kama kuna mtu anakuumiza au alikuumiza, mstari wa GBV {helpline_gbv} "
        "unaweza kukusaidia pia.\n\n"
        "Hii si utambuzi. Mhudumu wa afya atakuchunguza na kuamua matibabu "
        "unayohitaji."
    ),
    "sheng": (
        "Hii inahitaji kucarewa LEO. Usisubiri kucheck kama itaisha.\n\n"
        "1. Enda facility ya health iliyo karibu saa hii, ama mwambie nurse wa school "
        "akucheki leo. Enda na mtu unamtrust kama unaweza.\n"
        "2. Kama hauwezi kusafiri, call child helpline {helpline_child} — free, 24 "
        "hours — uwaambie inaendaje.\n"
        "3. Kama kuna mtu anakuhurt ama alikuhurt, GBV helpline {helpline_gbv} "
        "inaweza kukusaidia pia.\n\n"
        "Hii si diagnosis. Medic atakucha na kuamua care unayohitaji."
    ),
}

SAFEGUARDING_LINES: dict[str, str] = {
    "en": (
        "You are not alone in this, and it is not your fault. There is a safe adult "
        "whose job it is to help — a school nurse, a counsellor, or the child helpline "
        "{helpline_child}. What you say is kept private and shared only with the people "
        "whose job is to protect you."
    ),
    "sw": (
        "Huko peke yako katika hili, na si kosa lako. Kuna mtu mzima salama ambaye "
        "kazi yake ni kukusaidia — nesi wa shule, mshauri, au mstari wa watoto "
        "{helpline_child}. Unachosema ni siri na hutolewa tu kwa watu ambao kazi yao "
        "ni kukulinda."
    ),
    "sheng": (
        "Huko peke yako kwa hii, na si makosa yako. Kuna mtu mzima safe whose job ni "
        "kukusaidia — nurse wa school, counsellor, ama child helpline {helpline_child}. "
        "Unasema ni private na hutolewa tu kwa watu whose job ni kukulinda."
    ),
}


def _compile(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def _compile_keywords(keywords: Iterable[str]) -> re.Pattern[str]:
    # Word-boundary alternation over escaped keywords; multi-word phrases included.
    joined = "|".join(re.escape(keyword) for keyword in keywords)
    return re.compile(rf"(?<!\w)(?:{joined})(?!\w)", re.IGNORECASE)


def _matches_any(patterns: list[re.Pattern[str]], text_value: str) -> bool:
    return any(pattern.search(text_value) for pattern in patterns)


def _keywords_for(language: str) -> tuple[str, ...]:
    """Sheng is code-switched Kiswahili/English: its gate unions the en + sw lists."""
    if language == "sheng":
        return TOPIC_KEYWORDS["en"] + TOPIC_KEYWORDS["sw"] + TOPIC_KEYWORDS["sheng"]
    return TOPIC_KEYWORDS.get(language, TOPIC_KEYWORDS["en"])


_TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "en": _compile_keywords(_keywords_for("en")),
    "sw": _compile_keywords(_keywords_for("sw")),
    "sheng": _compile_keywords(_keywords_for("sheng")),
}
_MINOR_PATTERN = _compile_keywords(MINOR_GATED_KEYWORDS)
_MINOR_PROCEDURE_PATTERN = _compile_keywords(MINOR_PROCEDURE_KEYWORDS)
_MINOR_SEX_PATTERN = _compile_keywords(MINOR_SEXUAL_HEALTH_KEYWORDS)

_DIAGNOSIS_ASK_PATTERNS = _compile(DIAGNOSIS_ASK_PATTERNS)
_PRESCRIPTION_ASK_PATTERNS = _compile(PRESCRIPTION_ASK_PATTERNS)
_DIAGNOSIS_CLAIM_PATTERNS = _compile(DIAGNOSIS_CLAIM_PATTERNS)
_PRESCRIPTION_PATTERNS = _compile(PRESCRIPTION_PATTERNS)
_DRUG_DOSE_PATTERNS = _compile(DRUG_DOSE_PATTERNS)
_BAND_TOKEN_PATTERNS = _compile(BAND_TOKEN_PATTERNS)
_PROMPT_LEAK_PATTERNS = _compile(PROMPT_LEAK_PATTERNS)
_OFF_TOPIC_PATTERNS = _compile(OFF_TOPIC_PATTERNS)
_CITATION_RE = re.compile(CITATION_PATTERN, re.IGNORECASE)


class FilterVerdict(TypedDict):
    """Post-filter result: `ok` plus the first reason and every violation found."""

    ok: bool
    reason: str | None
    violations: list[str]


class TopicFilter:
    """Women's-health breadth gate (spec 5.2: the assistant stays in scope)."""

    def is_womens_health(self, text_value: str, language: str = "en") -> bool:
        if not text_value.strip():
            return False
        pattern = _TOPIC_PATTERNS.get(language)
        if pattern is None:
            pattern = _TOPIC_PATTERNS["en"]
        return bool(pattern.search(text_value))


class MinorTopicGate:
    """Age gate for 18+ topics. An unknown age is treated as a minor (safety
    asymmetry: the protective branch is the default). The keyword lists are single
    unions across en/sw/sheng — the gate is deliberately language-blind.

    Two families (A38): `is_procedure_gated` is the hard gate (generic referral, no
    model, whatever the two-step answer); `is_sexual_health_gated` is the two-step
    family. A text matching both is hard-gated — the procedure branch decides first.
    """

    def is_minor_gated(self, text_value: str, language: str = "en") -> bool:
        """Both families: "is this text minor-gated at all?" (the union)."""
        return bool(_MINOR_PATTERN.search(text_value))

    def is_procedure_gated(self, text_value: str, language: str = "en") -> bool:
        return bool(_MINOR_PROCEDURE_PATTERN.search(text_value))

    def is_sexual_health_gated(self, text_value: str, language: str = "en") -> bool:
        return bool(_MINOR_SEX_PATTERN.search(text_value))

    @staticmethod
    def applies(age: int | None) -> bool:
        return age is None or age < MINOR_AGE


class DiagnosisAskDetector:
    """Deterministic "do I have X / am I at risk" detector (A36: risk belongs to the
    engine). Runs BEFORE the model, so no band or condition can be assigned by it."""

    def is_diagnosis_ask(self, text_value: str, language: str = "en") -> bool:
        return _matches_any(_DIAGNOSIS_ASK_PATTERNS, text_value)


class PrescriptionAskDetector:
    """Deterministic prescription-request detector (D9). Runs BEFORE the model."""

    def is_prescription_ask(self, text_value: str, language: str = "en") -> bool:
        return _matches_any(_PRESCRIPTION_ASK_PATTERNS, text_value)


class PostFilter:
    """Deterministic post-filter on the model's answer (HZ-07 control).

    A model answer is returned to a user ONLY if this passes: no diagnosis claim
    (including negated ones — "you do not have…" is still a diagnosis statement),
    no prescription, no drug/dose, no band mention other than the engine's, no
    prompt leak, at least one chunk citation, and no off-topic drift.
    """

    def check(self, text_value: str, *, band: str | None = None) -> FilterVerdict:
        violations: list[str] = []
        if _matches_any(_DIAGNOSIS_CLAIM_PATTERNS, text_value):
            violations.append(VIOLATION_DIAGNOSIS_CLAIM)
        if _matches_any(_PRESCRIPTION_PATTERNS, text_value):
            violations.append(VIOLATION_PRESCRIPTION)
        if _matches_any(_DRUG_DOSE_PATTERNS, text_value):
            violations.append(VIOLATION_DRUG_DOSE)
        if self._band_mismatch(text_value, band):
            violations.append(VIOLATION_BAND_MISMATCH)
        if _matches_any(_PROMPT_LEAK_PATTERNS, text_value):
            violations.append(VIOLATION_PROMPT_LEAK)
        if not _CITATION_RE.search(text_value):
            violations.append(VIOLATION_MISSING_CITATION)
        if _matches_any(_OFF_TOPIC_PATTERNS, text_value):
            violations.append(VIOLATION_OFF_TOPIC_ANSWER)
        return {
            "ok": not violations,
            "reason": violations[0] if violations else None,
            "violations": violations,
        }

    @staticmethod
    def _band_mismatch(text_value: str, band: str | None) -> bool:
        for pattern in _BAND_TOKEN_PATTERNS:
            for match in pattern.finditer(text_value):
                mentioned = match.group(1).upper()
                if band is None or mentioned != band.upper():
                    return True
        return False


def build_urgent_script(
    hits: Sequence[RedFlagHit],
    backend_settings: BackendSettings,
    *,
    language: str = "en",
    safeguarding: bool = False,
) -> str:
    """The urgent-care script (spec 3.3): deterministic template + configured
    hotlines. Nothing here is model-generated and no condition is named — the
    red-flag hit categories (and the engine's safeguarding escalation) only decide
    whether the safeguarding paragraph is appended; safeguarding routes to the
    designated lead and the helplines, never to a guardian alert."""
    template = URGENT_SCRIPTS.get(language, URGENT_SCRIPTS["en"])
    script = template.format(
        helpline_child=backend_settings.helpline_child,
        helpline_gbv=backend_settings.helpline_gbv,
    )
    if safeguarding or any(hit.category in SAFEGUARDING_CATEGORIES for hit in hits):
        line = SAFEGUARDING_LINES.get(language, SAFEGUARDING_LINES["en"])
        script = f"{script}\n\n{line.format(helpline_child=backend_settings.helpline_child)}"
    return script


def refusal_text(routing: str, language: str = "en") -> str:
    texts = REFUSAL_TEXTS.get(language, REFUSAL_TEXTS["en"])
    return texts.get(routing, texts[ROUTING_REFUSED])


def minor_sex_check_text(language: str = "en") -> str:
    """The discreet two-step check question (deterministic; zero model calls)."""
    return MINOR_SEX_CHECK_TEXTS.get(language, MINOR_SEX_CHECK_TEXTS["en"])


def minor_no_sex_text(language: str = "en") -> str:
    """Generic guidance (no sexual content) + the nurse-referral sentence."""
    guidance = MINOR_NO_SEX_TEXTS.get(language, MINOR_NO_SEX_TEXTS["en"])
    return f"{guidance} {minor_nurse_line(language)}"


def minor_nurse_line(language: str = "en") -> str:
    """The deterministic nurse-referral sentence: part of the "no" guidance and
    appended (post-filter) to the education answer of a minor who answered "yes"."""
    return MINOR_YES_NURSE_LINE.get(language, MINOR_YES_NURSE_LINE["en"])


def citations_for(answer_text: str, hits: Sequence[SearchHit]) -> list[SearchHit]:
    """Retrieved chunks actually cited by the answer, in order of first citation."""
    indexed = hits_by_id(hits)
    return [indexed[chunk_id] for chunk_id in chunk_ids(answer_text) if chunk_id in indexed]
