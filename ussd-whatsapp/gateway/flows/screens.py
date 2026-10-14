"""USSD screen texts (en/sw). Constraints enforced by test_screen_lint:
- every screen ≤ 160 characters INCLUDING the footer the engine appends
- no condition names anywhere (non-negotiable 4)
- "0" back and "00" exit appear on every screen (appended by the engine)
- the SMS summary is generic wording only (spec 3.5)."""

SCREEN_LIMIT = 160
FOOTER_EN = "0 Back 00 Exit"
FOOTER_SW = "0 Rudi 00 Toka"

# The exact generic SMS wording from spec 3.5 — never contains scores or conditions.
SMS_SUMMARY = "Your health check results are ready. Visit your school nurse or open the app."

SCREENS = {
    "en": {
        "welcome": "Welcome to SISI. Answer a few questions about how you feel. "
        "If this phone is shared, clear the call log after.",
        "lang": "Choose language. Chagua lugha\n1 English\n2 Kiswahili",
        "age": "How old are you? Reply with your age in years.",
        "age_blocked": "SISI is for ages 13 and above. Thank you.",
        "privacy_adult": "SISI keeps your answers private and encrypted. School staff "
        "see only a care level. A nurse may contact you if needed.\n1 Agree",
        "privacy_minor": "SISI keeps your answers private. Storing them needs your "
        "parent or guardian's OK. A nurse can help. You can answer now.\n1 Continue",
        "q1": "On a scale of 0 to 10, how much pain do you have today? Reply with a number.",
        "q2": "How heavy is your bleeding?\n1 None\n2 Spotting\n3 Light\n4 Moderate\n5 Heavy",
        "q3": "How is your bleeding pattern?\n1 Regular\n2 Irregular\n3 Unsure",
        "q4": "How many school days have you missed this term because of how you feel? Reply with a number.",
        "q5": "Do you feel dizzy or faint?\n1 Yes\n2 No",
        "q6": "Do you feel very tired most days?\n1 Yes\n2 No",
        "q7": "Do your periods come regularly?\n1 Yes\n2 No\n3 Unsure",
        "q8": "How long have you felt this way?\n1 Under 3 months\n2 3 to 6 months\n3 Over 6 months",
        "q9": "Does the pain stop your daily activities?\n1 Yes\n2 No",
        "q10_adult": "Do you have pain during or after intercourse?\n1 Yes\n2 No\n3 Prefer not to say",
        "q10_minor": "Do you have pain when passing stool?\n1 Yes\n2 No\n3 Prefer not to say",
        "result_green": "Thank you. Keep tracking your days. See your school nurse if this keeps up.",
        "result_yellow": "Please see your school nurse when you can. Keep tracking your days.",
        "result_orange": "Please see a nurse or doctor soon. Do not wait long.",
        "result_red": "Please seek care now. Do not wait. If a nurse is near, go now.",
        "exit": "Session ended. Clear your call log if this phone is shared.",
        "timeout": "Your session expired. Start again.",
    },
    "sw": {
        "welcome": "Karibu SISI. Jibu maswali machache kuhusu hali yako. "
        "Kama simu hii inashirikiwa, futa historia ya simu baadaye.",
        "lang": "Choose language. Chagua lugha\n1 English\n2 Kiswahili",
        "age": "Una miaka mingapi? Jibu kwa namba ya miaka yako.",
        "age_blocked": "SISI ni kwa wenye miaka 13 na kuendelea. Asante.",
        "privacy_adult": "SISI huhifadhi majibu yako kwa siri. Wafanyakazi wa shule "
        "huona kiwango cha huduma tu. Muuguzi anaweza kuwasiliana nawe.\n1 Nakubali",
        "privacy_minor": "SISI huhifadhi majibu yako kwa siri. Kuhifadhi kunahitaji "
        "idhini ya mzazi au mlezi. Muuguzi anaweza kusaidia.\n1 Endelea",
        "q1": "Kutoka 0 hadi 10, una maumivu kiasi gani leo? Jibu kwa namba.",
        "q2": "Kutokwa na damu kwako ni kiasi gani?\n1 Hakuna\n2 Matone\n3 Kidogo\n4 Kiasi\n5 Kingi",
        "q3": "Hedhi yako inakujaje?\n1 Kwa utaratibu\n2 Bila utaratibu\n3 Sina uhakika",
        "q4": "Umeshindwa siku ngapi shuleni muhula huu kwa sababu ya hali yako? Jibu kwa namba.",
        "q5": "Unahisi kizunguzungu au kukaribia kuzimia?\n1 Ndio\n2 Hapana",
        "q6": "Unahisi uchovu mkubwa siku nyingi?\n1 Ndio\n2 Hapana",
        "q7": "Hedhi yako huja kwa utaratibu?\n1 Ndio\n2 Hapana\n3 Sina uhakika",
        "q8": "Hali hii imekudumu kwa muda gani?\n1 Chini ya miezi 3\n2 Miezi 3 hadi 6\n3 Zaidi ya miezi 6",
        "q9": "Maumivu yanakuzuia kufanya shughuli za kila siku?\n1 Ndio\n2 Hapana",
        "q10_adult": "Unahisi maumivu wakati au baada ya tendo la ndoa?\n1 Ndio\n2 Hapana\n3 Sipendelei kujibu",
        "q10_minor": "Unahisi maumivu wakati wa kujisaidia haja kubwa?\n1 Ndio\n2 Hapana\n3 Sipendelei kujibu",
        "result_green": "Asante. Endelea kufuatilia siku zako. Muone muuguzi kama hali inaendelea.",
        "result_yellow": "Tafadhali muone muuguzi wa shule utakapoweza. Endelea kufuatilia.",
        "result_orange": "Tafadhali muone muuguzi au daktari hivi karibuni. Usisubiri muda mrefu.",
        "result_red": "Tafadhali tafuta huduma sasa. Usisubiri. Kama muuguzi yuko karibu, nenda sasa.",
        "exit": "Kikao kimeisha. Futa historia ya simu kama simu hii inashirikiwa.",
        "timeout": "Kikao chako kimeisha. Anza tena.",
    },
}
