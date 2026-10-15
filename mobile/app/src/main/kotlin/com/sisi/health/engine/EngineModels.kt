package com.sisi.health.engine

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/** Models mirroring ontology/schema/rule.schema.json — the same JSON the backend
 * engine consumes, so on-device and server evaluation can never drift. */

@Serializable
data class RuleInputJson(
    val name: String,
    val type: String,
    val description: String? = null,
)

@Serializable
data class EvidenceJson(
    val title: String,
    @SerialName("source_type") val sourceType: String,
    val organization: String? = null,
    val year: Int? = null,
    val url: String? = null,
    val note: String? = null,
)

@Serializable
data class ChangelogJson(val version: String, val note: String)

@Serializable
data class LogicNode(
    val op: String,
    val operands: List<LogicNode> = emptyList(),
    val input: String? = null,
    val value: JsonElement? = null,
    val values: JsonArray? = null,
)

@Serializable
data class Rule(
    val id: String,
    val version: String,
    val condition: String,
    @SerialName("min_age") val minAge: Int,
    @SerialName("red_flag") val redFlag: Boolean = false,
    val priority: Int = 50,
    val inputs: List<RuleInputJson> = emptyList(),
    val logic: LogicNode,
    @SerialName("output_band") val outputBand: String,
    val evidence: List<EvidenceJson> = emptyList(),
    @SerialName("clinically_validated") val clinicallyValidated: Boolean = false,
    @SerialName("reviewer_name") val reviewerName: String? = null,
    @SerialName("reviewer_registration_no") val reviewerRegistrationNo: String? = null,
    @SerialName("signed_at") val signedAt: String? = null,
    val changelog: List<ChangelogJson> = emptyList(),
)

@Serializable
data class GoldenCase(
    val id: String,
    val description: String,
    val age: Int,
    @SerialName("diary_days") val diaryDays: Int,
    val features: Map<String, JsonElement>,
    @SerialName("expected_band") val expectedBand: String,
    @SerialName("expected_indicators") val expectedIndicators: List<String>,
    @SerialName("expected_escalations") val expectedEscalations: Map<String, Boolean>,
)

@Serializable
data class GoldenFile(val version: String, val description: String, val cases: List<GoldenCase>)

@Serializable
data class RedFlagPattern(
    val id: String,
    val category: String,
    val urgency: String,
    val regex: String,
)

@Serializable
data class RedFlagPatternFile(
    val version: String,
    val language: String,
    val description: String,
    val patterns: List<RedFlagPattern>,
)

data class Evaluation(
    val band: String,
    val indicators: List<String>,
    val urgent: Boolean,
    val safeguarding: Boolean,
    val ruleSetVersion: String,
)

/** Convert JsonElement feature values to plain Kotlin values (Boolean/Double/String/
 * nested maps), matching the feature dicts the backend produces. */
fun JsonElement.toAny(): Any? = when (this) {
    is JsonPrimitive -> when {
        isString -> content
        content == "true" -> true
        content == "false" -> false
        else -> doubleOrNull
    }
    is JsonObject -> entries.associate { (key, value) -> key to value.toAny() }
    is JsonArray -> map { it.toAny() }
    JsonNull -> null
}

fun featuresFromJson(features: Map<String, JsonElement>): Map<String, Any?> =
    features.mapValues { (_, value) -> value.toAny() }
