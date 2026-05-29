import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * useClaimFlow — manages the full baggage claim conversation.
 *
 * State is echoed back to the backend each turn (LangGraph MemorySaver does not
 * persist plain dataclass fields between ainvoke calls).
 *
 * Session restore semantics (intentional):
 *   - The session snapshot is written to sessionStorage on every change.
 *   - It is ONLY restored when the user arrives from the dashboard. The
 *     Dashboard sets a one-time flag (RETURN_FLAG) in sessionStorage right
 *     before it navigates to the simulator. On load the hook restores the
 *     snapshot only if that flag is present, then immediately consumes it.
 *   - A fresh page load, a manual refresh, or a server (uvicorn) restart has
 *     NO flag, so the simulator starts clean with the greeting — which is the
 *     behaviour we want. (The snapshot is also cleared on a clean start.)
 *
 * Lane 2 resolution:
 *   - When a claim is routed to Lane 2 ("under review"), the hook polls
 *     GET /claims/{id}/status. Once staff approve/reject in the dashboard, the
 *     card flips to approved (green, voucher + edited compensation) or rejected
 *     (red). Returning to the simulator from the dashboard restores this claim
 *     so the decision is visible.
 */

const BACKEND = 'http://localhost:8000'
const STORAGE_KEY = 'abc_claim_session_v1'
// Set by the Dashboard immediately before it navigates back to the simulator.
// Its presence is what authorises a one-time session restore.
const RETURN_FLAG = 'abc_return_to_sim'
const POLL_INTERVAL_MS = 4000

