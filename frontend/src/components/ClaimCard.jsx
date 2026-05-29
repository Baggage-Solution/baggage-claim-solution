import { useEffect, useState } from 'react'

/**
 * ClaimCard — displays a single Lane 2 claim for staff review.
 *
 * Shows: claim metadata, damage photos + bag tag photo (with click-to-enlarge
 * lightbox), severity bar, damage type chips, fraud flags, and action buttons.
 *
 * Photos are fetched from GET /claims/{claim_id}/images on mount and served
 * via the /uploads StaticFiles mount in main.py.
 *
 * @param {Object}   claim         - Claim record from Supabase
 * @param {Function} onDecision    - (claimId, action, modifiedComp?) → void
 * @param {boolean}  isProcessing  - True while POST /decision is in flight
 */
export default function ClaimCard({ claim, onDecision, isProcessing }) {
  const [showModify, setShowModify]       = useState(false)
  const [modifiedAmt, setModifiedAmt]     = useState(claim.compensation ?? 0)
  const [images, setImages]               = useState([])
  const [selectedImage, setSelectedImage] = useState(null)

  // Fetch uploaded photos for this claim on mount
  useEffect(() => {
    fetch(`/claims/${claim.id}/images`)
      .then((r) => r.json())
      .then((data) => setImages(data.images || []))
      .catch(() => {}) // silent — photos are supplementary to text data
  }, [claim.id])

  const damageImages = images.filter((img) => !img.is_tag)
  const tagImages    = images.filter((img) =>  img.is_tag)

  const severityPct   = Math.round((claim.severity_score ?? 0) * 100)
  const severityColor =
    severityPct > 70 ? 'bg-red-500' :
    severityPct > 40 ? 'bg-amber-500' :
                       'bg-green-500'

  return (
    <>
      <div className="overflow-hidden rounded-xl bg-white shadow-md">

        {/* ── Card header ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-bold text-gray-800">
              {claim.id}
            </span>
            {claim.pnr && (
              <span className="text-xs text-gray-400">PNR: {claim.pnr}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {claim.fraud_score > 0 && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                ⚠️ Fraud: {Number(claim.fraud_score).toFixed(2)}
              </span>
            )}
            <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
              🔴 Lane 2
            </span>
          </div>
        </div>

        <div className="px-5 py-4">

          {/* ── Photo gallery ─────────────────────────────────────────── */}
          {images.length > 0 ? (
            <div className="mb-5">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Uploaded Photos
              </p>

              <div className="flex flex-wrap gap-3">

                {/* Damage photos */}
                {damageImages.map((img, i) => (
                  <div key={img.url} className="relative">
                    <img
                      src={img.url}
                      alt={`Damage photo ${i + 1}`}
                      className="h-24 w-24 cursor-zoom-in rounded-lg object-cover shadow ring-2 ring-red-200 transition hover:scale-105 hover:ring-red-500"
                      onClick={() => setSelectedImage(img)}
                      title="Click to enlarge"
                    />
                    <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-red-500 px-1.5 py-0.5 text-[9px] font-bold text-white">
                      Damage {i + 1}
                    </span>
                  </div>
                ))}

                {/* Bag tag photo */}
                {tagImages.map((img, i) => (
                  <div key={img.url} className="relative">
                    <img
                      src={img.url}
                      alt="Bag tag"
                      className="h-24 w-24 cursor-zoom-in rounded-lg object-cover shadow ring-2 ring-blue-200 transition hover:scale-105 hover:ring-blue-500"
                      onClick={() => setSelectedImage(img)}
                      title="Click to enlarge"
                    />
                    <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-blue-500 px-1.5 py-0.5 text-[9px] font-bold text-white">
                      Bag Tag
                    </span>
                  </div>
                ))}

              </div>

              <p className="mt-3 text-xs text-gray-400">
                {damageImages.length} damage photo{damageImages.length !== 1 ? 's' : ''}
                {tagImages.length > 0 && ` · ${tagImages.length} bag tag photo`}
                {' · '}
                <span className="text-gray-300">Click any photo to enlarge</span>
              </p>
            </div>
          ) : (
            <div className="mb-5 rounded-lg bg-gray-50 px-4 py-4 text-center">
              <p className="text-sm text-gray-400">📷 No photos on file for this claim</p>
            </div>
          )}

          {/* ── Stats row ─────────────────────────────────────────────── */}
          <div className="mb-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-400">Brand</p>
              <p className="font-medium text-gray-800">
                {claim.brand || 'Unknown'}
                {claim.is_luxury && (
                  <span className="ml-1 text-xs font-semibold text-purple-600">
                    ✨ Luxury
                  </span>
                )}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-400">
                Compensation
              </p>
              <p className="font-medium text-gray-800">
                ${Number(claim.compensation ?? 0).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-400">Flight</p>
              <p className="font-medium text-gray-800">
                {claim.flight_number || '—'}
              </p>
            </div>
          </div>

          {/* ── Severity bar ──────────────────────────────────────────── */}
          <div className="mb-4">
            <div className="mb-1 flex justify-between">
              <p className="text-xs uppercase tracking-wide text-gray-400">Severity</p>
              <span className="text-xs font-medium text-gray-600">{severityPct}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-gray-200">
              <div
                className={`h-2 rounded-full transition-all ${severityColor}`}
                style={{ width: `${severityPct}%` }}
              />
            </div>
          </div>

          {/* ── Damage types ──────────────────────────────────────────── */}
          {claim.damage_types?.length > 0 && (
            <div className="mb-4">
              <p className="mb-1 text-xs uppercase tracking-wide text-gray-400">
                Damage Types
              </p>
              <div className="flex flex-wrap gap-1">
                {claim.damage_types.map((d, i) => (
                  <span
                    key={i}
                    className="rounded bg-red-50 px-2 py-0.5 text-xs text-red-700"
                  >
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── Fraud flags ───────────────────────────────────────────── */}
          {claim.fraud_flags?.length > 0 && (
            <div className="mb-4 rounded bg-yellow-50 px-3 py-2">
              <p className="text-xs font-medium text-yellow-800">
                ⚠️ Fraud flags: {claim.fraud_flags.join(', ')}
              </p>
            </div>
          )}

          {/* ── Modify compensation ───────────────────────────────────── */}
          {showModify && (
            <div className="mb-4 flex flex-wrap items-center gap-2 rounded bg-blue-50 px-3 py-2">
              <label className="text-sm font-medium text-blue-800">
                New compensation: $
              </label>
              <input
                type="number"
                value={modifiedAmt}
                onChange={(e) => setModifiedAmt(parseFloat(e.target.value))}
                step="0.01"
                min="0"
                className="w-24 rounded border border-blue-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
              <span className="text-xs text-blue-600">
                (was ${Number(claim.compensation ?? 0).toFixed(2)})
              </span>
            </div>
          )}

          {/* ── Action buttons ────────────────────────────────────────── */}
          <div className="flex gap-2 border-t border-gray-100 pt-3">
            <button
              onClick={() =>
                onDecision(claim.id, 'approve', showModify ? modifiedAmt : null)
              }
              disabled={isProcessing}
              className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isProcessing
                ? '⏳ Processing…'
                : showModify
                ? `✅ Approve $${Number(modifiedAmt || 0).toFixed(2)}`
                : '✅ Approve'}
            </button>

            <button
              onClick={() => setShowModify(!showModify)}
              disabled={isProcessing}
              title="Modify compensation amount"
              className={`rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-40 ${
                showModify
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
              }`}
            >
              ✏️
            </button>

            <button
              onClick={() => onDecision(claim.id, 'reject')}
              disabled={isProcessing}
              className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isProcessing ? '⏳ Processing…' : '❌ Reject'}
            </button>
          </div>

        </div>
      </div>

      {/* ── Lightbox overlay ──────────────────────────────────────────────── */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="relative"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={selectedImage.url}
              alt="Enlarged claim photo"
              className="max-h-[85vh] max-w-[90vw] rounded-xl shadow-2xl"
            />

            {/* Caption bar */}
            <div className="mt-2 flex items-center justify-between px-1">
              <p className="text-sm text-gray-300">{selectedImage.filename}</p>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                  selectedImage.is_tag
                    ? 'bg-blue-500 text-white'
                    : 'bg-red-500 text-white'
                }`}
              >
                {selectedImage.is_tag ? 'Bag Tag' : 'Damage Photo'}
              </span>
            </div>

            {/* Close button */}
            <button
              onClick={() => setSelectedImage(null)}
              className="absolute -right-3 -top-3 rounded-full bg-white px-2.5 py-1 text-sm font-bold text-gray-800 shadow-lg hover:bg-gray-100"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  )
}