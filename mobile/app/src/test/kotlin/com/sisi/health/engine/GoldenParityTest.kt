package com.sisi.health.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import java.io.File

/** Rule source for JVM tests: reads the test-resources copy of /ontology (the same
 * JSON the backend tests use — parity by construction). */
class ClasspathRuleSource : RuleSource {
    private val root = File("src/test/resources/ontology")

    override fun listFiles(dir: String): List<String> =
        File(root, dir).listFiles()?.map { it.name }?.toList() ?: emptyList()

    override fun readText(path: String): String = File(root, path).readText(Charsets.UTF_8)
}

/** DoD: on-device vs server band parity on the golden file. The Kotlin engine MUST
 * produce the same band, indicators, and escalations as the Python engine on every
 * case in ontology/golden/cases.json — a failing case blocks the merge. */
class GoldenParityTest {

    @Test
    fun `kotlin engine matches every golden case exactly like the python engine`() {
        val source = ClasspathRuleSource()
        val engine = RuleSetLoader.buildEngine(source, allowUnvalidated = true)
        val golden = RuleSetLoader.loadGoldenFile(source)
        assertNotNull(golden.cases)

        val failures = mutableListOf<String>()
        for (case in golden.cases) {
            val result = engine.evaluate(
                age = case.age,
                diaryDays = case.diaryDays,
                features = featuresFromJson(case.features),
            )
            if (result.band != case.expectedBand ||
                result.indicators.sorted() != case.expectedIndicators.sorted() ||
                result.urgent != case.expectedEscalations["urgent"] ||
                result.safeguarding != case.expectedEscalations["safeguarding"]
            ) {
                failures += "${case.id}: band=${result.band} (expected ${case.expectedBand}), " +
                    "indicators=${result.indicators}"
            }
        }
        assertEquals("golden parity failures:\n" + failures.joinToString("\n"), 0, failures.size)
        assertEquals(37, golden.cases.size)
    }

    @Test
    fun `engine loads the same rule set as the backend`() {
        val engine = RuleSetLoader.buildEngine(ClasspathRuleSource(), allowUnvalidated = true)
        assertEquals(
            setOf(
                "anemia-risk-flag",
                "endo-indicator",
                "endo-indicator-adult",
                "fibroid-indicator",
                "pcos-indicator",
                "redflag-heavy-bleeding-dizziness",
                "redflag-severe-acute-pain",
                "redflag-self-harm",
                "redflag-postcoital-bleeding",
                "redflag-intermenstrual-bleeding",
                "redflag-postmenopausal-bleeding",
                "redflag-persistent-discharge",
            ),
            engine.ruleIds.toSet(),
        )
    }

    @Test
    fun `all shipped rules are unvalidated with empty sign-off`() {
        val rules = RuleSetLoader.loadRules(ClasspathRuleSource())
        for (rule in rules) {
            assertEquals("${rule.id}: must ship unvalidated", false, rule.clinicallyValidated)
            assertEquals("${rule.id}: reviewer_name must be empty", null, rule.reviewerName)
            assertEquals("${rule.id}: registration must be empty", null, rule.reviewerRegistrationNo)
            assertEquals("${rule.id}: signed_at must be empty", null, rule.signedAt)
        }
    }
}
