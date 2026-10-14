package com.sisi.health.engine

/** Client-side field merge — the same conflict rule as the server (spec 2):
 * highest version wins per field, server timestamp breaks ties; nested dicts
 * (symptoms) merge recursively. The server re-runs the same rule on sync, so
 * the local view converges with the authoritative merged view. */
object FieldMerge {

    data class VersionedPayload(val version: Int, val serverTs: Long, val payload: Map<String, Any?>)

    fun merge(versions: List<VersionedPayload>): Map<String, Any?> {
        fun pick(pairs: List<Triple<Int, Long, Any?>>): Any? =
            pairs.sortedWith(compareBy<Triple<Int, Long, Any?>> { it.first }.thenBy { it.second })
                .last().third

        fun mergeAt(pairs: List<Triple<Int, Long, Map<String, Any?>>>): Map<String, Any?> {
            val keys = pairs.flatMap { it.third.keys }.toSet()
            return keys.associateWith { key ->
                val candidates = pairs.mapNotNull { (version, ts, map) ->
                    map[key]?.let { Triple(version, ts, it) }
                }
                val value = pick(candidates)
                if (value is Map<*, *>) {
                    @Suppress("UNCHECKED_CAST")
                    val nested = pairs.mapNotNull { (version, ts, map) ->
                        (map[key] as? Map<String, Any?>)?.let { Triple(version, ts, it) }
                    }
                    mergeAt(nested)
                } else {
                    value
                }
            }
        }

        return mergeAt(versions.map { Triple(it.version, it.serverTs, it.payload) })
    }
}
