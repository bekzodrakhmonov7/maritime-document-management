import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { SkipLink } from './components/layout/SkipLink'
import { AppShell } from './components/layout/AppShell'
import { RoleGate } from './components/RoleGate'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { DashboardPage } from './pages/DashboardPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { VesselsPage } from './pages/VesselsPage'
import { SeafarersPage } from './pages/SeafarersPage'
import { AlertsPage } from './pages/AlertsPage'
import { ReportsPage } from './pages/ReportsPage'
import { AdminConfigPage } from './pages/AdminConfigPage'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <SkipLink />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route
                path="dashboard"
                element={<DashboardPage />}
              />
              <Route
                path="vessels"
                element={<VesselsPage />}
              />
              <Route
                path="seafarers"
                element={<SeafarersPage />}
              />
              <Route
                path="documents"
                element={<DocumentsPage />}
              />
              <Route
                path="alerts"
                element={<AlertsPage />}
              />
              <Route
                path="reports"
                element={<ReportsPage />}
              />
              <Route
                path="admin/config"
                element={
                  <RoleGate roles={['administrator']}>
                    <AdminConfigPage />
                  </RoleGate>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
