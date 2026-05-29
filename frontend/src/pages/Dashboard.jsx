import { useEffect, useState } from 'react'
import ClaimCard from '../components/ClaimCard.jsx'

/**
 * Dashboard — Lane 2 staff review page.
 *
 * Shows all AWAITING_REVIEW claims from GET /claims/pending.
 * Staff can approve, reject, or modify compensation via POST /decision.
 *
 * The /decision response returns the PERSISTED status, compensation, and
 * voucher code, which we surface in a short confirmation banner so staff can
 * see exactly what was written to the database (including an edited amount).
 *
 * Route: /dashboard
 */
export default function Dashboard() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [processingId, setProcessingId] = useState(null)
  const [toast, setToast] = useState(null) // { kind, text }

  const fetchClaims = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/claims/pending')
      const data = await res.json()
      setClaims(data.claims || [])
    } catch {
      setError('Failed to load claims — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchClaims()
  }, [])

  // Auto-dismiss the toast.
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const handleDecision = async (claimId, action, modifiedCompensation = null) => {
    setProcessingId(claimId)
    try {
      const payload = {
        claim_id: claimId,
        action,
        agent_id: 'AGENT-001', // POC — no auth, hardcoded agent
        ...(modifiedCompensation != null && { modified_compensation: modifiedCompensation }),
      }

      const res = await fetch('/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()

      if (data.status === 'RESOLVED' || data.status === 'REJECTED') {
        // Remove from the pending list — optimistic update.
        setClaims((prev) => prev.filter((c) => c.id !== claimId))

        if (data.status === 'RESOLVED') {
          const amt = data.compensation != null ? `$${Number(data.compensation).toFixed(2)}` : '—'
          setToast({
            kind: 'success',
            text: `✅ ${claimId} approved · ${amt} · voucher ${data.voucher_code || '—'} (saved)`,
          })
        } else {
          setToast({ kind: 'error', text: `❌ ${claimId} rejected (saved)` })
        }
      } else {
        setToast({ kind: 'error', text: data.message || 'Decision failed.' })
      }
    } catch {
      setToast({ kind: 'error', text: 'Decision request failed — is the backend running?' })
    } finally {
      setProcessingId(null)
    }
  }

  return (
    <div className="min-h-screen bg-gray-100">

      {/* ── Header bar ──────────────────────────────────────────────────── */}
      <div className="bg-[#075E54] px-6 py-4 shadow-md">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">
              ABC Airline — Lane 2 Claims Dashboard
            </h1>
            <p className="text-sm text-[#c5e8e2]">Staff review queue</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-red-500 px-3 py-1 text-sm font-bold text-white">
              {claims.length} pending
            </span>
            <button
              onClick={fetchClaims}
              disabled={loading}
              className="rounded-lg bg-white/20 px-3 py-1 text-sm text-white hover:bg-white/30 disabled:opacity-50"
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => {
                // Authorise a one-time session restore on the simulator so the
                // Lane 2 claim (and its decision) is still there when we return.
                // A plain reload of the simulator won't have this flag → clean start.
                try {
                  sessionStorage.setItem('abc_return_to_sim', '1')
                } catch {
                  /* ignore storage errors */
                }
                window.location.href = '/'
              }}
              className="rounded-lg bg-white/20 px-3 py-1 text-sm text-white hover:bg-white/30"
            >
              ← Simulator
            </button>
          </div>
        </div>
      </div>

      {/* ── Confirmation toast ──────────────────────────────────────────── */}
      {toast && (
        <div className="mx-auto mt-4 max-w-4xl px-6">
          <div
            className={`rounded-lg px-4 py-3 text-sm font-medium shadow ${
              toast.kind === 'success'
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}
          >
            {toast.text}
          </div>
        </div>
      )}

      {/* ── Content ─────────────────────────────────────────────────────── */}
      <div className="mx-auto max-w-4xl px-6 py-6">

        {loading && <p className="text-center text-gray-500">Loading claims...</p>}

        {error && (
          <div className="rounded-lg bg-red-50 p-4 text-red-700">{error}</div>
        )}

        {!loading && !error && claims.length === 0 && (
          <div className="rounded-lg bg-white p-10 text-center shadow">
            <p className="text-5xl">✅</p>
            <p className="mt-3 text-lg font-medium text-gray-700">
              No claims awaiting review
            </p>
            <p className="mt-1 text-sm text-gray-400">
              All Lane 2 claims have been processed.
            </p>
          </div>
        )}

        <div className="space-y-4">
          {claims.map((claim) => (
            <ClaimCard
              key={claim.id}
              claim={claim}
              onDecision={handleDecision}
              isProcessing={processingId === claim.id}
            />
          ))}
        </div>

      </div>
    </div>
  )
}
