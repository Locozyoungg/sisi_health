package com.sisi.health.core.uuid

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.UUID

/** UUIDv7: version, variant, monotonicity, uniqueness (non-negotiable 6). */
class Uuid7Test {

    @Test
    fun `version and variant are correct`() {
        val value = UUID.fromString(Uuid7.generate())
        assertEquals(7, value.version())
        assertEquals(2, value.variant())
    }

    @Test
    fun `ids are monotonic`() {
        val values = (0 until 500).map { UUID.fromString(Uuid7.generate()) }
        assertTrue(values.zipWithNext().all { (a, b) -> a < b })
    }

    @Test
    fun `ids are unique`() {
        assertEquals(1000, (0 until 1000).map { Uuid7.generate() }.toSet().size)
    }
}
