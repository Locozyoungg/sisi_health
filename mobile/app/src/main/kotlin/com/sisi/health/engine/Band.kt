package com.sisi.health.engine

/** Severity bands. The deterministic engine assigns bands; an LLM never does
 * (non-negotiable 1). Mirrors backend/app/rules/bands.py exactly. */
enum class Band(val severity: Int) {
    GREEN(0),
    YELLOW(1),
    ORANGE(2),
    RED(3),
}

const val NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"
const val MIN_DIARY_DAYS = 14
const val MIN_AGE = 13
const val RULE_SET_VERSION = "ontology-1.1"
