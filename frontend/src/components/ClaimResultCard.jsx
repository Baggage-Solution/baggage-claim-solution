/**
 * ClaimResultCard — terminal result card shown at the end of a claim.
 *
 * Lane 1 (auto-approved):  Green card, voucher code, "claim approved instantly".
 * Lane 2 (staff review):   Amber card, reference number, "under review" status.
 *
 * Sits inside the chat window as the last message — styled to stand out
 * while keeping the WhatsApp aesthetic.
 *
 * @param {1|2}            lane         - Routing lane from A4 decision engine
 * @param {string|null}    voucherCode  - Lane 1 only: the compensation voucher code
 * @param {string|null}    claimId      - CLM-YYYYMMDD-XXXX reference ID from A4
 */
export default function ClaimResultCard({ lane, voucherCode, claimId }) {
  const isLane1 = lane === 1

  return (
    <div className="my-3 flex justify-center">
      <div
        className={`w-full max-w-[340px] rounded-2xl p-4 shadow-md ${
          isLane1
            ? 'border border-green-200 bg-gradient-to-br from-green-50 to-emerald-100'
            : 'border border-amber-200 bg-gradient-to-br from-amber-50 to-yellow-100'
        }`}
      >
        {/* Header row */}
        <div className="mb-3 flex items-center gap-2">
          <span className="text-2xl">{isLane1 ? '✅' : '🕐'}</span>
          <div>
            <p className={`text-sm font-bold ${isLane1 ? 'text-green-800' : 'text-amber-800'}`}>
              {isLane1 ? 'Claim Approved!' : 'Claim Under Review'}
            </p>
            <p className={`text-xs ${isLane1 ? 'text-green-600' : 'text-amber-600'}`}>
              {isLane1 ? 'ABC Airline · Instant Approval' : 'ABC Airline · Staff Review'}
            </p>
          </div>
        </div>

        {/* Divider */}
        <div className={`mb-3 h-px ${isLane1 ? 'bg-green-200' : 'bg-amber-200'}`} />

        {/* Body */}
        {isLane1 ? (
          <div className="space-y-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-green-600">Voucher Code</p>
              <p className="font-mono text-lg font-bold tracking-widest text-green-800">
                {voucherCode || '—'}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-green-600">Claim Reference</p>
              <p className="font-mono text-sm text-green-700">{claimId || '—'}</p>
            </div>
            <p className="mt-2 text-xs text-green-700">
              💳 Your compensation voucher has been issued. Present this code at any ABC Airline counter or use it when booking online.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-amber-600">Reference Number</p>
              <p className="font-mono text-sm font-bold text-amber-800">{claimId || '—'}</p>
            </div>
            <p className="text-xs text-amber-700">
              🔍 Our team is reviewing your claim. You will receive a decision within 24–48 hours. Please save your reference number above.
            </p>
            <div className="mt-2 flex items-center gap-1.5 rounded-lg bg-amber-200/60 px-3 py-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
              <p className="text-xs font-medium text-amber-800">Awaiting agent review</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
