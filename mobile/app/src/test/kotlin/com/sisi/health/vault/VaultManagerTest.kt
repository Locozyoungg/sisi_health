package com.sisi.health.vault

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import com.sisi.health.data.prefs.SettingsStore
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Privacy vault logic (spec 5.1): PIN set/verify/lock, wrong-PIN rejection,
 * and the invariant that nothing in vault state is plaintext. */
@RunWith(RobolectricTestRunner::class)
class VaultManagerTest {

    private lateinit var settings: SettingsStore
    private lateinit var vault: VaultManager

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("sisi_settings", Context.MODE_PRIVATE)
            .edit().clear().commit()
        settings = SettingsStore(context)
        vault = VaultManager(settings)
    }

    @Test
    fun `set pin locks immediately`() {
        vault.setPin("1234")
        assertTrue(settings.vaultEnabled)
        assertTrue(vault.isLocked)
    }

    @Test
    fun `correct pin unlocks, wrong pin does not`() {
        vault.setPin("1234")
        assertFalse(vault.unlock("0000"))
        assertTrue(vault.isLocked)
        assertTrue(vault.unlock("1234"))
        assertFalse(vault.isLocked)
    }

    @Test
    fun `invalid pins are rejected`() {
        assertTrue(vault.setPin("12").isFailure)
        assertTrue(vault.setPin("abcd").isFailure)
        assertTrue(vault.setPin("1234567").isFailure)
        assertFalse(settings.vaultEnabled)
    }

    @Test
    fun `pin is never stored in plaintext`() {
        vault.setPin("1234")
        val raw = ApplicationProvider.getApplicationContext<Context>()
            .getSharedPreferences("sisi_settings", Context.MODE_PRIVATE).all
        assertFalse(raw.values.any { it == "1234" })
    }

    @Test
    fun `disable requires the correct pin`() {
        vault.setPin("1234")
        assertFalse(vault.disableVault("9999"))
        assertTrue(settings.vaultEnabled)
        assertTrue(vault.disableVault("1234"))
        assertFalse(settings.vaultEnabled)
        assertFalse(vault.isLocked)
    }

    @Test
    fun `lock is instant for quick exit`() {
        vault.setPin("1234")
        vault.unlock("1234")
        vault.lock()
        assertTrue(vault.isLocked)
    }
}
