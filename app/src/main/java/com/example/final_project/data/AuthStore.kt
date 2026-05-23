package com.example.final_project.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.authDataStore by preferencesDataStore(name = "auth")

object AuthStore {
    private val KEY_TOKEN = stringPreferencesKey("token")
    private val KEY_EMAIL = stringPreferencesKey("email")
    private val KEY_NAME = stringPreferencesKey("name")
    private val KEY_STUDENT_ID = stringPreferencesKey("student_id")

    fun tokenFlow(context: Context): Flow<String?> =
        context.authDataStore.data.map { it[KEY_TOKEN] }

    fun emailFlow(context: Context): Flow<String?> =
        context.authDataStore.data.map { it[KEY_EMAIL] }

    fun nameFlow(context: Context): Flow<String?> =
        context.authDataStore.data.map { it[KEY_NAME] }

    suspend fun save(context: Context, token: String, email: String, name: String, studentId: Int) {
        context.authDataStore.edit {
            it[KEY_TOKEN] = token
            it[KEY_EMAIL] = email
            it[KEY_NAME] = name
            it[KEY_STUDENT_ID] = studentId.toString()
        }
    }

    suspend fun clear(context: Context) {
        context.authDataStore.edit { it.clear() }
    }
}
