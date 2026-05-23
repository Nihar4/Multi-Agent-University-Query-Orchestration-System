package com.example.final_project.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.final_project.ui.AppViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TicketDetailScreen(
    vm: AppViewModel,
    ticketId: Int,
    onBack: () -> Unit,
) {
    val current by vm.currentTicket.collectAsState()
    var reply by remember { mutableStateOf("") }

    LaunchedEffect(ticketId) { vm.openTicket(ticketId) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ticket #${current?.id ?: ticketId}") },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("Back") }
                },
            )
        }
    ) { inner ->
        val t = current
        if (t == null) {
            Column(Modifier.padding(inner).padding(20.dp)) { Text("Loading…") }
            return@Scaffold
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(inner),
        ) {
            Card(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(t.subject, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        AssistChip(onClick = {}, label = { Text(t.status) })
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(t.department, style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(10.dp))
                    Text("Summary for staff:", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                    Text(t.summary, style = MaterialTheme.typography.bodyMedium)
                }
            }

            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(t.messages) { m ->
                    MessageRow(m.sender, m.body)
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = reply,
                    onValueChange = { reply = it },
                    placeholder = { Text("Reply to the department…") },
                    modifier = Modifier.weight(1f),
                    maxLines = 4,
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    enabled = reply.isNotBlank(),
                    onClick = {
                        val msg = reply.trim()
                        reply = ""
                        vm.replyToCurrentTicket(msg) {}
                    },
                ) { Text("Send") }
            }
        }
    }
}

@Composable
private fun MessageRow(sender: String, body: String) {
    val (label, isLeft) = when (sender) {
        "student" -> "You" to false
        "agent"   -> "AI agent" to true
        else      -> "Department" to true
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isLeft) Arrangement.Start else Arrangement.End,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 320.dp)
                .background(
                    color = if (isLeft) MaterialTheme.colorScheme.surfaceVariant
                    else MaterialTheme.colorScheme.primaryContainer,
                    shape = RoundedCornerShape(14.dp),
                )
                .padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            Text(label, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(2.dp))
            Text(body, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
