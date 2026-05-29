/**
 * ClaimResultCard — terminal result card shown at the end of a claim.
 *
 * States:
 *   approved      → Green card: voucher code + (edited) compensation amount.
 *                   Used for Lane 1 instant approval AND Lane 2 staff approval.
 *   under_review  → Amber card: reference number + "awaiting agent review".
 *                   Lane 2 before staff act.
 *   rejected      → Red card: reference number + rejection notice.
 *                   Lane 2 after staff reject.
 *
 * Props:
 * @param {1|2}         lane         - Routing lane (1 = instant, 2 = staff review)
 * @param {string}      status       - 'approved' | 'under_review' | 'rejected'
 * @param {string|null} voucherCode  - Voucher code (approved only)
 * @param {string|null} claimId      - CLM-YYYYMMDD-XXXX reference ID
 * @param {number|null} compensation - Final/edited compensation in USD (approved)
 */
export default function ClaimResultCard({
  lane,
  status,
  voucherCode = null,
  claimId = null,
  compensation = null,
}) {
  // Back-compat: if status is missing, infer it from the lane (old callers).
  const resolved = status || (lane === 1 ? 'approved' : 'under_review')

  if (resolved === 'rejected') {
    return (
      <div className="my-3 flex justify-center">
        <div className="w-full max-w-[340px] rounded-2xl border border-red-200 bg-gradient-to-br from-red-50 to-rose-100 p-4 shadow-md">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-2xl">❌</span>
            <div>
              <p className="text-sm font-bold text-red-800">Claim Not Approved</p>
              <p className="text-xs text-red-600">ABC Airline · Staff Review</p>
            </div>
          </div>
          <div className="mb-3 h-px bg-red-200" />
          <div className="space-y-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-red-600">Reference Number</p>
              <p className="font-mono text-sm font-bold text-red-800">{claimId || '—'}</p>
            </div>
            <p className="text-xs text-red-700">
              After reviewing your claim, our team was unable to approve compensation in this case.
              If you believe this is a mistake, please contact our support desk with your reference number.
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (resolved === 'approved') {
    return (
      <div className="my-3 flex justify-center">
        <div className="w-full max-w-[340px] rounded-2xl border border-green-200 bg-gradient-to-br from-green-50 to-emerald-100 p-4 shadow-md">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-2xl">✅</span>
            <div>
              <p className="text-sm font-bold text-green-800">Claim Approved!</p>
              <p className="text-xs text-green-600">
                {lane === 1 ? 'ABC Airline · Instant Approval' : 'ABC Airline · Approved by Staff'}
              </p>
            </div>
          </div>
          <div className="mb-3 h-px bg-green-200" />
          <div className="space-y-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-green-600">Voucher Code</p>
              <p className="font-mono text-lg font-bold tracking-widest text-green-800">
                {voucherCode || '—'}
              </p>
            </div>
            {compensation != null && (
              <div>
                <p className="text-xs uppercase tracking-wide text-green-600">Compensation</p>
                <p className="text-lg font-bold text-green-800">
                  ${Number(compensation).toFixed(2)}
                </p>
              </div>
            )}
            <div>
              <p className="text-xs uppercase tracking-wide text-green-600">Claim Reference</p>
              <p className="font-mono text-sm text-green-700">{claimId || '—'}</p>
            </div>
            <p className="mt-2 text-xs text-green-700">
              💳 Your compensation voucher has been issued. Present this code at any ABC Airline counter or use it when booking online.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // under_review (Lane 2, awaiting staff)
  return (
    <div className="my-3 flex justify-center">
      <div className="w-full max-w-[340px] rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-yellow-100 p-4 shadow-md">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-2xl">🕐</span>
          <div>
            <p className="text-sm font-bold text-amber-800">Claim Under Review</p>
            <p className="text-xs text-amber-600">ABC Airline · Staff Review</p>
          </div>
        </div>
        <div className="mb-3 h-px bg-amber-200" />
        <div className="space-y-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-amber-600">Reference Number</p>
            <p className="font-mono text-sm font-bold text-amber-800">{claimId || '—'}</p>
          </div>
          <p className="text-xs text-amber-700">
            🔍 Our team is reviewing your claim. This page will update automatically once a decision is made — you can keep it open or check back later.
          </p>
          <div className="mt-2 flex items-center gap-1.5 rounded-lg bg-amber-200/60 px-3 py-2">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
            <p className="text-xs font-medium text-amber-800">Awaiting agent review</p>
          </div>
        </div>
      </div>
    </div>
  )
}
