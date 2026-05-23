package com.example.final_project.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.final_project.data.AuthStore
import com.example.final_project.data.api.ChatRequest
import com.example.final_project.data.api.ChatResponse
import com.example.final_project.data.api.LoginRequest
import com.example.final_project.data.api.NetworkModule
import com.example.final_project.data.api.SignupRequest
import com.example.final_project.data.api.StudentOut
import com.example.final_project.data.api.TicketListItem
import com.example.final_project.data.api.TicketOut
import com.example.final_project.data.api.TicketReplyRequest
import com.example.final_project.data.api.bearer
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Single screen-spanning ViewModel. For a small demo this is fine.
 * Split per-screen if it ever grows.
 */
class AppViewModel(app: Application) : AndroidViewModel(app) {

    data class ChatTurn(
        val role: String,                       // "user" | "assistant"
        val text: String,
        val routedTo: List<String> = emptyList(),
        val ticketIds: List<Int> = emptyList(),
    )

    // ---- Auth state ----
    private val _token = MutableStateFlow<String?>(null)
    val token: StateFlow<String?> = _token.asStateFlow()

    private val _userName = MutableStateFlow<String?>(null)
    val userName: StateFlow<String?> = _userName.asStateFlow()

    private val _userEmail = MutableStateFlow<String?>(null)
    val userEmail: StateFlow<String?> = _userEmail.asStateFlow()

    private val _profile = MutableStateFlow<StudentOut?>(null)
    val profile: StateFlow<StudentOut?> = _profile.asStateFlow()

    // ---- Chat state ----
    private val _chatTurns = MutableStateFlow<List<ChatTurn>>(emptyList())
    val chatTurns: StateFlow<List<ChatTurn>> = _chatTurns.asStateFlow()

    private val _chatBusy = MutableStateFlow(false)
    val chatBusy: StateFlow<Boolean> = _chatBusy.asStateFlow()

    // ---- Tickets state ----
    private val _tickets = MutableStateFlow<List<TicketListItem>>(emptyList())
    val tickets: StateFlow<List<TicketListItem>> = _tickets.asStateFlow()

    private val _currentTicket = MutableStateFlow<TicketOut?>(null)
    val currentTicket: StateFlow<TicketOut?> = _currentTicket.asStateFlow()

    // ---- Generic error channel ----
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun clearError() { _error.value = null }

    init {
        // Hydrate token from DataStore on launch
        viewModelScope.launch {
            val ctx = getApplication<Application>().applicationContext
            _token.value = AuthStore.tokenFlow(ctx).first()
            _userName.value = AuthStore.nameFlow(ctx).first()
            _userEmail.value = AuthStore.emailFlow(ctx).first()
            if (_token.value != null) {
                fetchProfile()
                loadTickets()
                loadChatHistory()
            }
        }
    }

    // ---- Auth ops ----

