package com.sisi.health.engine

/** The deterministic band engine — a faithful port of backend/app/rules/engine.py.
 * Invariants (all under test, mirrored on the server):
 * - red flags evaluate FIRST; a red-flag match can never lower the band
 * - safety asymmetry: missing/invalid red-flag input counts as matched; for regular
 *   rules it counts as not matched
 * - fewer than 14 diary days -> NOT_ENOUGH_DATA, never a band
 * - users under 13 are rejected
 * - unvalidated rules refuse to run unless the dev flag is on (non-negotiable 3) */
class RuleEngine(
    rules: List<Rule>,
    private val ruleSetVersion: String,
    allowUnvalidated: Boolean,
) {
    private val rules: List<Rule> =
        rules.sortedWith(compareByDescending<Rule> { it.redFlag }.thenByDescending { it.priority })

    init {
        require(allowUnvalidated || rules.none { !it.clinicallyValidated }) {
            "one or more rules lack clinician sign-off; refusing to evaluate"
        }
    }

    val ruleIds: List<String> get() = rules.map { it.id }

    fun evaluate(age: Int, diaryDays: Int, features: Map<String, Any?>): Evaluation {
        require(age >= MIN_AGE) { "users under 13 are blocked" }
        if (diaryDays < MIN_DIARY_DAYS) {
            return Evaluation(NOT_ENOUGH_DATA, emptyList(), false, false, ruleSetVersion)
        }
        val matches = rules.filter { rule ->
            age >= rule.minAge && evalNode(rule.logic, features, rule.redFlag)
        }
        val band = matches.map { Band.valueOf(it.outputBand) }.maxByOrNull { it.severity } ?: Band.GREEN
        return Evaluation(
            band = band.name,
            indicators = matches.map { it.id }.sorted(),
            urgent = matches.any { it.redFlag },
            safeguarding = features["self_harm_signal"] == true ||
                matches.any { it.condition == "self_harm" },
            ruleSetVersion = ruleSetVersion,
        )
    }

    private fun evalNode(node: LogicNode, features: Map<String, Any?>, redFlag: Boolean): Boolean =
        when (node.op) {
            "and" -> node.operands.all { evalNode(it, features, redFlag) }
            "or" -> node.operands.any { evalNode(it, features, redFlag) }
            "not" -> !evalNode(node.operands.first(), features, redFlag)
            else -> compare(node, features, redFlag)
        }

    private fun compare(node: LogicNode, features: Map<String, Any?>, redFlag: Boolean): Boolean {
        val input = node.input ?: throw IllegalArgumentException("comparison node missing input")
        val value = features[input]
        if (value == null) {
            // Safety asymmetry: uncertainty on a red-flag input resolves to matched.
            return redFlag
        }
        return when {
            value is Boolean && node.op in COMPARISON_OPS_FOR_BOOL -> compareScalar(node, value)
            value is Number && value !is Boolean -> compareScalar(node, value)
            else -> redFlag // wrong type: uncertain -> matched only for red flags
        }
    }

    private fun compareScalar(node: LogicNode, value: Any): Boolean {
        fun scalarOf(element: JsonElement?): Any? = when (element) {
            null -> null
            is JsonPrimitive -> when {
                element.isString -> element.content.toDoubleOrNull()
                element.content == "true" -> true
                element.content == "false" -> false
                else -> element.content.toDoubleOrNull()
            }
            else -> null
        }

        return when (node.op) {
            "eq" -> value == scalarOf(node.value)
            "neq" -> value != scalarOf(node.value)
            "in" -> node.values.orEmpty().any { value == scalarOf(it) }
            "between" -> {
                if (value is Number && !value.equals(Unit)) {
                    val lo = node.values?.getOrNull(0)?.let(::scalarOf) as? Number
                    val hi = node.values?.getOrNull(1)?.let(::scalarOf) as? Number
                    lo != null && hi != null && value.toDouble() in lo.toDouble()..hi.toDouble()
                } else {
                    false
                }
            }
            "gte", "gt", "lte", "lt" -> {
                val other = scalarOf(node.value)
                if (value is Number && other is Number) {
                    when (node.op) {
                        "gte" -> value.toDouble() >= other.toDouble()
                        "gt" -> value.toDouble() > other.toDouble()
                        "lte" -> value.toDouble() <= other.toDouble()
                        "lt" -> value.toDouble() < other.toDouble()
                        else -> false
                    }
                } else {
                    false
                }
            }
            else -> false
        }
    }

    private companion object {
        val COMPARISON_OPS_FOR_BOOL = setOf("eq", "neq", "in")
    }
}
