package com.example.final_project.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.final_project.ui.screens.ChatScreen
import com.example.final_project.ui.screens.HomeScreen
import com.example.final_project.ui.screens.LoginScreen
import com.example.final_project.ui.screens.SignupScreen
import com.example.final_project.ui.screens.TicketDetailScreen
import com.example.final_project.ui.screens.TicketsScreen

object Routes {
    const val LOGIN = "login"
    const val SIGNUP = "signup"
    const val HOME = "home"
    const val CHAT = "chat"
    const val TICKETS = "tickets"
    const val TICKET_DETAIL = "ticket/{id}"
    fun ticketDetail(id: Int) = "ticket/$id"
}

@Composable
fun AppNav() {
    val nav = rememberNavController()
    val vm: AppViewModel = viewModel()
    val token by vm.token.collectAsState()

    val startDest = if (token != null) Routes.HOME else Routes.LOGIN

    NavHost(navController = nav, startDestination = startDest) {

        composable(Routes.LOGIN) {
            LoginScreen(
                vm = vm,
                onLoggedIn = {
                    nav.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onGoToSignup = { nav.navigate(Routes.SIGNUP) },
            )
        }

        composable(Routes.SIGNUP) {
            SignupScreen(
                vm = vm,
                onSignedUp = {
                    nav.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onGoToLogin = { nav.popBackStack() },
            )
        }

        composable(Routes.HOME) {
            HomeScreen(
                vm = vm,
                onOpenChat = { nav.navigate(Routes.CHAT) },
                onOpenTickets = { nav.navigate(Routes.TICKETS) },
                onLogout = {
                    vm.logout {
                        nav.navigate(Routes.LOGIN) {
                            popUpTo(0) { inclusive = true }
                        }
                    }
                },
            )
        }

        composable(Routes.CHAT) {
            ChatScreen(
                vm = vm,
                onBack = { nav.popBackStack() },
                onOpenTicket = { id -> nav.navigate(Routes.ticketDetail(id)) },
            )
        }

        composable(Routes.TICKETS) {
            TicketsScreen(
                vm = vm,
                onBack = { nav.popBackStack() },
                onOpenTicket = { id -> nav.navigate(Routes.ticketDetail(id)) },
            )
        }

        composable(Routes.TICKET_DETAIL) { entry ->
            val id = entry.arguments?.getString("id")?.toIntOrNull() ?: 0
            TicketDetailScreen(
                vm = vm,
                ticketId = id,
                onBack = { nav.popBackStack() },
            )
        }
    }
}
