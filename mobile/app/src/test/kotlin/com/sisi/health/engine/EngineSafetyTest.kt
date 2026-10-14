package com.sisi.health.engine

import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** Ports of the backend's safety-invariant tests: red-flag asymmetry, age gating,
 * NOT_ENOUGH_DATA, threshold boundaries. A failing test here means the on-device
 * engine has diverged from the server engine. */
class EngineSafetyTest {

    private fun engine(allowUnvalidated: Boolean = true) =
        RuleSetLoader.buildEngine(ClasspathRuleSource(), allowUnvalidated)

    private fun features(vararg pairs: Pair<String, Any?>): Map<String, Any?> =
        mapOf(
            "max_pain_90d" to 1,
            "avg_pain_90d" to 0.5,
            "cyclical_pain_ratio_90d" to 0.1,
            "avg_bleeding_volume_90d" to 0.5,
            "fatigue_ratio_30d" to 0.0,
            "cycle_irregularity_90d" to null,
            "dyschezia" to false,
            "dyspareunia" to false,
            "pelvic_pressure" to false,
            "urinary_frequency" to false,
            "androgenic_symptoms" to false,
            "self_harm_signal" to false,
            "dizziness_signal" to false,
        ) + pairs

    @Test
    fun `missing red-flag input counts as matched`() {
        val result = engine().evaluate(24, 30, features("max_pain_90d" to null))
        assertEquals("RED", result.band)
        assertTrue("redflag-severe-acute-pain" in result.indicators)
        assertTrue(result.urgent)
    }

    @Test
    fun `red flag can never lower a band`() {
        // Mild pattern + severe pain: the band is RED, never downgraded.
        val result = engine().evaluate(24, 30, features("max_pain_90d" to 9))
        assertEquals("RED", result.band)
    }

    @Test
    fun `missing regular input does not match`() {
        val result = engine().evaluate(
            24, 30, features("avg_bleeding_volume_90d" to 3.0, "fatigue_ratio_30d" to null)
        )
        assertFalse("anemia-risk-flag" in result.indicators)
        val pcos = engine().evaluate(
            24, 30, features("cycle_irregularity_90d" to null, "androgenic_symptoms" to true)
        )
        assertFalse("pcos-indicator" in pcos.indicators)
    }

    @Test
    fun `age below 13 is rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            engine().evaluate(12, 30, features())
        }
    }

    @Test
    fun `fewer than 14 diary days returns NOT_ENOUGH_DATA never a band`() {
        val result = engine().evaluate(24, 13, features("max_pain_90d" to 9))
        assertEquals(NOT_ENOUGH_DATA, result.band)
        assertTrue(result.indicators.isEmpty())
    }

    @Test
    fun `exactly 14 diary days evaluates`() {
        val result = engine().evaluate(24, 14, features())
        assertTrue(result.band != NOT_ENOUGH_DATA)
    }

    @Test
    fun `minor never matches the adult dyspareunia rule`() {
        val shared = features(
            "cyclical_pain_ratio_90d" to 0.8,
            "dyschezia" to true,
            "dyspareunia" to true,
        )
        val minor = engine().evaluate(15, 75, shared)
        val adult = engine().evaluate(25, 75, shared)
        assertEquals(listOf("endo-indicator"), minor.indicators)
        assertEquals(listOf("endo-indicator", "endo-indicator-adult"), adult.indicators.sorted())
    }

    @Test
    fun `min_age is inclusive at exactly 18`() {
        val result = engine().evaluate(
            18, 60, features("cyclical_pain_ratio_90d" to 0.8, "dyspareunia" to true)
        )
        assertTrue("endo-indicator-adult" in result.indicators)
    }

    @Test
    fun `unvalidated rules refuse to run without the dev flag`() {
        assertThrows(IllegalArgumentException::class.java) {
            RuleSetLoader.buildEngine(ClasspathRuleSource(), allowUnvalidated = false)
        }
    }

    @Test
    fun `threshold boundaries are inclusive`() {
        val at = engine().evaluate(24, 30, features("avg_bleeding_volume_90d" to 3.0, "fatigue_ratio_30d" to 0.5))
        assertTrue("anemia-risk-flag" in at.indicators)
        val below = engine().evaluate(24, 30, features("avg_bleeding_volume_90d" to 2.9, "fatigue_ratio_30d" to 0.5))
        assertFalse("anemia-risk-flag" in below.indicators)
        assertTrue(
            "redflag-severe-acute-pain" in
                engine().evaluate(24, 30, features("max_pain_90d" to 9)).indicators
        )
        assertFalse(
            "redflag-severe-acute-pain" in
                engine().evaluate(24, 30, features("max_pain_90d" to 8)).indicators
        )
    }

    @Test
    fun `boolean is never coerced into a number comparison`() {
        // Build a synthetic engine: numeric input compared against a boolean value
        // must NOT match (mirrors the backend's bool-vs-number guard).
        val synthetic = Rule(
            id = "t-weird",
            version = "1.0.0",
            condition = "test",
            minAge = 13,
            logic = LogicNode(op = "gte", input = "x", value = JsonPrimitive(true)),
            outputBand = "YELLOW",
        )
        val result = RuleEngine(listOf(synthetic), "test", true)
            .evaluate(20, 30, mapOf("x" to 3))
        assertFalse("t-weird" in result.indicators)
    }
}
