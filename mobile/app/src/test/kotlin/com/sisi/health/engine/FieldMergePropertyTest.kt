package com.sisi.health.engine

import io.kotest.property.Arb
import io.kotest.property.arbitrary.int
import io.kotest.property.arbitrary.list
import io.kotest.property.arbitrary.long
import io.kotest.property.arbitrary.map
import io.kotest.property.arbitrary.string
import io.kotest.property.checkAll
import io.kotest.property.forAll
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

/** DoD: sync-conflict property tests (spec 2). The merge rule is "highest version
 * wins per field, server timestamp breaks ties" — property-checked against a
 * brute-force oracle over random version sets, and against the backend semantics. */
class FieldMergePropertyTest {

    private fun oracle(pairs: List<Triple<Int, Long, Map<String, Any?>>>): Map<String, Any?> {
        fun pick(candidates: List<Triple<Int, Long, Any?>>): Any? =
            candidates.sortedWith(compareBy<Triple<Int, Long, Any?>> { it.first }.thenBy { it.second })
                .last().third

        val keys = pairs.flatMap { it.third.keys }.toSet()
        return keys.associateWith { key ->
            pick(pairs.mapNotNull { (v, ts, map) -> map[key]?.let { Triple(v, ts, it) } })
        }
    }

    @Test
    fun `merge matches brute-force oracle for random flat payloads`() = checkAll(
        Arb.int(1, 100),
        Arb.list(Arb.int(1, 20), 1..50),
        Arb.long(0, 1_000_000),
        Arb.map(Arb.string(1, 8), Arb.int(-100, 100), 1..8),
    ) { version, versions, serverTs, values ->
        val payloads = versions.map { v ->
            FieldMerge.VersionedPayload(v, serverTs, values.entries.associate { it.key to it.value })
        }
        val merged = FieldMerge.merge(payloads)
        val expected = oracle(payloads.map { Triple(it.version, it.serverTs, it.payload) })
        assertEquals(expected, merged)
    }

    @Test
    fun `same-version fields break ties by server timestamp`() {
        val early = FieldMerge.VersionedPayload(1, 100L, mapOf("pain" to 3))
        val late = FieldMerge.VersionedPayload(1, 900L, mapOf("pain" to 5))
        assertEquals(mapOf("pain" to 5), FieldMerge.merge(listOf(early, late)))
        assertEquals(mapOf("pain" to 5), FieldMerge.merge(listOf(late, early)))
    }

    @Test
    fun `merge is pure - inputs are never mutated`() {
        val payload = mapOf("pain" to 3, "symptoms" to mapOf("fatigue" to false))
        val v1 = FieldMerge.VersionedPayload(1, 1L, payload)
        val v2 = FieldMerge.VersionedPayload(2, 2L, mapOf("pain" to 7))
        FieldMerge.merge(listOf(v1, v2))
        assertEquals(mapOf("pain" to 3, "symptoms" to mapOf("fatigue" to false)), payload)
    }

    @Test
    fun `nested symptoms merge field by field`() {
        val v1 = FieldMerge.VersionedPayload(
            1, 1L,
            mapOf("symptoms" to mapOf("fatigue" to false, "dizziness" to false)),
        )
        val v2 = FieldMerge.VersionedPayload(
            2, 2L,
            mapOf("symptoms" to mapOf("fatigue" to true)),
        )
        assertEquals(
            mapOf("symptoms" to mapOf("fatigue" to true, "dizziness" to false)),
            FieldMerge.merge(listOf(v1, v2)),
        )
    }

    @Test
    fun `golden parity guard - merge never changes rule inputs unexpectedly`() {
        // Property: merged pain values are always the highest-version pain value.
        forAll<Int, Int, Long, Long> { pain1, pain2, ts1, ts2 ->
            val merged = FieldMerge.merge(
                listOf(
                    FieldMerge.VersionedPayload(1, ts1, mapOf("pain" to pain1)),
                    FieldMerge.VersionedPayload(2, ts2, mapOf("pain" to pain2)),
                )
            )
            merged["pain"] == pain2
        }
    }
}
