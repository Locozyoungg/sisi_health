package com.sisi.health.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sisi.health.R
import com.sisi.health.data.prefs.SettingsStore
import com.sisi.health.vault.VaultManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Settings: privacy vault, decoy mode, low-literacy mode, language, discreet icon.
 * Discreet features are available to ALL users including minors and are never
 * disabled by a guardian (spec 3.2) — there is no guardian control here. */
@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val vault: VaultManager,
    private val settings: SettingsStore,
) : ViewModel() {

    fun setPin(pin: String, onResult: (Result<Unit>) -> Unit) = viewModelScope.launch {
        onResult(vault.setPin(pin))
    }

    fun disableVault(pin: String, onResult: (Boolean) -> Unit) = viewModelScope.launch {
        onResult(vault.disableVault(pin))
    }

    fun setDecoy(enabled: Boolean) {
        settings.decoyMode = enabled
    }

    fun setLowLiteracy(enabled: Boolean) {
        settings.lowLiteracyMode = enabled
    }

    fun setLanguage(language: String) {
        settings.language = language
    }
}

@Composable
fun SettingsScreen(viewModel: SettingsViewModel, settings: SettingsStore) {
    var pin by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<String?>(null) }
    // Strings for callbacks are hoisted here (composable context) so lambdas
    // (non-composable context) never call stringResource directly.
    val pinSetMsg = stringResource(R.string.settings_pin_set)
    val pinInvalidMsg = stringResource(R.string.settings_pin_invalid)
    val vaultDisabledMsg = stringResource(R.string.settings_vault_disabled)
    val wrongPinMsg = stringResource(R.string.vault_wrong_pin)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.nav_settings), style = MaterialTheme.typography.headlineSmall)

        Text(text = stringResource(R.string.settings_privacy_title), style = MaterialTheme.typography.titleMedium)

        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = stringResource(R.string.settings_vault))
                Text(
                    text = stringResource(
                        if (settings.vaultEnabled) R.string.settings_vault_on else R.string.settings_vault_off
                    ),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (!settings.vaultEnabled) {
                OutlinedTextField(
                    value = pin,
                    onValueChange = { if (it.length <= 6 && it.all { c -> c.isDigit() }) pin = it },
                    label = { Text(text = stringResource(R.string.settings_pin_hint)) },
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = {
                    viewModel.setPin(pin) { result ->
                        status = result.fold(
                            onSuccess = { pinSetMsg },
                            onFailure = { pinInvalidMsg },
                        )
                        pin = ""
                    }
                }) {
                    Text(text = stringResource(R.string.settings_enable_vault))
                }
            } else {
                TextButton(onClick = {
                    viewModel.disableVault(pin) { ok ->
                        status = if (ok) vaultDisabledMsg else wrongPinMsg
                        pin = ""
                    }
                }) {
                    Text(text = stringResource(R.string.settings_disable_vault))
                }
            }
        }

        status?.let { Text(text = it, color = MaterialTheme.colorScheme.primary) }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = stringResource(R.string.settings_decoy))
                Text(text = stringResource(R.string.settings_decoy_body), style = MaterialTheme.typography.bodySmall)
            }
            Switch(checked = settings.decoyMode, onCheckedChange = viewModel::setDecoy)
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = stringResource(R.string.settings_low_literacy))
                Text(
                    text = stringResource(R.string.settings_low_literacy_body),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(checked = settings.lowLiteracyMode, onCheckedChange = viewModel::setLowLiteracy)
        }

        Text(text = stringResource(R.string.settings_language), style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("en" to "English", "sw" to "Kiswahili").forEach { (code, label) ->
                TextButton(onClick = { viewModel.setLanguage(code) }) {
                    Text(text = label + if (settings.language == code) " ✓" else "")
                }
            }
        }

        Text(text = stringResource(R.string.settings_disclaimer), style = MaterialTheme.typography.bodySmall)
    }
}
