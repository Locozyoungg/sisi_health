"""Versioned consent texts. Plain-language templates; the wording itself is subject to
legal review (human task H6) and each text records its content hash so consent events
always reference exactly what was consented to."""

from dataclasses import dataclass

EN_PRIVACY = (
    "SISI Health stores your health check answers and diary privately, encrypted, and "
    "never shares them with your school staff except as a severity level. A school nurse "
    "may contact you if your result needs follow-up. You can withdraw your consent at any "
    "time. SISI supports you and your doctor - it does not diagnose."
)
SW_PRIVACY = (
    "SISI Health huhifadhi majibu yako ya afya kwa siri, yamefichwa kwa usimbaji, na "
    "hayashirikiwi na wafanyakazi wa shule isipokuwa kiwango cha hatari tu. Muuguzi wa "
    "shule anaweza kuwasiliana nawe ikiwa matokeo yanahitaji ufuatiliaji. Unaweza kuondoa "
    "idhini yako wakati wowote. SISI inakusaidia wewe na daktari wako - haitoi utambuzi."
)
EN_GUARDIAN = (
    "I confirm I am the parent or guardian of this child and I consent to SISI Health "
    "collecting and storing her health check answers and diary so that the school nurse "
    "and health workers can support her. I understand her diary and answers are private "
    "and I will not be shown them. I may withdraw this consent at any time."
)
SW_GUARDIAN = (
    "Ninathibitisha kuwa mimi ni mzazi au mlezi wa mtoto huyu na ninatoa idhini kwa SISI "
    "Health kukusanya na kuhifadhi majibu yake ya afya ili muuguzi wa shule na wafanyakazi "
    "wa afya waweze kumsaidia. Ninaelewa kuwa shajara na majibu yake ni ya siri na "
    "sitaonyeshwa. Naweza kuondoa idhini hii wakati wowote."
)
EN_ASSENT = (
    "I understand that SISI Health will keep my answers private, that my parent or "
    "guardian will not read my diary, and that I can stop at any time. I agree to take "
    "part."
)
SW_ASSENT = (
    "Ninaelewa kuwa SISI Health itahifadhi majibu yangu kwa siri, kwamba mzazi au mlezi "
    "wangu hatasoma shajara yangu, na kwamba ninaweza kuacha wakati wowote. Nakubali "
    "kushiriki."
)
EN_SELF = (
    "I consent to SISI Health collecting and storing my health check answers and diary, "
    "encrypted and private to me. I may withdraw this consent at any time. SISI supports "
    "you and your doctor - it does not diagnose."
)
SW_SELF = (
    "Ninatoa idhini kwa SISI Health kukusanya na kuhifadhi majibu yangu ya afya, "
    "yakiwa yamefichwa na ya siri kwangu. Naweza kuondoa idhini hii wakati wowote. SISI "
    "inakusaidia wewe na daktari wako - haitoi utambuzi."
)


@dataclass(frozen=True)
class ConsentTextSpec:
    key: str
    language: str
    title: str
    body: str


CONSENT_TEXTS: tuple[ConsentTextSpec, ...] = (
    ConsentTextSpec("privacy_notice", "en", "Privacy notice", EN_PRIVACY),
    ConsentTextSpec("privacy_notice", "sw", "Taarifa ya faragha", SW_PRIVACY),
    ConsentTextSpec("guardian_consent", "en", "Parent/guardian consent", EN_GUARDIAN),
    ConsentTextSpec("guardian_consent", "sw", "Idhini ya mzazi/mlezi", SW_GUARDIAN),
    ConsentTextSpec("minor_assent", "en", "Assent of the minor", EN_ASSENT),
    ConsentTextSpec("minor_assent", "sw", "Idhini ya mtoto", SW_ASSENT),
    ConsentTextSpec("self_consent", "en", "Consent (adult)", EN_SELF),
    ConsentTextSpec("self_consent", "sw", "Idhini (mtu mzima)", SW_SELF),
)
