import { useState } from 'react'

/**
 * ManualTagEntry — structured form for typing bag-tag details when the
 * passenger has no tag or OCR could not read it (issue #3).
 *
 * Shown above the input bar when the backend sets offer_manual_entry=true.
 * The passenger can also just type the details in chat as free text; this
 * form is the structured alternative.
 *
 * @param {Function} onSubmit({ flight, pnr, bagId }) - submit handler
 * @param {Function} onCancel                          - dismiss the form
 * @param {boolean}  disabled                          - lock while awaiting reply
 */
export default function ManualTagEntry({ onSubmit, onCancel, disabled = false }) {
  const [flight, setFlight] = useState('')
  const [pnr, setPnr] = useState('')
  const [bagId, setBagId] = useState('')

  const canSubmit = !disabled && (flight.trim() || pnr.trim() || bagId.trim())

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-medium text-gray-700">Enter bag tag details</p>
        <button
          onClick={onCancel}
          className="text-xs text-gray-400 hover:text-gray-600"
          aria-label="Cancel manual entry"
        >
          Cancel
        </button>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <input
          type="text"
          value={flight}
          onChange={(e) => setFlight(e.target.value)}
          placeholder="Flight no. (e.g. AI202)"
          disabled={disabled}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-[#128C7E] disabled:opacity-40"
        />
        <input
          type="text"
          value={pnr}
          onChange={(e) => setPnr(e.target.value)}
          placeholder="PNR (6 chars)"
          maxLength={6}
          disabled={disabled}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm uppercase outline-none focus:border-[#128C7E] disabled:opacity-40"
        />
        <input
          type="text"
          value={bagId}
          onChange={(e) => setBagId(e.target.value)}
          placeholder="Bag tag no. (10-12 digits)"
          disabled={disabled}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-[#128C7E] disabled:opacity-40"
        />
      </div>

      <button
        onClick={() => onSubmit({ flight: flight.trim(), pnr: pnr.trim(), bagId: bagId.trim() })}
        disabled={!canSubmit}
        className="mt-2 w-full rounded-md bg-[#075E54] py-2 text-sm font-medium text-white transition-colors hover:bg-[#128C7E] disabled:cursor-not-allowed disabled:opacity-40"
      >
        Submit tag details
      </button>
      <p className="mt-1.5 text-center text-xs text-gray-400">
        You can also just type these details in the chat.
      </p>
    </div>
  )
}
