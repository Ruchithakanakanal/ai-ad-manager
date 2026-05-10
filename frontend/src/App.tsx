import { Routes, Route, Navigate } from 'react-router-dom'

import { AuthProvider } from './context/AuthContext'

import { ProtectedRoute } from './components/ProtectedRoute'

import { LoginPage } from './pages/LoginPage'

import { DashboardLayout } from './pages/DashboardLayout'

import { OverviewPage } from './pages/OverviewPage'

import { CampaignsPage } from './pages/CampaignsPage'

import { CampaignDetailPage } from './pages/CampaignDetailPage'

import { AlertsPage } from './pages/AlertsPage'

import { CreateCampaignPage } from './pages/CreateCampaignPage'

export function App() {

  return (

    <AuthProvider>

      <Routes>

        {/* Default */}
        <Route
          path="/"
          element={<Navigate to="/login" replace />}
        />

        {/* Login */}
        <Route
          path="/login"
          element={<LoginPage />}
        />

        {/* Protected */}
        <Route element={<ProtectedRoute />}>

          <Route element={<DashboardLayout />}>

            <Route
              path="/dashboard"
              element={<OverviewPage />}
            />

            <Route
              path="/dashboard/campaigns"
              element={<CampaignsPage />}
            />

            <Route
              path="/dashboard/campaigns/:id"
              element={<CampaignDetailPage />}
            />

            <Route
              path="/dashboard/alerts"
              element={<AlertsPage />}
            />

            <Route
              path="/dashboard/create-campaign"
              element={<CreateCampaignPage />}
            />

          </Route>

        </Route>

        {/* Fallback */}
        <Route
          path="*"
          element={<Navigate to="/login" replace />}
        />

      </Routes>

    </AuthProvider>

  )
}