import { useCallback, useRef, useState } from 'react'

/**
 * useClaimFlow — manages the full baggage claim conversation.
 *
 * WHY WE ECHO STATE BACK TO THE BACKEND:
 * LangGraph MemorySaver does not persist plain dataclass fields between
 * separate ainvoke() calls. Each turn starts with a fresh ClaimState at defaults.
 * The frontend stores key results from each response and sends them back on the
 * next request so the backend always has the full picture:
 *
 *   conversation_step       — which step the flow is on
 *   processed_damage_paths  — which damage photos A2 already analysed (skip re-analysis)
 *   damage_types            — A2 result: what damage was found
 *   severity_score          — A2 result: how severe (0.0–1.0)
 *   brand_detected          — A2 result: bag brand
 *   is_luxury               — A2 result: luxury flag (affects compensation × 1.5)
 *   compensation_estimate   — A2 result: base USD estimate
 *   flight_number           — A3 result: from bag tag OCR
 *   pnr                     — A3 result: passenger name record
 *   bag_id                  — A3 result: bag tag number
 *   ocr_confidence          — A3 result: OCR quality score
 *
 * Without echoing A2/A3 results, the confirm turn would start with blank
 * damage_types and severity=0, causing A4 to always route to Lane 1 with $0
 * compensation regardless of the actual damage.
 *
 * T-018 addition:
 *   airport + terminal context is forwarded to the backend on every request
 *   so A1 can include location context in its greeting when QR auto-start fires.
 */

const BACKEND = 'http://localhost:8000'

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

/**
 * @param {object} options
 * @param {string|null} options.airport  - Airport context from QR URL param (T-018)
 * @param {string|null} options.terminal - Terminal context from QR URL param (T-018)
 */
export function useClaimFlow({ airport = null, terminal = null } = {}) {
  const sessionId = useRef(makeSessionId())
  const claimIdRef = useRef(null)
  const conversationHistory = useRef([])
  const allUploadedPaths = useRef([])

  // Echoed state — all persisted across turns and sent back each request
  const echoedState = useRef({
    conversation_ended: false,
    no_damage_detected: false,
    processed_damage_paths: [],
    // A2 results
    damage_types: [],
    severity_score: 0.0,
    brand_detected: null,
    is_luxury: false,
    compensation_estimate_usd: 0.0,
    // A3 results
    processed_tag_paths: [],
    flight_number: null,
    pnr: null,
    bag_id: null,
    ocr_confidence: 0.0,
  })

  const [messages, setMessages] = useState([
    botMsg(
      '👋 Hello! I\'m the ABC Airline baggage claim assistant. I\'m here to help you file a damage claim quickly — no queues, no paperwork.\n\nCould you please briefly describe what happened to your bag?',
    ),
  ])
  const [step, setStep] = useState('greeting')
  const [isLoading, setIsLoading] = useState(false)
  const [claimResult, setClaimResult] = useState(null)
  const [pendingImages, setPendingImages] = useState([])
  const [inputDisabled, setInputDisabled] = useState(false)

  const appendMessages = useCallback((...msgs) => {
    setMessages((prev) => [...prev, ...msgs])
  }, [])

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

  const callWebhook = useCallback(async (message, newImagePaths = []) => {
    if (newImagePaths.length > 0) {
      allUploadedPaths.current = [...allUploadedPaths.current, ...newImagePaths]
    }

    const body = {
      session_id: sessionId.current,
      message,
      image_paths: allUploadedPaths.current,
      conversation_history: conversationHistory.current,
      conversation_step: step,
      // T-018: forward QR airport/terminal context to backend
      airport_context: airport,
      terminal_context: terminal,
      // Echo all persisted state back to backend
      ...echoedState.current,
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

      // Update all echoed fields from response
      echoedState.current = {
        conversation_ended: data.conversation_ended ?? echoedState.current.conversation_ended,
        no_damage_detected: data.no_damage_detected ?? echoedState.current.no_damage_detected,
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
      }

      return data
    } catch (err) {
      console.error('[useClaimFlow] webhook error:', err)
      return null
    }
  }, [step, airport, terminal])

  const handleSendText = useCallback(
    async (text) => {
      if (!text.trim() || isLoading || inputDisabled) return

      // Don't render the QR auto-start sentinel message as a user bubble
      if (!text.startsWith('[QR_AUTO_START]')) {
        appendMessages(userMsg(text))
      }
      setIsLoading(true)

      const response = await callWebhook(text)
      setIsLoading(false)

      if (!response) {
        appendMessages(botMsg('⚠️ Sorry, I could not reach the server. Please check your connection and try again.'))
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

  function _handleResult(response) {
    // Terminal — passenger confirmed no damage / nothing to claim. Lock input.
    // NOTE: no_damage_detected (a single clear photo showing no damage) is NOT
    // terminal — the input stays OPEN so the passenger can send a real damage
    // photo or confirm the bag is fine. Only conversation_ended locks the chat.
    if (response.conversation_ended) {
      setInputDisabled(true)
      setStep('result')
      return
    }
    if (response.routing_lane === 1) {
      setClaimResult({ lane: 1, voucherCode: response.voucher_code, claimId: response.claim_id })
      setInputDisabled(true)
      setStep('result')
    } else if (response.routing_lane === 2) {
      setClaimResult({ lane: 2, claimId: response.claim_id })
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

  return {
    messages,
    step,
    isLoading,
    claimResult,
    pendingImages,
    inputDisabled,
    handleSendText,
    handleSendImages,
    handleFileSelect,
    removePendingImage,
  }
}