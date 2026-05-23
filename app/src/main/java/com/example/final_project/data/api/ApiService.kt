package com.example.final_project.data.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {
    @POST("auth/signup")
    suspend fun signup(@Body req: SignupRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body req: LoginRequest): TokenResponse

    @GET("auth/me")
    suspend fun me(@Header("Authorization") bearer: String): StudentOut

    @POST("chat")
    suspend fun chat(
        @Header("Authorization") bearer: String,
        @Body req: ChatRequest,
    ): ChatResponse

    @GET("chat/history")
    suspend fun chatHistory(
        @Header("Authorization") bearer: String,
        @Query("limit") limit: Int = 50,
    ): List<ChatMessageOut>

    @GET("tickets")
    suspend fun listTickets(@Header("Authorization") bearer: String): List<TicketListItem>

    @GET("tickets/{id}")
    suspend fun getTicket(
        @Header("Authorization") bearer: String,
        @Path("id") id: Int,
    ): TicketOut

    @POST("tickets/{id}/reply")
    suspend fun replyTicket(
        @Header("Authorization") bearer: String,
        @Path("id") id: Int,
        @Body req: TicketReplyRequest,
    ): TicketMessageOut
}
