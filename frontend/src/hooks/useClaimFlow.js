import { useCallback, useRef, useState } from 'react'

/**
 * useClaimFlow — manages the full baggage claim conversation.
 *
 * KEY DESIGN DECISIONS:
 *
 * 1. conversation_step is sent to backend on every request.
 *    LangGraph MemorySaver does not persist plain dataclass field values
 *    between separate ainvoke() calls. The backend creates a fresh ClaimState
 *    with step="greeting" each call unless we supply the current step.
 *    Frontend tracks the step from each response and echoes it back.
 *
 * 2. allUploadedPaths accumulates every uploaded image path across the session.
 *    At the "confirm" step the user sends only text ("yes"). A4 still needs
 *    all image paths for fraud checks and routing. Resending the full set
 *    on every webhook call guarantees A4 has everything it needs.
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

export function useClaimFlow() {
  const sessionId = useRef(makeSessionId())
  const claimIdRef = useRef(null)
  const conversationHistory = useRef([])
  const allUploadedPaths = useRef([])   // accumulates ALL uploaded paths for this session

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

  /**
   * callWebhook — sends message + full accumulated image paths + current step.
   *
   * Always sends:
   *   - allUploadedPaths.current (full set, not just this turn's paths)
   *   - step (current frontend step, echoed to backend to preserve conversation flow)
   */
  const callWebhook = useCallback(async (message, newImagePaths = []) => {
    if (newImagePaths.length > 0) {
      allUploadedPaths.current = [...allUploadedPaths.current, ...newImagePaths]
    }

    const body = {
      session_id: sessionId.current,
      message,
      image_paths: allUploadedPaths.current,
      conversation_history: conversationHistory.current,
      conversation_step: step,   // ← echo current step to backend
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
      return data
    } catch (err) {
      console.error('[useClaimFlow] webhook error:', err)
      return null
    }
  }, [step])   // step is a dependency — callWebhook reads it

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