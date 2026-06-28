// P-009 — Simulator feature flag
// Root App component. Routes:
//   /            → Simulator (gated on VITE_ENABLE_SIMULATOR)
//   /simulator   → Simulator (alias, also gated)
//   /dashboard   → Dashboard (ALWAYS available — airline ops staff route)
//
// When VITE_ENABLE_SIMULATOR=false (production build):
//   / and /simulator → <SimulatorDisabledPage />
//
// When VITE_ENABLE_SIMULATOR=true (local dev):
//   / and /simulator → full simulator
//   A "DEV MODE — Simulator Active" banner is shown at the top of simulator pages.
//
// The simulator JSX is NOT deleted — it is kept for offline debugging and demos.
// Author: Anoushka (unified branch — P-009)

import { useState } from 'react'
import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom'
import ChatHeader from './components/ChatHeader.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ImageUploadPreview from './components/ImageUploadPreview.jsx'
import ManualTagEntry from './components/ManualTagEntry.jsx'
import { useClaimFlow } from './hooks/useClaimFlow.js'
import Dashboard from './pages/Dashboard.jsx'
import Simulator from './pages/Simulator.jsx'

// ── Feature flag — set VITE_ENABLE_SIMULATOR=true in .env.local for dev ────
const SIMULATOR_ENABLED = import.meta.env.VITE_ENABLE_SIMULATOR === 'true'

// ── DEV MODE banner — shown at top of simulator pages when active ─────────────
function DevModeBanner() {
  return (
    <div className="w-full bg-yellow-400 py-1 text-center text-xs font-bold text-yellow-900">
      ⚠ DEV MODE — Simulator Active — Not for production use
    </div>
  )
}

// ── Simulator Disabled page — shown when ENABLE_SIMULATOR=false ──────────────
function SimulatorDisabledPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-800 text-white">
      <div className="rounded-2xl bg-gray-700 p-8 text-center shadow-2xl">
        <div className="mb-4 text-5xl">🔒</div>
        <h1 className="mb-2 text-xl font-bold">Simulator Disabled</h1>
        <p className="mb-4 text-sm text-gray-400">
          The WhatsApp simulator is not available in this environment.
        </p>
        <a
          href="/dashboard"
          className="inline-block rounded-full bg-[#075E54] px-6 py-2 text-sm font-semibold text-white hover:bg-[#128C7E]"
        >
          Go to Dashboard →
        </a>
      </div>
    </div>
  )
}

// ── Standalone root simulator (/) — legacy route kept for backwards compat ────
function RootSimulator() {
  const [inputValue, setInputValue] = useState('')

  const {
    messages,
    step,
    isLoading,
    claimResult,
    pendingImages,
    inputDisabled,
    showManualEntry,
    setShowManualEntry,
    handleSendText,
    handleSendImages,
    submitManualTag,
    handleFileSelect,
    removePendingImage,
    resetClaim,
  } = useClaimFlow()

  const onSend = async () => {
    if (inputDisabled || isLoading) return
    if (pendingImages.length > 0) {
      await handleSendImages(inputValue.trim())
      setInputValue('')
    } else if (inputValue.trim()) {
      await handleSendText(inputValue.trim())
      setInputValue('')
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  const isFinished =
    claimResult &&
    (claimResult.lane === 1 ||
      claimResult.status === 'approved' ||
      claimResult.status === 'rejected')

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-gray-700 py-6">
      {/* DEV MODE banner — visible reminder that this is the simulator */}
      {SIMULATOR_ENABLED && <DevModeBanner />}

      {/* Toolbar above the phone */}
      <div className="flex w-[400px] items-center justify-between px-1">
        <a
          href="/dashboard"
          className="rounded-full bg-black/30 px-3 py-1 text-xs font-medium text-white hover:bg-black/50"
        >
          Dashboard →
        </a>
        <span className="rounded-full bg-black/30 px-3 py-1 text-xs font-medium text-white">
          step: {step}
        </span>
      </div>

      <div className="relative flex h-[700px] w-[400px] flex-col overflow-hidden rounded-2xl shadow-2xl">
        <ChatHeader />

        <ChatWindow messages={messages} isLoading={isLoading} claimResult={claimResult} />

        {showManualEntry && !inputDisabled && (
          <ManualTagEntry
            onSubmit={submitManualTag}
            onCancel={() => setShowManualEntry(false)}
            disabled={isLoading}
          />
        )}

        <ImageUploadPreview files={pendingImages} onRemove={removePendingImage} />

        {isFinished ? (
          <div className="bg-[#F0F0F0] px-3 py-3">
            <button
              onClick={resetClaim}
              className="w-full rounded-full bg-[#075E54] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#128C7E]"
            >
              Start a new claim
            </button>
          </div>
        ) : (
          <ChatInput
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onSend={onSend}
            onKeyDown={onKeyDown}
            onFileSelect={handleFileSelect}
            disabled={inputDisabled || isLoading}
            hasPendingImages={pendingImages.length > 0}
          />
        )}
      </div>
    </div>
  )
}

/**
 * App — top-level router.
 *
 * Route table:
 *   /            → RootSimulator (if SIMULATOR_ENABLED) or SimulatorDisabledPage
 *   /simulator   → Simulator page (if SIMULATOR_ENABLED) or SimulatorDisabledPage
 *   /dashboard   → Dashboard (always — airline ops production route)
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Root — simulator or disabled page */}
        <Route
          path="/"
          element={SIMULATOR_ENABLED ? <RootSimulator /> : <SimulatorDisabledPage />}
        />

        {/* /simulator — same gate */}
        <Route
          path="/simulator"
          element={
            SIMULATOR_ENABLED ? (
              <div className="flex min-h-screen flex-col">
                {SIMULATOR_ENABLED && <DevModeBanner />}
                <Simulator />
              </div>
            ) : (
              <SimulatorDisabledPage />
            )
          }
        />

        {/* /dashboard — ALWAYS available, no gate */}
        <Route path="/dashboard" element={<Dashboard />} />

        {/* Catch-all → root */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}