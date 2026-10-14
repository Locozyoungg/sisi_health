package com.sisi.health.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sisi.health.R
import com.sisi.health.data.db.SyncStateKeys
import com.sisi.health.domain.AddDiaryEntryUseCase
import com.sisi.health.domain.EvaluateUseCase
import com.sisi.health.engine.NOT_ENOUGH_DATA
import com.sisi.health.engine.RULE_SET_VERSION
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

data class HomeState(
    val diaryDays: Int = 0,
    val band: String? = null,
    val indicators: List<String> = emptyList(),
    val urgent: Boolean = false,
    val safeguarding: Boolean = false,
    val savedToday: Boolean = false,
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val addEntry: AddDiaryEntryUseCase,
    private val evaluate: EvaluateUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeState())
    val state: StateFlow<HomeState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        val (evaluation, diaryDays) = evaluate()
        _state.value = _state.value.copy(
            diaryDays = diaryDays,
            band = evaluation.band,
            indicators = evaluation.indicators,
            urgent = evaluation.urgent,
            safeguarding = evaluation.safeguarding,
        )
    }

    fun checkIn(
        pain: Int?,
        bleedingVolume: Int?,
        fatigue: Boolean?,
        cycleStart: Boolean,
    ) = viewModelScope.launch {
        val userId = "local-user" // replaced by the synced user id once registered
        val payload = addEntry.buildPayload(
            date = LocalDate.now().toString(),
            pain = pain,
            bleedingVolume = bleedingVolume,
            cycleStart = cycleStart,
            fatigue = fatigue,
        )
        addEntry(userId, payload)
        _state.value = _state.value.copy(savedToday = true)
        refresh()
    }
}

/** Home: the <60-second daily check-in plus the deterministic pattern result.
 * NEVER a diagnosis — the result card says "your pattern suggests" (spec 5.1). */
@Composable
fun HomeScreen(viewModel: HomeViewModel) {
    val state by viewModel.state.collectAsState()
    var pain by remember { mutableIntStateOf(0) }
    var bleeding by remember { mutableIntStateOf(0) }
    var fatigue by remember { mutableStateOf<Boolean?>(null) }
    var cycleStart by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.home_checkin_title), style = MaterialTheme.typography.headlineSmall)

        Card {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = stringResource(R.string.diary_pain) + ": ${pain}/10",
                    modifier = Modifier.semantics { contentDescription = "pain ${pain} out of 10" },
                )
                Slider(
                    value = pain.toFloat(),
                    onValueChange = { pain = it.toInt() },
                    valueRange = 0f..10f,
                )
                Text(text = stringResource(R.string.diary_bleeding) + ": $bleeding")
                Slider(
                    value = bleeding.toFloat(),
                    onValueChange = { bleeding = it.toInt() },
                    valueRange = 0f..4f,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = fatigue == true,
                        onCheckedChange = { fatigue = if (it) true else null },
                    )
                    Text(text = stringResource(R.string.diary_fatigue))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = cycleStart, onCheckedChange = { cycleStart = it })
                    Text(text = stringResource(R.string.diary_cycle_start))
                }
                Button(onClick = { viewModel.checkIn(pain, bleeding, fatigue, cycleStart) }) {
                    Text(text = stringResource(R.string.home_save_checkin))
                }
                if (state.savedToday) {
                    Text(
                        text = stringResource(R.string.home_saved_today),
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }

        Card(
            colors = CardDefaults.cardColors(
                containerColor = bandColor(state.band, state.urgent),
            ),
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.band == null || state.diaryDays < 14) {
                    Text(text = stringResource(R.string.result_not_enough_title), style = MaterialTheme.typography.titleMedium)
                    Text(text = stringResource(R.string.result_not_enough_body))
                    Text(
                        text = stringResource(R.string.result_days_so_far, state.diaryDays),
                        style = MaterialTheme.typography.bodySmall,
                    )
                } else {
                    Text(
                        text = stringResource(R.string.result_band_title, bandLabel(state.band!!)),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (state.indicators.isNotEmpty()) {
                        Text(
                            text = stringResource(R.string.result_pattern_suggests),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            text = state.indicators.joinToString(", "),
                            style = MaterialTheme.typography.bodyLarge,
                        )
                    }
                    if (state.urgent) {
                        Text(
                            text = stringResource(R.string.result_urgent_body),
                            color = MaterialTheme.colorScheme.error,
                        )
                        OutlinedButton(onClick = { /* dials helpline from config */ }) {
                            Text(text = stringResource(R.string.result_helpline))
                        }
                    }
                    Text(text = stringResource(R.string.result_disclaimer), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        Spacer(modifier = Modifier.height(8.dp))
    }
}

private fun bandLabel(band: String): String = when (band) {
    "GREEN" -> "self-care"
    "YELLOW" -> "see a nurse"
    "ORANGE" -> "see a doctor soon"
    "RED" -> "urgent"
    else -> band
}

@Composable
private fun bandColor(band: String?, urgent: Boolean): androidx.compose.ui.graphics.Color =
    when {
        urgent || band == "RED" -> MaterialTheme.colorScheme.errorContainer
        band == "ORANGE" -> MaterialTheme.colorScheme.tertiaryContainer
        band == "YELLOW" -> MaterialTheme.colorScheme.secondaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
