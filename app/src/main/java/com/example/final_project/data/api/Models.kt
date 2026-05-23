package com.example.final_project.data.api

import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class LoginRequest(val email: String, val password: String)

@JsonClass(generateAdapter = true)
data class SignupRequest(
    val email: String,
    val password: String,
    val full_name: String,
    val student_number: String,
    val major: String = "Computer Science",
    val year: Int = 1,
)

@JsonClass(generateAdapter = true)
data class TokenResponse(
    val access_token: String,
    val token_type: String,
    val student_id: Int,
    val full_name: String,
    val email: String,
)

@JsonClass(generateAdapter = true)
data class StudentOut(
    val id: Int,
    val email: String,
    val full_name: String,
    val student_number: String,
    val major: String,
    val year: Int,
    val gpa: Double,
)

@JsonClass(generateAdapter = true)
data class ChatRequest(val message: String)

@JsonClass(generateAdapter = true)
data class ChatResponse(
    val answer: String,
    val routed_to: List<String>,
    val ticket_ids: List<Int> = emptyList(),
    val trace: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class ChatMessageOut(
    val id: Int,
    val role: String,
    val content: String,
    val routed_to: String,
    val ticket_id: Int?,
    val created_at: String,
)

@JsonClass(generateAdapter = true)
data class TicketListItem(
    val id: Int,
    val subject: String,
    val status: String,
    val department: String,
    val department_code: String,
    val created_at: String,
)

@JsonClass(generateAdapter = true)
data class TicketMessageOut(
    val id: Int,
    val sender: String,
    val body: String,
    val created_at: String,
)

@JsonClass(generateAdapter = true)
data class TicketOut(
    val id: Int,
    val subject: String,
    val summary: String,
    val original_question: String,
    val status: String,
    val department: String,
    val department_code: String,
    val created_at: String,
    val updated_at: String,
    val messages: List<TicketMessageOut> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class TicketReplyRequest(val body: String)
