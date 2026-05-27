import { useEffect, useRef, useState } from 'react'
import ChatHeader from '../components/ChatHeader.jsx'
import ChatInput from '../components/ChatInput.jsx'
import ChatWindow from '../components/ChatWindow.jsx'
import ImageUploadPreview from '../components/ImageUploadPreview.jsx'
import { useClaimFlow } from '../hooks/useClaimFlow.js'

/**
 * Simulator — full claim conversation page, reachable at /simulator.
 *
 * T-018 additions vs the original App root:
 *  - Reads `?airport=T3&terminal=B&auto=1` URL params set by the QR code.
 *  - On mount, if `auto=1` is present, fires an automatic greeting message
 *    that includes the airport + terminal context so A1 can greet the
 *    passenger with their exact location ("I can see you're at Terminal B —
 *    let's get your claim started.").
 *  - Displays a small context badge in the header area when airport/terminal
 *    context is present, so testers and demo reviewers can see what was
 *    pre-filled from the QR scan.
 *
 * The auto-start fires once, guarded by a ref, so React StrictMode
 * double-invoke in dev does not send the greeting twice.
 */
export default function Simulator() {
  const [inputValue, setInputValue] = useState('')
  const autoStartFired = useRef(false)

  // ── Parse QR context from URL params ──────────────────────────────────────
  const params = new URLSearchParams(window.location.search)
  const airport = params.get('airport') || null
  const terminal = params.get('terminal') || null
  const autoStart = params.get('auto') === '1'

  const {
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
  } = useClaimFlow({ airport, terminal })

  /**
   * Auto-start: if QR params include auto=1, fire a greeting message once
   * on mount so the passenger doesn't have to type anything first.
   * The greeting text is invisible to the user (it's just a trigger) —
   * the first visible message is the bot's contextual reply.
   */
  useEffect(() => {
    if (!autoStart || autoStartFired.current) return
    autoStartFired.current = true

    // Short delay so the UI renders first — feels more natural
    const t = setTimeout(() => {
      const contextMsg = airport && terminal
        ? `[QR_AUTO_START] airport=${airport} terminal=${terminal}`
        : '[QR_AUTO_START]'
      handleSendText(contextMsg)
    }, 600)

    return () => clearTimeout(t)
  }, [autoStart, airport, terminal, handleSendText])

  /**
   * onSend — determine whether to send text-only or images.
   * If photos are staged, always send them (text becomes the caption).
   */
  const onSend = async () => {
    if (inputDisabled || isLoading) return

    if (pendingImages.length > 0) {
      await handleSendImages(inputValue.trim())
      setInputValue('')
    } else if (inputValue.trim()) {
      await handleSendText(inputValue.trim())
      setInputValue('')
    }
  }

  /** Allow Enter key to trigger send */
  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-700">
      {/* Phone-width simulator frame */}
      <div className="flex h-[700px] w-[400px] flex-col overflow-hidden rounded-2xl shadow-2xl">

        {/* Step badge — small dev indicator showing current conversation step */}
        <div className="absolute right-4 top-4 z-10 hidden rounded-full bg-black/40 px-2 py-0.5 text-[10px] text-white md:block">
          step: {step}
        </div>

        {/* QR context badge — shown when airport/terminal params are present */}
        {airport && terminal && (
          <div className="absolute left-4 top-4 z-10 rounded-full bg-blue-500/80 px-2 py-0.5 text-[10px] text-white">
            ✈ {airport} · Terminal {terminal}
          </div>
        )}

        <ChatHeader />

        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          claimResult={claimResult}
        />

        {/* Staged photo strip — visible when photos selected but not yet sent */}
        <ImageUploadPreview
          files={pendingImages}
          onRemove={removePendingImage}
        />

        <ChatInput
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onSend={onSend}
          onKeyDown={onKeyDown}
          onFileSelect={handleFileSelect}
          disabled={inputDisabled || isLoading}
          hasPendingImages={pendingImages.length > 0}
        />
      </div>
    </div>
  )
}