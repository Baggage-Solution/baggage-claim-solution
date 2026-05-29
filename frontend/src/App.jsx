import { useState } from 'react'
import ChatHeader from './components/ChatHeader.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ImageUploadPreview from './components/ImageUploadPreview.jsx'
import ManualTagEntry from './components/ManualTagEntry.jsx'
import { useClaimFlow } from './hooks/useClaimFlow.js'

/**
 * App — root component (the simulator at "/").
 *
 * Conversation state machine steps:
 *   greeting → damage_photos → tag_photo → confirm → result
 *
 * The session persists across reloads (localStorage) and a Lane 2 claim keeps
 * polling for the staff decision, so the result card updates to approved/rejected
 * without losing the conversation. "Start new claim" clears the persisted session.
 */
export default function App() {
  const [inputValue, setInputValue] = useState('')

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
  } = useClaimFlow()

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

  // A claim is fully finished (no more action) when it's Lane 1 approved, or a
  // Lane 2 claim that has resolved either way.
  const isFinished =
    claimResult &&
    (claimResult.lane === 1 ||
      claimResult.status === 'approved' ||
      claimResult.status === 'rejected')

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-gray-700 py-6">

      {/* Toolbar above the phone — keeps controls off the chat header */}
      <div className="flex w-[400px] items-center justify-between px-1">
        <a
          href="/dashboard"
          className="rounded-full bg-black/30 px-3 py-1 text-xs font-medium text-white hover:bg-black/50"
        >
          Dashboard →
        </a>
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

        {/* Manual tag-entry form — shown when backend offers it */}
        {showManualEntry && !inputDisabled && (
          <ManualTagEntry
            onSubmit={submitManualTag}
            onCancel={() => setShowManualEntry(false)}
            disabled={isLoading}
          />
        )}

        <ImageUploadPreview files={pendingImages} onRemove={removePendingImage} />

        {/* When the claim is finished, replace the input bar with a reset action. */}
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