function makeSessionId() {
  return `sim-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function nowTime() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function botMsg(text, extra = {}) {
  return { id: crypto.randomUUID(), sender: 'bot', text, timestamp: nowTime(), ...extra }
}

function userMsg(text, extra = {}) {
  return { id: crypto.randomUUID(), sender: 'user', text, timestamp: nowTime(), ...extra }
}

const GREETING = botMsg(
  '👋 Hello! I\'m the ABC Airline baggage claim assistant. I\'m here to help you file a damage claim quickly — no queues, no paperwork.\n\nCould you please briefly describe what happened to your bag?',
)

const DEFAULT_ECHO = {
  conversation_ended: false,
  no_damage_detected: false,
  not_a_bag: false,
  last_object_description: null,
  non_bag_attempts: 0,
  tag_in_damage_photo: false,
  tag_candidate_paths: [],
  processed_damage_paths: [],
  damage_types: [],
  severity_score: 0.0,
  brand_detected: null,
  is_luxury: false,
  compensation_estimate_usd: 0.0,
  processed_tag_paths: [],
  flight_number: null,
  pnr: null,
  bag_id: null,
  ocr_confidence: 0.0,
  tag_data_complete: false,
  tag_manually_entered: false,
  offer_manual_entry: false,
}

// ── sessionStorage helpers ──────────────────────────────────────────────────
//
// loadPersisted() restores the snapshot ONLY if the dashboard set the one-time
// return flag. This is what makes "Dashboard → Simulator" keep the session while
// a fresh load / refresh / server restart starts clean.
function loadPersisted() {
  try {
    const returning = sessionStorage.getItem(RETURN_FLAG) === '1'
    // The flag is one-shot — consume it so a later manual refresh starts clean.
    sessionStorage.removeItem(RETURN_FLAG)

    if (!returning) {
      // Not arriving from the dashboard → discard any stale snapshot, start fresh.
      sessionStorage.removeItem(STORAGE_KEY)
      return null
    }

    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function clearPersisted() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export function useClaimFlow({ airport = null, terminal = null } = {}) {
  // Restore any persisted session once, synchronously, so first render is correct.
  const persisted = useRef(loadPersisted()).current

  const sessionId = useRef(persisted?.sessionId || makeSessionId())
  const claimIdRef = useRef(persisted?.claimId || null)
  const conversationHistory = useRef(persisted?.conversationHistory || [])
  const allUploadedPaths = useRef(persisted?.allUploadedPaths || [])
  const echoedState = useRef(persisted?.echoedState || { ...DEFAULT_ECHO })

  const [messages, setMessages] = useState(persisted?.messages?.length ? persisted.messages : [GREETING])
  const [step, setStep] = useState(persisted?.step || 'greeting')
  const [isLoading, setIsLoading] = useState(false)
  const [claimResult, setClaimResult] = useState(persisted?.claimResult || null)
  const [pendingImages, setPendingImages] = useState([])
  const [inputDisabled, setInputDisabled] = useState(persisted?.inputDisabled || false)
  const [showManualEntry, setShowManualEntry] = useState(false)

  // ── Persist a snapshot whenever meaningful state changes ──────────────────
  useEffect(() => {
    try {
      // Strip blob: preview URLs — they are invalid after a reload anyway.
      const persistableMessages = messages.map((m) =>
        m.imagePreviews ? { ...m, imagePreviews: undefined } : m,
      )
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          sessionId: sessionId.current,
          claimId: claimIdRef.current,
          conversationHistory: conversationHistory.current,
          allUploadedPaths: allUploadedPaths.current,
          echoedState: echoedState.current,
          messages: persistableMessages,
          step,
          claimResult,
          inputDisabled,
        }),
      )
    } catch {
      /* quota / serialization issues are non-fatal */
    }
  }, [messages, step, claimResult, inputDisabled])

  const appendMessages = useCallback((...msgs) => {
    setMessages((prev) => [...prev, ...msgs])
  }, [])

  // ── Lane 2 status polling ─────────────────────────────────────────────────
  // While a claim is "under review" (lane 2, not yet resolved), poll the
  // backend so the simulator reflects the staff decision once it happens.
  useEffect(() => {
    const underReview =
      claimResult && claimResult.lane === 2 && claimResult.status === 'under_review'
    if (!underReview || !claimResult.claimId) return

    let cancelled = false

    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND}/claims/${claimResult.claimId}/status`)
        if (!res.ok) return
        const data = await res.json()
        if (cancelled || !data.found) return

        if (data.status === 'RESOLVED') {
          const resolved = {
            lane: 2,
            status: 'approved',
            claimId: claimResult.claimId,
            voucherCode: data.voucher_code || null,
            compensation: data.compensation ?? null,
          }
          setClaimResult(resolved)
          appendMessages(
            botMsg('🎉 Good news! Your claim has been approved by our team. Your voucher details are below.'),
          )
        } else if (data.status === 'REJECTED') {
          const rejected = {
            lane: 2,
            status: 'rejected',
            claimId: claimResult.claimId,
          }
          setClaimResult(rejected)
          appendMessages(
            botMsg('We\'re sorry — after review, your claim could not be approved. Please see the details below. If you believe this is a mistake, you can contact our support desk.'),
          )
        }
      } catch {
        /* network blip — try again next tick */
      }
    }

    // Poll immediately (covers the reload case where the decision already
    // happened), then on an interval.
    poll()
    const id = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [claimResult, appendMessages])

  const uploadFile = useCallback(async (file, photoType) => {
    const cid = claimIdRef.current || 'pending'
    const form = new FormData()
    form.append('session_id', sessionId.current)
    form.append('claim_id', cid)
    form.append('photo_type', photoType)
    form.append('file', file)
    try {
      const res = await fetch(`${BACKEND}/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(`Upload HTTP ${res.status}`)
      const data = await res.json()
      return data.path
    } catch (err) {
      console.error('[useClaimFlow] upload error:', err)
      return null
    }
  }, [])

  const callWebhook = useCallback(
    async (message, newImagePaths = [], manual = null) => {
      if (newImagePaths.length > 0) {
        allUploadedPaths.current = [...allUploadedPaths.current, ...newImagePaths]
      }

      const body = {
        session_id: sessionId.current,
        message,
        image_paths: allUploadedPaths.current,
        conversation_history: conversationHistory.current,
        conversation_step: step,
        airport_context: airport,
        terminal_context: terminal,
        ...echoedState.current,
        manual_tag_text: manual?.text ?? null,
        manual_flight_number: manual?.flight ?? null,
        manual_pnr: manual?.pnr ?? null,
        manual_bag_id: manual?.bagId ?? null,
      }

      try {
        const res = await fetch(`${BACKEND}/webhook`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!res.ok) throw new Error(`Webhook HTTP ${res.status}`)
        const data = await res.json()

        conversationHistory.current = [
          ...conversationHistory.current,
          { role: 'user', content: message },
          { role: 'assistant', content: data.reply || '' },
        ]

        if (data.claim_id) claimIdRef.current = data.claim_id

        echoedState.current = {
          conversation_ended: data.conversation_ended ?? echoedState.current.conversation_ended,
          no_damage_detected: data.no_damage_detected ?? echoedState.current.no_damage_detected,
          not_a_bag: data.not_a_bag ?? echoedState.current.not_a_bag,
          last_object_description: data.last_object_description ?? echoedState.current.last_object_description,
          non_bag_attempts: data.non_bag_attempts ?? echoedState.current.non_bag_attempts,
          tag_in_damage_photo: data.tag_in_damage_photo ?? echoedState.current.tag_in_damage_photo,
          tag_candidate_paths: data.tag_candidate_paths ?? echoedState.current.tag_candidate_paths,
          processed_damage_paths: data.processed_damage_paths ?? echoedState.current.processed_damage_paths,
          damage_types: data.damage_types ?? echoedState.current.damage_types,
          severity_score: data.severity_score ?? echoedState.current.severity_score,
          brand_detected: data.brand_detected ?? echoedState.current.brand_detected,
          is_luxury: data.is_luxury ?? echoedState.current.is_luxury,
          compensation_estimate_usd: data.compensation_estimate_usd ?? echoedState.current.compensation_estimate_usd,
          processed_tag_paths: data.processed_tag_paths ?? echoedState.current.processed_tag_paths,
          flight_number: data.flight_number ?? echoedState.current.flight_number,
          pnr: data.pnr ?? echoedState.current.pnr,
          bag_id: data.bag_id ?? echoedState.current.bag_id,
          ocr_confidence: data.ocr_confidence ?? echoedState.current.ocr_confidence,
          tag_data_complete: data.tag_data_complete ?? echoedState.current.tag_data_complete,
          tag_manually_entered: data.tag_manually_entered ?? echoedState.current.tag_manually_entered,
          offer_manual_entry: data.offer_manual_entry ?? echoedState.current.offer_manual_entry,
        }

        setShowManualEntry(Boolean(data.offer_manual_entry))

        return data
      } catch (err) {
        console.error('[useClaimFlow] webhook error:', err)
        return null
      }
    },
    [step, airport, terminal],
  )

  const handleSendText = useCallback(
    async (text) => {
      if (!text.trim() || isLoading || inputDisabled) return
      if (!text.startsWith('[QR_AUTO_START]')) appendMessages(userMsg(text))
      setIsLoading(true)
      const response = await callWebhook(text)
      setIsLoading(false)
      if (!response) {
        appendMessages(botMsg('⚠️ Sorry, I could not reach the server. Please try again.'))
        return
      }
      if (response.error) {
        appendMessages(botMsg(`⚠️ Something went wrong: ${response.error}`))
        return
      }
      if (response.conversation_step) setStep(response.conversation_step)
      if (response.reply) appendMessages(botMsg(response.reply))
      _handleResult(response)
    },
    [isLoading, inputDisabled, appendMessages, callWebhook],
  )

  const handleSendImages = useCallback(
    async (captionText = '') => {
      if (pendingImages.length === 0 || isLoading) return

      const photoType = step === 'tag_photo' ? 'tag' : 'damage'

      appendMessages(
        userMsg(captionText || `📸 ${pendingImages.length} photo${pendingImages.length > 1 ? 's' : ''} attached`, {
          imagePreviews: pendingImages.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })),
        }),
      )

      setIsLoading(true)
      setPendingImages([])

      const paths = await Promise.all(pendingImages.map((file) => uploadFile(file, photoType)))
      const validPaths = paths.filter(Boolean)
      if (validPaths.length === 0) {
        setIsLoading(false)
        appendMessages(botMsg('⚠️ Photo upload failed. Please try again.'))
        return
      }

      const messageText = captionText || `[Attached ${validPaths.length} ${photoType} photo(s)]`
      const response = await callWebhook(messageText, validPaths)
      setIsLoading(false)
      if (!response) {
        appendMessages(botMsg('⚠️ Could not reach the server. Please try again.'))
        return
      }
      if (response.error) {
        appendMessages(botMsg(`⚠️ Error: ${response.error}`))
        return
      }
      if (response.conversation_step) setStep(response.conversation_step)
      if (response.reply) appendMessages(botMsg(response.reply))
      _handleResult(response)
    },
    [pendingImages, isLoading, step, appendMessages, uploadFile, callWebhook],
  )

  const submitManualTag = useCallback(
    async ({ flight = '', pnr = '', bagId = '' }) => {
      if (isLoading || inputDisabled) return
      const summary = [
        flight && `Flight ${flight}`,
        pnr && `PNR ${pnr}`,
        bagId && `Bag ${bagId}`,
      ]
        .filter(Boolean)
        .join(', ')
      appendMessages(userMsg(`📝 Entered tag details: ${summary || '(none)'}`))
      setShowManualEntry(false)
      setIsLoading(true)
      const response = await callWebhook('[Manual tag details provided]', [], { flight, pnr, bagId })
      setIsLoading(false)
      if (!response) {
        appendMessages(botMsg('⚠️ Could not reach the server. Please try again.'))
        return
      }
      if (response.error) {
        appendMessages(botMsg(`⚠️ Error: ${response.error}`))
        return
      }
      if (response.conversation_step) setStep(response.conversation_step)
      if (response.reply) appendMessages(botMsg(response.reply))
      _handleResult(response)
    },
    [isLoading, inputDisabled, appendMessages, callWebhook],
  )

  function _handleResult(response) {
    if (response.conversation_ended) {
      setInputDisabled(true)
      setStep('result')
      return
    }
    if (response.routing_lane === 1) {
      setClaimResult({
        lane: 1,
        status: 'approved',
        voucherCode: response.voucher_code,
        claimId: response.claim_id,
        compensation: response.compensation_estimate_usd ?? null,
      })
      setInputDisabled(true)
      setStep('result')
    } else if (response.routing_lane === 2) {
      // Under review — the polling effect will resolve this to approved/rejected.
      setClaimResult({ lane: 2, status: 'under_review', claimId: response.claim_id })
      setInputDisabled(true)
      setStep('result')
    }
  }

  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files)
    if (files.length === 0) return
    setPendingImages((prev) => [...prev, ...files])
    e.target.value = ''
  }, [])

  const removePendingImage = useCallback((idx) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== idx))
  }, [])

  // Start a brand-new claim (clears persisted session).
  const resetClaim = useCallback(() => {
    clearPersisted()
    sessionId.current = makeSessionId()
    claimIdRef.current = null
    conversationHistory.current = []
    allUploadedPaths.current = []
    echoedState.current = { ...DEFAULT_ECHO }
    setMessages([GREETING])
    setStep('greeting')
    setClaimResult(null)
    setInputDisabled(false)
    setShowManualEntry(false)
    setPendingImages([])
  }, [])

  return {
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
  }
}