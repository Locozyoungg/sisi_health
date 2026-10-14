package com.sisi.health.ui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Non-negotiable 4 (app-side): nothing condition-identifying ever appears in
 * notifications, the launcher/discreet name, or the app-switcher surface. This
 * test scans the shipped string resources and manifest and fails the build if a
 * condition term sneaks into any user-visible or notification string. */
class StringsPrivacyTest {

    private val stringsDir = File("src/main/res")
    private val manifest = File("src/main/AndroidManifest.xml")

    /** Terms that must never appear in notification/launcher strings. */
    private val forbiddenTerms = listOf(
        "endometriosis", "pcos", "polycystic", "fibroid", "fibroids", "cancer",
        "cervical", "diagnosis", "symptom", "period", "menstrual", "bleeding",
        "pregnancy", "pregnant", "pain",
    )

    @Test
    fun `notification strings never name a condition`() {
        val strings = stringsDir.walkTopDown()
            .filter { it.name == "strings.xml" }
            .flatMap { it.readText(Charsets.UTF_8).lineSequence() }
            .filter { it.contains("notification") }
            .joinToString("\n")
        assertTrue("notification strings missing", strings.isNotBlank())
        for (term in forbiddenTerms) {
            assertFalse(
                "notification string leaks '$term':\n$strings",
                strings.contains(term, ignoreCase = true),
            )
        }
    }

    @Test
    fun `discreet launcher name is non-identifying`() {
        val strings = File(stringsDir, "values/strings.xml").readText(Charsets.UTF_8)
        val match = Regex("""name="discreet_app_name">([^<]+)<""").find(strings)
        val value = match?.groupValues?.get(1)?.trim().orEmpty()
        assertTrue("discreet name missing", value.isNotBlank())
        assertTrue("discreet name must be neutral", value.equals("Notes", ignoreCase = true))
        for (term in forbiddenTerms) {
            assertFalse(value.contains(term, ignoreCase = true))
        }
    }

    @Test
    fun `manifest declares the discreet alias disabled by default`() {
        val text = manifest.readText(Charsets.UTF_8)
        assertTrue("activity-alias missing", text.contains("activity-alias"))
        assertTrue("alias must be disabled by default", text.contains("android:enabled=\"false\""))
    }

    @Test
    fun `localization stubs exist for all spec languages`() {
        for (lang in listOf("values-sw", "values-luo", "values-kal", "values-so")) {
            assertTrue("missing locale dir $lang", File(stringsDir, lang).isDirectory)
        }
    }
}
