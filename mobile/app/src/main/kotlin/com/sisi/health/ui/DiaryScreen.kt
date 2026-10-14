package com.sisi.health.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sisi.health.R
import com.sisi.health.data.db.DiaryEntryEntity
import com.sisi.health.data.repo.DiaryRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject

data class DiaryState(val entries: List<DiaryEntryEntity> = emptyList())

@HiltViewModel
class DiaryViewModel @Inject constructor(
    private val repository: DiaryRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DiaryState())
    val state: StateFlow<DiaryState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        _state.value = DiaryState(repository.allEntries())
    }

    fun delete(clientId: String) = viewModelScope.launch {
        // Append-only: clears the symptom content as a new version (server erasure
        // is the true delete path); shared devices keep no residual symptom data.
        repository.clearEntry(clientId)
        refresh()
    }
}

/** Diary list: date, pain, bleeding — icons-first for low-literacy mode. */
@Composable
fun DiaryScreen(viewModel: DiaryViewModel) {
    val state by viewModel.state.collectAsState()
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.nav_diary), style = MaterialTheme.typography.headlineSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(state.entries, key = { it.clientId }) { entry ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        val payload = runCatching {
                            Json.parseToJsonElement(entry.payloadJson).jsonObject
                        }.getOrNull()
                        Text(
                            text = payload?.get("date")?.jsonPrimitive?.content ?: entry.clientId,
                            style = MaterialTheme.typography.titleSmall,
                        )
                        Text(
                            text = buildString {
                                payload?.get("pain")?.jsonPrimitive?.content?.let { append("pain $it/10") }
                                payload?.get("bleeding_volume")?.jsonPrimitive?.content
                                    ?.let { append("  bleeding $it/4") }
                            },
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        TextButton(onClick = { viewModel.delete(entry.clientId) }) {
                            Text(text = stringResource(R.string.diary_delete))
                        }
                    }
                }
            }
        }
    }
}
