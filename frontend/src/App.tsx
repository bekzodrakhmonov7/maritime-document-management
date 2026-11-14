import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { SkipLink } from './components/layout/SkipLink'
import { AppShell } from './components/layout/AppShell'
import { RoleGate } from './components/RoleGate'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { HomePage } from './pages/HomePage'
import { AccountsPage } from './pages/AccountsPage'
import { VesselsPage } from './pages/VesselsPage'
import { VesselPage } from './pages/VesselPage'
import { PositionsPage } from './pages/PositionsPage'
import { DocumentTypesPage } from './pages/DocumentTypesPage'
import { SeafarersPage } from './pages/SeafarersPage'
import { SeafarerPage } from './pages/SeafarerPage'
import { DocumentPage } from './pages/DocumentPage'
import { SettingsPage } from './pages/SettingsPage'
import { RequirementsPage } from './pages/RequirementsPage'
import { AuditLogPage } from './pages/AuditLogPage'
import { AlertsPage } from './pages/AlertsPage'

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
              <Route index element={<HomePage />} />
              <Route
                path="seafarers"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <SeafarersPage />
                  </RoleGate>
                }
              />
              <Route
                path="seafarers/:id"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <SeafarerPage />
                  </RoleGate>
                }
              />
              <Route
                path="documents/:id"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <DocumentPage />
                  </RoleGate>
                }
              />
              <Route
                path="alerts"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <AlertsPage />
                  </RoleGate>
                }
              />
              <Route
                path="vessels"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <VesselsPage />
                  </RoleGate>
                }
              />
              <Route
                path="vessels/:id"
                element={
                  <RoleGate roles={['administrator', 'crewing_officer']}>
                    <VesselPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/accounts"
                element={
                  <RoleGate roles={['administrator']}>
                    <AccountsPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/document-types"
                element={
                  <RoleGate roles={['administrator']}>
                    <DocumentTypesPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/positions"
                element={
                  <RoleGate roles={['administrator']}>
                    <PositionsPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/requirements"
                element={
                  <RoleGate roles={['administrator']}>
                    <RequirementsPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/settings"
                element={
                  <RoleGate roles={['administrator']}>
                    <SettingsPage />
                  </RoleGate>
                }
              />
              <Route
                path="admin/audit"
                element={
                  <RoleGate roles={['administrator']}>
                    <AuditLogPage />
                  </RoleGate>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
