package com.sisi.health

import android.content.ComponentName
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.sisi.health.data.prefs.SettingsStore
import com.sisi.health.ui.SisiNav
import com.sisi.health.ui.VaultLockScreen
import com.sisi.health.ui.theme.SisiTheme
import com.sisi.health.vault.VaultManager
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/** Privacy by default (spec 5.1): release builds and vault-enabled installs set
 * FLAG_SECURE (no screenshots, blank app-switcher preview). Quick-exit = double
 * back press locks the vault and moves the app off the task list. The vault
 * re-locks whenever the app leaves the foreground. */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var vaultManager: VaultManager

    @Inject
    lateinit var settings: SettingsStore

    private var locked by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        locked = vaultManager.isLocked
        applyScreenProtection()
        setContent {
            SisiTheme(settings = settings) {
                if (locked) {
                    BackHandler { moveTaskToBack(true) }
                    VaultLockScreen(
                        decoyMode = vaultManager.decoyMode,
                        onUnlock = { pin ->
                            if (vaultManager.unlock(pin)) {
                                applyScreenProtection()
                                locked = false
                                true
                            } else {
                                false
                            }
                        },
                    )
                } else {
                    var backPressAt = 0L
                    BackHandler {
                        val now = System.currentTimeMillis()
                        if (now - backPressAt < 600) {
                            vaultManager.lock() // quick-exit: lock + leave no trace
                            moveTaskToBack(true)
                        } else {
                            backPressAt = now
                        }
                    }
                    SisiNav(settings = settings)
                }
            }
        }
    }

    override fun onStop() {
        super.onStop()
        // The vault re-locks whenever the app leaves the foreground.
        if (settings.vaultEnabled) {
            vaultManager.lock()
            locked = true
        }
    }

    private fun applyScreenProtection() {
        if (!BuildConfig.DEBUG || settings.vaultEnabled) {
            window.setFlags(
                WindowManager.LayoutParams.FLAG_SECURE,
                WindowManager.LayoutParams.FLAG_SECURE,
            )
        }
    }

    fun setDiscreetAlias(enabled: Boolean) {
        val alias = ComponentName(this, "com.sisi.health.DiscreetAlias")
        packageManager.setComponentEnabledSetting(
            alias,
            if (enabled) PackageManager.COMPONENT_ENABLED_STATE_ENABLED
            else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
    }
}
