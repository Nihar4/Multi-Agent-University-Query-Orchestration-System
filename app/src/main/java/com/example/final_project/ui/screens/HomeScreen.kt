package com.example.final_project.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.ElevatedButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.final_project.ui.AppViewModel

@Composable
fun HomeScreen(
    vm: AppViewModel,
    onOpenChat: () -> Unit,
    onOpenTickets: () -> Unit,
    onLogout: () -> Unit,
) {
    val profile by vm.profile.collectAsState()
    val tickets by vm.tickets.collectAsState()
    val name by vm.userName.collectAsState()

    val statusBarPadding = WindowInsets.statusBars.asPaddingValues().calculateTopPadding()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(start = 20.dp, end = 20.dp, top = statusBarPadding + 20.dp, bottom = 20.dp),
    ) {
        Text(
            "Welcome,",
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            name ?: "Student",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(20.dp))

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Profile", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text("Student #: ${profile?.student_number ?: "—"}")
                Text("Major: ${profile?.major ?: "—"}")
                Text("Year: ${profile?.year ?: "—"}")
                Text("GPA: ${profile?.gpa ?: "—"}")
            }
        }
        Spacer(Modifier.height(16.dp))

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Quick stats", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text("Open tickets: ${tickets.count { it.status == "open" }}")
                Text("Total tickets: ${tickets.size}")
            }
        }
        Spacer(Modifier.height(24.dp))

        ElevatedButton(
            onClick = onOpenChat,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Ask the assistant") }

        Spacer(Modifier.height(8.dp))
        ElevatedButton(
            onClick = onOpenTickets,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("My tickets (${tickets.size})") }

        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onLogout,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Sign out") }

        Spacer(Modifier.height(24.dp))
        Text(
            "Try these:",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "• Why can't I enroll in CS301 for next semester?\n" +
                "• What courses am I still missing for graduation?\n" +
                "• Is there a hold on my account?\n" +
                "• I can't log in to my student portal, please unlock my account.\n" +
                "• What's my meal plan balance?",
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}
