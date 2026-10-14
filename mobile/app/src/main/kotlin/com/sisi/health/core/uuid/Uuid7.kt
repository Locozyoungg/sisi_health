package com.sisi.health.core.uuid

import java.security.SecureRandom
import java.util.UUID

/** UUIDv7 (RFC 9562), monotonic within the process. Client-generated ids for diary
 * entries so the app can work fully offline (non-negotiable 6: UUIDv7 only). */
object Uuid7 {
    private val random = SecureRandom()
    private var lastTs = 0L
    private var lastRandA = 0

    @Synchronized
    fun generate(): String {
        var ts = System.currentTimeMillis()
        when {
            ts <= lastTs && lastRandA >= 0xFFF -> {
                lastTs += 1
                lastRandA = 0
            }
            ts <= lastTs -> {
                lastRandA += 1
                ts = lastTs
            }
            else -> {
                lastRandA = 0
                lastTs = ts
            }
        }
        val bytes = ByteArray(16)
        var t = ts
        for (i in 5 downTo 0) {
            bytes[i] = (t and 0xFF).toByte()
            t = t shr 8
        }
        bytes[6] = (0x70 or (lastRandA shr 8)).toByte()
        bytes[7] = lastRandA.toByte()
        val randB = ByteArray(8)
        random.nextBytes(randB)
        bytes[8] = (0x80 or (randB[0].toInt() and 0x3F)).toByte()
        System.arraycopy(randB, 1, bytes, 9, 7)
        var msb = 0L
        var lsb = 0L
        for (i in 0..7) msb = (msb shl 8) or (bytes[i].toLong() and 0xFF)
        for (i in 8..15) lsb = (lsb shl 8) or (bytes[i].toLong() and 0xFF)
        return UUID(msb, lsb).toString()
    }
}
