package com.sisi.health.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.sisi.health.R
import com.sisi.health.data.prefs.SettingsStore

sealed class SisiDestination(val route: String, val labelRes: Int) {
    data object Home : SisiDestination("home", R.string.nav_home)
    data object Diary : SisiDestination("diary", R.string.nav_diary)
    data object Settings : SisiDestination("settings", R.string.nav_settings)
}

@Composable
fun SisiNav(settings: SettingsStore) {
    val navController = rememberNavController()
    val destinations = listOf(SisiDestination.Home, SisiDestination.Diary, SisiDestination.Settings)
    Scaffold(
        bottomBar = {
            NavigationBar {
                val backStack by navController.currentBackStackEntryAsState()
                val current = backStack?.destination
                destinations.forEach { destination ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == destination.route } == true,
                        onClick = {
                            navController.navigate(destination.route) {
                                popUpTo(navController.graph.startDestinationId) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(imageVector = destination.icon(), contentDescription = null) },
                        label = { Text(text = stringResource(destination.labelRes)) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = SisiDestination.Home.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(SisiDestination.Home.route) { HomeScreen(hiltViewModel()) }
            composable(SisiDestination.Diary.route) { DiaryScreen(hiltViewModel()) }
            composable(SisiDestination.Settings.route) { SettingsScreen(hiltViewModel(), settings) }
        }
    }
}

private fun SisiDestination.icon() = when (this) {
    SisiDestination.Home -> androidx.compose.material.icons.Icons.Default.Home
    SisiDestination.Diary -> androidx.compose.material.icons.Icons.Default.DateRange
    SisiDestination.Settings -> androidx.compose.material.icons.Icons.Default.Settings
}
