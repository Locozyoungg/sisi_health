package com.sisi.health.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/** The Kotlin feature extractor must produce the SAME features as the backend's
 * compute_features on identical data (parity of parity — the golden band test
 * depends on it). Mirrors backend tests/test_diary_sync.py expectations. */
class FeatureExtractorParityTest {

    private fun record(dayOffset: Long, pain: Int?, bleeding: Int?, fatigue: Boolean? = null,
                       dyschezia: Boolean? = null, dizziness: Boolean? = null,
                       cycleStart: Boolean = false) =
        FeatureExtractor.DiaryRecord(
            date = LocalDate.now().minusDays(dayOffset),
            pain = pain,
            bleedingVolume = bleeding,
            cycleStart = cycleStart,
            fatigue = fatigue,
            dyschezia = dyschezia,
            dyspareunia = null,
            dizziness = dizziness,
            pelvicPressure = null,
            urinaryFrequency = null,
            androgenic = null,
            selfHarm = null,
        )

    @Test
    fun `matches the backend expectations on the same synthetic 25-day diary`() {
        val records = (0 until 25).map { i ->
            record(
                dayOffset = i.toLong(),
                pain = if (i % 5 == 0) 8 else 2,
                bleeding = 3,
                fatigue = i % 2 == 0,
                dyschezia = i % 9 == 0,
                dizziness = i % 11 == 0,
                cycleStart = i % 28 == 0,
            )
        }
        val extracted = FeatureExtractor.extract(records)
        assertEquals(25, extracted.diaryDays)
        assertEquals(8.0, extracted.features["max_pain_90d"])
        assertEquals(3.0, extracted.features["avg_bleeding_volume_90d"])
        assertEquals(true, extracted.features["dyschezia"])
        assertEquals(true, extracted.features["dizziness_signal"])
        assertEquals(0.52, extracted.features["fatigue_ratio_30d"])
        assertNull(extracted.features["cycle_irregularity_90d"]) // only one cycle start
    }

    @Test
    fun `pstdev matches python statistics pstdev`() {
        val values = listOf(2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0)
        // Population std of this list is exactly 2.0.
        assertEquals(2.0, FeatureExtractor.pstdev(values), 1e-9)
    }

    @Test
    fun `cyclical pain ratio counts days near a cycle start`() {
        val start = LocalDate.now().minusDays(10)
        val records = listOf(
            record(10, pain = 5, bleeding = 1, cycleStart = true),
            record(8, pain = 6, bleeding = 1),  // 2 days after start: near
            record(2, pain = 4, bleeding = 1),  // far from start
        )
        val extracted = FeatureExtractor.extract(records)
        assertEquals(2.0 / 3.0, extracted.features["cyclical_pain_ratio_90d"] as Double, 0.01)
        assertTrue(extracted.features["cycle_irregularity_90d"] == null)
    }
}
