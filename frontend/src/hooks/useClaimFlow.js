import { useCallback, useRef, useState } from 'react'

/**
 * useClaimFlow — manages the full baggage claim conversation.
 *
 * State is echoed back to the backend each turn (LangGraph MemorySaver does not
 * persist plain dataclass fields between ainvoke calls). New in this version:
 *   - not_a_bag / non_bag_attempts / last_object_description (issue #1)
 *   - tag_in_damage_photo / tag_candidate_paths (issues #2 & #4)
 *   - tag_data_complete / tag_manually_entered / offer_manual_entry (issue #3)
 *   - manual tag entry via submitManualTag()
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

export function useClaimFlow({ airport = null, terminal = null } = {}) {
  const sessionId = useRef(makeSessionId())
  const claimIdRef = useRef(null)
  const conversationHistory = useRef([])
  const allUploadedPaths = useRef([])

  // Echoed state — persisted across turns and sent back each request.
  const echoedState = useRef({
    conversation_ended: false,
    no_damage_detected: false,
    // Issue #1 — object gate
    not_a_bag: false,
    last_object_description: null,
    non_bag_attempts: 0,
    // Issue #2/#4 — tag in damage photo
    tag_in_damage_photo: false,
    tag_candidate_paths: [],
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
    tag_data_complete: false,
    tag_manually_entered: false,
    offer_manual_entry: false,
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
  // Issue #3 — when true, the UI shows a manual tag-entry form.
  const [showManualEntry, setShowManualEntry] = useState(false)

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
        // Manual tag entry overrides (issue #3) — only sent on the turn the
        // passenger submits them; not persisted in echoedState afterwards.
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

        // Surface the manual-entry form when the backend offers it.
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

      // Only an explicit tag_photo step forces the 'tag' label. Otherwise images
      // are uploaded as 'damage' and the backend vision gate decides whether each
      // one is a bag and whether a readable tag is present (issues #1, #2, #4).
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

  // Issue #3 — submit manually typed tag details (from the form).
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
      const response = await callWebhook('[Manual tag details provided]', [], {
        flight,
        pnr,
        bagId,
      })
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
    // Terminal — no claim filed (confirmed-fine OR repeated non-bag uploads).
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
    showManualEntry,
    setShowManualEntry,
    handleSendText,
    handleSendImages,
    submitManualTag,
    handleFileSelect,
    removePendingImage,
  }
}