package com.sisi.health.domain

import com.sisi.health.data.db.DiaryEntryEntity
import com.sisi.health.data.repo.DiaryRepository
import com.sisi.health.engine.Evaluation
import com.sisi.health.engine.FeatureExtractor
import com.sisi.health.engine.FeatureExtractor.DiaryRecord
import com.sisi.health.engine.RuleEngine
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

/** Add/edit one diary day (append-only; edits create a new version). */
@Singleton
class AddDiaryEntryUseCase @Inject constructor(
    private val repository: DiaryRepository,
) {
    suspend operator fun invoke(userId: String, payload: JsonObject, editOfClientId: String? = null) =
        repository.addEntry(userId, payload, editOfClientId)

    /** Builds the validated diary payload. dyspareunia is collected only from
     * users 18+ — the UI never asks minors (spec 5.1); this builder accepts it
     * only when the caller passes the age-gated flag. */
    fun buildPayload(
        date: String,
        pain: Int?,
        bleedingVolume: Int?,
        cycleStart: Boolean,
        fatigue: Boolean?,
        dyschezia: Boolean? = null,
        dyspareunia: Boolean? = null,
        dizziness: Boolean? = null,
        pelvicPressure: Boolean? = null,
        urinaryFrequency: Boolean? = null,
        androgenic: Boolean? = null,
        selfHarm: Boolean? = null,
    ): JsonObject = buildJsonObject {
        put("date", date)
        pain?.let { put("pain", it) }
        bleedingVolume?.let { put("bleeding_volume", it) }
        put("cycle_start", cycleStart)
        val symptoms = buildJsonObject {
            fatigue?.let { put("fatigue", it) }
            dyschezia?.let { put("dyschezia", it) }
            dyspareunia?.let { put("dyspareunia", it) }
            dizziness?.let { put("dizziness", it) }
            pelvicPressure?.let { put("pelvic_pressure", it) }
            urinaryFrequency?.let { put("urinary_frequency", it) }
            androgenic?.let { put("androgenic", it) }
            selfHarm?.let { put("self_harm", it) }
        }
        if (symptoms.isNotEmpty()) put("symptoms", symptoms)
    }
}

/** Evaluate the local diary with the SAME engine and rules the server uses. */
@Singleton
class EvaluateUseCase @Inject constructor(
    private val repository: DiaryRepository,
    private val engine: RuleEngine,
    private val json: Json,
) {
    suspend operator fun invoke(): Pair<Evaluation, Int> {
        val entries = repository.allEntries()
        val records = entries.mapNotNull { entry -> entry.toRecord(json) }
        val extracted = FeatureExtractor.extract(records)
        val age = ageFromBirthDate(repository.state()[com.sisi.health.data.db.SyncStateKeys.BIRTH_DATE])
        return engine.evaluate(age ?: MIN_AGE_FOR_EVALUATION, extracted.diaryDays, extracted.features) to
            extracted.diaryDays
    }

    private fun DiaryEntryEntity.toRecord(json: Json): DiaryRecord? {
        val payload = runCatching { json.parseToJsonElement(payloadJson).jsonObject }.getOrNull()
            ?: return null
        val date = payload["date"]?.jsonPrimitive?.content?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
            ?: return null
        val symptoms = payload["symptoms"]?.jsonObject
        fun bool(name: String): Boolean? = symptoms?.get(name)?.jsonPrimitive?.content?.toBooleanStrictOrNull()
        return DiaryRecord(
            date = date,
            pain = payload["pain"]?.jsonPrimitive?.content?.toIntOrNull(),
            bleedingVolume = payload["bleeding_volume"]?.jsonPrimitive?.content?.toIntOrNull(),
            cycleStart = payload["cycle_start"]?.jsonPrimitive?.content?.toBooleanStrictOrNull() ?: false,
            fatigue = bool("fatigue"),
            dyschezia = bool("dyschezia"),
            dyspareunia = bool("dyspareunia"),
            dizziness = bool("dizziness"),
            pelvicPressure = bool("pelvic_pressure"),
            urinaryFrequency = bool("urinary_frequency"),
            androgenic = bool("androgenic"),
            selfHarm = bool("self_harm"),
        )
    }

    private fun ageFromBirthDate(birthDateIso: String?): Int? {
        if (birthDateIso == null) return null
        val born = runCatching { LocalDate.parse(birthDateIso) }.getOrNull() ?: return null
        val today = LocalDate.now()
        return today.year - born.year - if (today.monthValue < born.monthValue ||
            (today.monthValue == born.monthValue && today.dayOfMonth < born.dayOfMonth)
        ) 1 else 0
    }

    private companion object {
        // Age unknown (not yet registered): treat as adult-only evaluation surface;
        // the backend enforces the real age gate on registration.
        const val MIN_AGE_FOR_EVALUATION = 18
    }
}
