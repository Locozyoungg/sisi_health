package com.sisi.health.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.sisi.health.R

/** Privacy vault lock screen. In decoy mode it presents as a plain "Notes" surface;
 * a long-press on the surface reveals the PIN pad (spec 5.1: decoy mode). */
@Composable
fun VaultLockScreen(decoyMode: Boolean, onUnlock: (String) -> Boolean) {
    var showPin by remember { mutableStateOf(!decoyMode) }
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Column(
            modifier = Modifier.align(Alignment.Center).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (showPin) {
                Text(text = "PIN", style = MaterialTheme.typography.titleMedium)
                PinDots(length = pin.length, error = error)
                if (error) {
                    Text(
                        text = stringResource(R.string.vault_wrong_pin),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                PinPad(
                    onDigit = { digit ->
                        if (pin.length < 6) {
                            pin += digit
                            error = false
                        }
                    },
                    onBackspace = { pin = pin.dropLast(1) },
                    onClear = { pin = "" },
                )
                Spacer(modifier = Modifier.height(8.dp))
                Button(
                    enabled = pin.length >= 4,
                    onClick = {
                        if (!onUnlock(pin)) {
                            error = true
                            pin = ""
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(text = stringResource(R.string.vault_unlock))
                }
            } else {
                // Decoy surface: looks like a plain notes app; long-press reveals PIN.
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(160.dp)
                        .semantics { contentDescription = "Notes" }
                        .pointerInput(Unit) {
                            detectTapGestures(onLongPress = { showPin = true })
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "—",
                        style = MaterialTheme.typography.displayMedium,
                    )
                }
            }
        }
    }
}

@Composable
private fun PinDots(length: Int, error: Boolean) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        repeat(6) { index ->
            Box(
                modifier = Modifier
                    .size(14.dp)
                    .background(
                        color = if (index < length) {
                            if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.surfaceVariant
                        },
                        shape = RoundedCornerShape(50),
                    ),
            )
        }
    }
}

@Composable
private fun PinPad(onDigit: (String) -> Unit, onBackspace: () -> Unit, onClear: () -> Unit) {
    val rows = listOf(
        listOf("1", "2", "3"),
        listOf("4", "5", "6"),
        listOf("7", "8", "9"),
        listOf("⌫", "0", "C"),
    )
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in rows) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (label in row) {
                    OutlinedButton(
                        onClick = {
                            when (label) {
                                "⌫" -> onBackspace()
                                "C" -> onClear()
                                else -> onDigit(label)
                            }
                        },
                        modifier = Modifier
                            .width(72.dp)
                            .semantics { contentDescription = "key $label" },
                    ) {
                        Text(text = label)
                    }
                }
            }
        }
    }
}
