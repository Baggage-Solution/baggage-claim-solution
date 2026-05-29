import { useEffect, useRef, useState } from 'react'
import ChatHeader from '../components/ChatHeader.jsx'
import ChatInput from '../components/ChatInput.jsx'
import ChatWindow from '../components/ChatWindow.jsx'
import ImageUploadPreview from '../components/ImageUploadPreview.jsx'
import ManualTagEntry from '../components/ManualTagEntry.jsx'
import { useClaimFlow } from '../hooks/useClaimFlow.js'

/**
 * Simulator — full claim conversation page, reachable at /simulator.
 *
 * QR context (T-018): reads ?airport=&terminal=&auto=1 from the URL.
 *
 * Session persists across reloads (localStorage); a Lane 2 claim polls for the
 * staff decision and updates the result card to approved/rejected.
 */
export default function Simulator() {
  const [inputValue, setInputValue] = useState('')
  const autoStartFired = useRef(false)

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
    showManualEntry,
    setShowManualEntry,
    handleSendText,
    handleSendImages,
    submitManualTag,
    handleFileSelect,
    removePendingImage,
    resetClaim,
  } = useClaimFlow({ airport, terminal })

  useEffect(() => {
    if (!autoStart || autoStartFired.current) return
    autoStartFired.current = true
    const t = setTimeout(() => {
      const contextMsg = airport && terminal
        ? `[QR_AUTO_START] airport=${airport} terminal=${terminal}`
        : '[QR_AUTO_START]'
      handleSendText(contextMsg)
    }, 600)
    return () => clearTimeout(t)
  }, [autoStart, airport, terminal, handleSendText])

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

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  const isFinished =
    claimResult &&
    (claimResult.lane === 1 ||
      claimResult.status === 'approved' ||
      claimResult.status === 'rejected')

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-gray-700 py-6">

      {/* Toolbar above the phone — keeps controls off the chat header */}
      <div className="flex w-[400px] items-center justify-between px-1">
        {airport && terminal ? (
          <span className="rounded-full bg-blue-500/80 px-3 py-1 text-xs font-medium text-white">
            ✈ {airport} · Terminal {terminal}
          </span>
        ) : (
          <a
            href="/dashboard"
            className="rounded-full bg-black/30 px-3 py-1 text-xs font-medium text-white hover:bg-black/50"
          >
            Dashboard →
          </a>
        )}
        <span className="rounded-full bg-black/30 px-3 py-1 text-xs font-medium text-white">
          step: {step}
        </span>
      </div>

      <div className="relative flex h-[700px] w-[400px] flex-col overflow-hidden rounded-2xl shadow-2xl">

        <ChatHeader />

        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          claimResult={claimResult}
        />

        {showManualEntry && !inputDisabled && (
          <ManualTagEntry
            onSubmit={submitManualTag}
            onCancel={() => setShowManualEntry(false)}
            disabled={isLoading}
          />
        )}

        <ImageUploadPreview files={pendingImages} onRemove={removePendingImage} />

        {isFinished ? (
          <div className="bg-[#F0F0F0] px-3 py-3">
            <button
              onClick={resetClaim}
              className="w-full rounded-full bg-[#075E54] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#128C7E]"
            >
              Start a new claim
            </button>
          </div>
        ) : (
          <ChatInput
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onSend={onSend}
            onKeyDown={onKeyDown}
            onFileSelect={handleFileSelect}
            disabled={inputDisabled || isLoading}
            hasPendingImages={pendingImages.length > 0}
          />
        )}
      </div>
    </div>
  )
}
