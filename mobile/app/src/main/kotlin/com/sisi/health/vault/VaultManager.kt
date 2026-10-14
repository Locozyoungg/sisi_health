package com.sisi.health.vault

import com.sisi.health.data.prefs.SettingsStore
import java.security.MessageDigest
import java.security.SecureRandom

/** Privacy vault (spec 5.1): PIN lock, decoy mode, quick-exit state. The PIN is
 * stored only as a salted SHA-256 hash. Guardians can never disable these
 * features for a minor (spec 3.2) — there is no bypass path in code. */
class VaultManager(private val settings: SettingsStore) {

    val isLocked: Boolean get() = settings.vaultEnabled && settings.vaultLocked
    val decoyMode: Boolean get() = settings.decoyMode

    fun setPin(pin: String): Result<Unit> {
        if (pin.length !in 4..6 || pin.any { !it.isDigit() }) {
            return Result.failure(IllegalArgumentException("PIN must be 4-6 digits"))
        }
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        settings.pinSalt = salt.toHex()
        settings.pinHash = hash(pin, salt)
        settings.vaultEnabled = true
        settings.vaultLocked = true
        return Result.success(Unit)
    }

    fun verifyPin(pin: String): Boolean {
        val salt = settings.pinSalt?.hexToBytes() ?: return false
        val expected = settings.pinHash ?: return false
        return MessageDigest.isEqual(expected.toByteArray(), hash(pin, salt).toByteArray())
    }

    fun unlock(pin: String): Boolean {
        if (settings.vaultEnabled && verifyPin(pin)) {
            settings.vaultLocked = false
            return true
        }
        return false
    }

    /** Quick-exit: lock immediately and leave no trace in the task list. */
    fun lock() {
        settings.vaultLocked = true
    }

    fun disableVault(pin: String): Boolean {
        if (verifyPin(pin)) {
            settings.pinHash = null
            settings.pinSalt = null
            settings.vaultEnabled = false
            settings.vaultLocked = false
            return true
        }
        return false
    }

    private fun hash(pin: String, salt: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update(salt)
        return digest.digest(pin.toByteArray(Charsets.UTF_8)).toHex()
    }
}

private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

private fun String.hexToBytes(): ByteArray =
    chunked(2).map { it.toInt(16).toByte() }.toByteArray()
