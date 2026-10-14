package com.sisi.health.engine

import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.sqrt

/** Deterministic feature extraction — a faithful port of the backend's
 * compute_features so on-device and server produce identical bands on identical
 * data. Keys match the rule schema input names exactly; missing data is null
 * (the engine applies the safety asymmetry). */
object FeatureExtractor {
    const val WINDOW_DAYS = 90L
    const val FATIGUE_WINDOW_DAYS = 30L
    const val CYCLE_NEAR_DAYS = 3L

    data class DiaryRecord(
        val date: LocalDate,
        val pain: Int?,
        val bleedingVolume: Int?,
        val cycleStart: Boolean,
        val fatigue: Boolean?,
        val dyschezia: Boolean?,
        val dyspareunia: Boolean?,
        val dizziness: Boolean?,
        val pelvicPressure: Boolean?,
        val urinaryFrequency: Boolean?,
        val androgenic: Boolean?,
        val selfHarm: Boolean?,
    )

    data class Extracted(val features: Map<String, Any?>, val diaryDays: Int)

    fun extract(records: List<DiaryRecord>): Extracted {
        val today = LocalDate.now()
        val windowStart = today.minusDays(WINDOW_DAYS)
        val fatStart = today.minusDays(FATIGUE_WINDOW_DAYS)
        val recent = records.filter { it.date >= windowStart }

        val diaryDays = recent.map { it.date }.distinct().size
        val pain = recent.mapNotNull { it.pain }
        val bleeding = recent.mapNotNull { it.bleedingVolume }
        val fatigueDays = recent.count { it.date >= fatStart && it.fatigue == true }
        val logged30 = recent.count { it.date >= fatStart }
        val cycleStarts = recent.filter { it.cycleStart }.map { it.date }.sorted()

        val painDays = recent.filter { it.pain != null }.map { it.date }.toSet()
        val nearDays = cycleStarts
            .flatMap { start -> (-CYCLE_NEAR_DAYS..CYCLE_NEAR_DAYS).map { start.plusDays(it) } }
            .toSet()
        val cyclical =
            if (painDays.isEmpty()) null else (painDays intersect nearDays).size.toDouble() / painDays.size

        val gaps = cycleStarts.zipWithNext { a, b ->
            ChronoUnit.DAYS.between(a, b).toDouble()
        }
        val irregularity = if (gaps.size >= 2) pstdev(gaps) else null

        return Extracted(
            features = mapOf(
                "max_pain_90d" to (pain.maxOrNull()?.toDouble()),
                "avg_pain_90d" to pain.takeIf { it.isNotEmpty() }?.let { round(it.average(), 2) },
                "cyclical_pain_ratio_90d" to cyclical?.let { round(it, 2) },
                "avg_bleeding_volume_90d" to bleeding.takeIf { it.isNotEmpty() }?.let { round(it.average(), 2) },
                "fatigue_ratio_30d" to logged30.takeIf { it > 0 }?.let { round(fatigueDays.toDouble() / it, 2) },
                "cycle_irregularity_90d" to irregularity?.let { round(it, 2) },
                "dyschezia" to recent.any { it.dyschezia == true },
                "dyspareunia" to recent.any { it.dyspareunia == true },
                "pelvic_pressure" to recent.any { it.pelvicPressure == true },
                "urinary_frequency" to recent.any { it.urinaryFrequency == true },
                "androgenic_symptoms" to recent.any { it.androgenic == true },
                "self_harm_signal" to recent.any { it.selfHarm == true },
                "dizziness_signal" to recent.any { it.dizziness == true },
            ),
            diaryDays = diaryDays,
        )
    }

    /** Population standard deviation (matches Python statistics.pstdev). */
    fun pstdev(values: List<Double>): Double {
        require(values.isNotEmpty())
        val mean = values.average()
        return sqrt(values.sumOf { (it - mean) * (it - mean) } / values.size)
    }

    private fun round(value: Double, places: Int): Double {
        val factor = 10.0.pow(places)
        return kotlin.math.round(value * factor) / factor
    }
}

private fun Double.pow(n: Int): Double {
    var result = 1.0
    repeat(n) { result *= this }
    return result
}
