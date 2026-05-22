import { useCallback, useRef, useState } from 'react'

/**
 * useClaimFlow — manages the full 13-step baggage claim conversation.
 *
 * Conversation steps (mirrors ClaimState.conversation_step on backend):
 *   greeting → damage_photos → tag_photo → confirm → result
 *
 * Responsibilities:
 *   - Maintains message list, current step, pending image queue, session ID
 *   - Calls POST /upload for each photo, then POST /webhook with image paths
 *   - Surfaces claim result (Lane 1 voucher | Lane 2 under-review) to UI
 *   - Handles re_request_tag and re_request_damage retry prompts
 *
 * T-013 scope: full backend wiring, replacing all T-003 stubs in App.jsx.
 */

const BACKEND = 'http://localhost:8000'

/** Generate a random session ID once per browser session */
function makeSessionId() {
  return `sim-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** Format current time as HH:MM for message timestamps */
function nowTime() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

/** Build a bot message object */
function botMsg(text, extra = {}) {
  return { id: crypto.randomUUID(), sender: 'bot', text, timestamp: nowTime(), ...extra }
}

/** Build a user message object */
function userMsg(text, extra = {}) {
  return { id: crypto.randomUUID(), sender: 'user', text, timestamp: nowTime(), ...extra }
}

export function useClaimFlow() {
  const sessionId = useRef(makeSessionId())
  const claimIdRef = useRef(null)
  const conversationHistory = useRef([])

  const [messages, setMessages] = useState([
    botMsg(
      '👋 Hello! I\'m the ABC Airline baggage claim assistant. I\'m here to help you file a damage claim quickly — no queues, no paperwork.\n\nCould you please briefly describe what happened to your bag?',
    ),
  ])
  const [step, setStep] = useState('greeting') // greeting | damage_photos | tag_photo | confirm | result
  const [isLoading, setIsLoading] = useState(false)
  const [claimResult, setClaimResult] = useState(null) // { lane, voucherCode, claimId }
  const [pendingImages, setPendingImages] = useState([]) // File[] staged before send
  const [inputDisabled, setInputDisabled] = useState(false)

  /** Append one or more messages to the chat */
  const appendMessages = useCallback((...msgs) => {
    setMessages((prev) => [...prev, ...msgs])
  }, [])

  /**
   * Upload a single File to /upload.
   * Returns the server path string, or null on failure.
   */
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
      console.error('[T-013] upload error:', err)
      return null
    }
  }, [])

  /**
   * Call POST /webhook with the current message + image paths.
   * Returns the parsed WebhookResponse, or null on failure.
   */
  const callWebhook = useCallback(async (message, imagePaths = []) => {
    const body = {
      session_id: sessionId.current,
      message,
      image_paths: imagePaths,
      conversation_history: conversationHistory.current,
    }

    try {
      const res = await fetch(`${BACKEND}/webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`Webhook HTTP ${res.status}`)
      const data = await res.json()

      // Keep rolling conversation history for multi-turn context
      conversationHistory.current = [
        ...conversationHistory.current,
        { role: 'user', content: message },
        { role: 'assistant', content: data.reply || '' },
      ]

      // Persist claim_id once A4 sets it
      if (data.claim_id) claimIdRef.current = data.claim_id

      return data
    } catch (err) {
      console.error('[T-013] webhook error:', err)
      return null
    }
  }, [])

  /**
   * handleSendText — user sends a plain text message.
   * Called from App.jsx when user presses Send.
   */
  const handleSendText = useCallback(
    async (text) => {
      if (!text.trim() || isLoading || inputDisabled) return

      appendMessages(userMsg(text))
      setIsLoading(true)

      const response = await callWebhook(text)
      setIsLoading(false)

      if (!response) {
        appendMessages(botMsg('⚠️ Sorry, I could not reach the server. Please check your connection and try again.'))
        return
      }

      // Handle backend error
      if (response.error) {
        appendMessages(botMsg(`⚠️ Something went wrong: ${response.error}`))
        return
      }

      // Update step
      if (response.conversation_step) setStep(response.conversation_step)

      // Show bot reply
      if (response.reply) appendMessages(botMsg(response.reply))

      // Check for terminal result
      _handleResult(response)
    },
    [isLoading, inputDisabled, appendMessages, callWebhook],
  )

  /**
   * handleSendImages — user has staged photos and hits Send (with or without text).
   * Uploads all staged images first, then calls /webhook with their paths.
   */
  const handleSendImages = useCallback(
    async (captionText = '') => {
      if (pendingImages.length === 0 || isLoading) return

      // Determine photo type based on current step
      const photoType = step === 'tag_photo' ? 'tag' : 'damage'

      // Show user bubble with image previews immediately
      appendMessages(
        userMsg(captionText || `📸 ${pendingImages.length} photo${pendingImages.length > 1 ? 's' : ''} attached`, {
          imagePreviews: pendingImages.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })),
        }),
      )

      setIsLoading(true)
      setPendingImages([])

      // Upload all files in parallel
      const paths = await Promise.all(
        pendingImages.map((file) => uploadFile(file, photoType)),
      )
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

  /**
   * _handleResult — check response for final lane routing and update UI.
   * Internal — not exposed to App.
   */
  function _handleResult(response) {
    if (response.routing_lane === 1) {
      setClaimResult({
        lane: 1,
        voucherCode: response.voucher_code,
        claimId: response.claim_id,
      })
      setInputDisabled(true)
      setStep('result')
    } else if (response.routing_lane === 2) {
      setClaimResult({
        lane: 2,
        claimId: response.claim_id,
      })
      setInputDisabled(true)
      setStep('result')
    }
  }

  /**
   * handleFileSelect — user picks files via the paperclip button.
   * Stages them in pendingImages for preview; does NOT upload yet.
   */
  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files)
    if (files.length === 0) return
    setPendingImages((prev) => [...prev, ...files])
    e.target.value = ''
  }, [])

  /** Remove a staged image by index */
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