    fun login(email: String, password: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            try {
                val resp = NetworkModule.api.login(LoginRequest(email = email, password = password))
                val ctx = getApplication<Application>().applicationContext
                AuthStore.save(ctx, resp.access_token, resp.email, resp.full_name, resp.student_id)
                _token.value = resp.access_token
                _userName.value = resp.full_name
                _userEmail.value = resp.email
                fetchProfile()
                loadTickets()
                loadChatHistory()
                onSuccess()
            } catch (e: Exception) {
                _error.value = "Login failed: ${e.localizedMessage ?: e.message ?: "unknown error"}"
            }
        }
    }

    fun signup(
        email: String,
        password: String,
        fullName: String,
        studentNumber: String,
        major: String,
        year: Int,
        onSuccess: () -> Unit,
    ) {
        viewModelScope.launch {
            try {
                val resp = NetworkModule.api.signup(
                    SignupRequest(
                        email = email,
                        password = password,
                        full_name = fullName,
                        student_number = studentNumber,
                        major = major,
                        year = year,
                    )
                )
                val ctx = getApplication<Application>().applicationContext
                AuthStore.save(ctx, resp.access_token, resp.email, resp.full_name, resp.student_id)
                _token.value = resp.access_token
                _userName.value = resp.full_name
                _userEmail.value = resp.email
                fetchProfile()
                onSuccess()
            } catch (e: Exception) {
                _error.value = "Signup failed: ${e.localizedMessage ?: e.message ?: "unknown error"}"
            }
        }
    }

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            val ctx = getApplication<Application>().applicationContext
            AuthStore.clear(ctx)
            _token.value = null
            _userName.value = null
            _userEmail.value = null
            _profile.value = null
            _chatTurns.value = emptyList()
            _tickets.value = emptyList()
            _currentTicket.value = null
            onDone()
        }
    }

    private fun fetchProfile() {
        val tok = _token.value ?: return
        viewModelScope.launch {
            runCatching { NetworkModule.api.me(bearer(tok)) }
                .onSuccess { _profile.value = it }
                .onFailure { _error.value = "Couldn't load profile: ${it.localizedMessage}" }
        }
    }

    // ---- Chat ops ----

    fun loadChatHistory() {
        val tok = _token.value ?: return
        viewModelScope.launch {
            runCatching { NetworkModule.api.chatHistory(bearer(tok), limit = 100) }
                .onSuccess { history ->
                    _chatTurns.value = history.map { m ->
                        ChatTurn(
                            role = m.role,
                            text = m.content,
                            // routed_to is a comma-joined string in history rows
                            routedTo = m.routed_to.split(",").map { it.trim() }.filter { it.isNotEmpty() },
                            ticketIds = listOfNotNull(m.ticket_id),
                        )
                    }
                }
                .onFailure { _error.value = "Couldn't load chat history: ${it.localizedMessage}" }
        }
    }

    fun sendChat(message: String) {
        val tok = _token.value ?: return
        if (message.isBlank() || _chatBusy.value) return
        // Optimistically append the user's message
        _chatTurns.value = _chatTurns.value + ChatTurn(role = "user", text = message)
        _chatBusy.value = true
        viewModelScope.launch {
            try {
                val resp: ChatResponse = NetworkModule.api.chat(bearer(tok), ChatRequest(message))
                _chatTurns.value = _chatTurns.value + ChatTurn(
                    role = "assistant",
                    text = resp.answer,
                    routedTo = resp.routed_to,
                    ticketIds = resp.ticket_ids,
                )
                // If any tickets were created, refresh the tickets list
                if (resp.ticket_ids.isNotEmpty()) loadTickets()
            } catch (e: Exception) {
                _chatTurns.value = _chatTurns.value + ChatTurn(
                    role = "assistant",
                    text = "Sorry — something went wrong: ${e.localizedMessage ?: "unknown error"}",
                    routedTo = listOf("error"),
                )
            } finally {
                _chatBusy.value = false
            }
        }
    }

    // ---- Ticket ops ----

    fun loadTickets() {
        val tok = _token.value ?: return
        viewModelScope.launch {
            runCatching { NetworkModule.api.listTickets(bearer(tok)) }
                .onSuccess { _tickets.value = it }
                .onFailure { _error.value = "Couldn't load tickets: ${it.localizedMessage}" }
        }
    }

    fun openTicket(id: Int) {
        val tok = _token.value ?: return
        viewModelScope.launch {
            runCatching { NetworkModule.api.getTicket(bearer(tok), id) }
                .onSuccess { _currentTicket.value = it }
                .onFailure { _error.value = "Couldn't open ticket: ${it.localizedMessage}" }
        }
    }

    fun replyToCurrentTicket(body: String, onSent: () -> Unit) {
        val tok = _token.value ?: return
        val ticket = _currentTicket.value ?: return
        if (body.isBlank()) return
        viewModelScope.launch {
            runCatching {
                NetworkModule.api.replyTicket(bearer(tok), ticket.id, TicketReplyRequest(body))
            }.onSuccess {
                openTicket(ticket.id)  // refresh
                onSent()
            }.onFailure {
                _error.value = "Reply failed: ${it.localizedMessage}"
            }
        }
    }
}
