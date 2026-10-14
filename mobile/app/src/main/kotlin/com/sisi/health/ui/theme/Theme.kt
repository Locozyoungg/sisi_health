package com.sisi.health.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Typography
import com.sisi.health.data.prefs.SettingsStore

private val LightColors = lightColorScheme(
    primary = androidx.compose.ui.graphics.Color(0xFF6750A4),
    secondary = androidx.compose.ui.graphics.Color(0xFF625B71),
    tertiary = androidx.compose.ui.graphics.Color(0xFF7D5260),
)

private val DarkColors = darkColorScheme(
    primary = androidx.compose.ui.graphics.Color(0xFFD0BCFF),
    secondary = androidx.compose.ui.graphics.Color(0xFFCCC2DC),
    tertiary = androidx.compose.ui.graphics.Color(0xFFEFB8C8),
)

@Composable
fun SisiTheme(settings: SettingsStore, content: @Composable () -> Unit) {
    val lowLiteracy = settings.lowLiteracyMode
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        typography = if (lowLiteracy) largeTypography() else Typography(),
        content = content,
    )
}

/** Low-literacy mode: larger type throughout (spec 5.1 accessibility). */
private fun largeTypography() = Typography(
    bodyLarge = Typography().bodyLarge.copy(fontSize = 20.sp),
    bodyMedium = Typography().bodyMedium.copy(fontSize = 18.sp),
    bodySmall = Typography().bodySmall.copy(fontSize = 16.sp),
    titleMedium = Typography().titleMedium.copy(fontSize = 22.sp),
    headlineSmall = Typography().headlineSmall.copy(fontSize = 28.sp),
)
