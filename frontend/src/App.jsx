import { useState } from 'react'
import ChatHeader from './components/ChatHeader.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ImageUploadPreview from './components/ImageUploadPreview.jsx'
import { useClaimFlow } from './hooks/useClaimFlow.js'

/**
 * App — root component. Full T-013 implementation.
 *
 * T-003 stubs removed. All logic delegated to useClaimFlow hook:
 *   - Multi-turn conversation with FastAPI /webhook
 *   - Multi-photo upload via /upload endpoint
 *   - Staged photo preview before send
 *   - Claim result (Lane 1 voucher | Lane 2 under-review) surfaced via hook
 *
 * Conversation state machine steps:
 *   greeting → damage_photos → tag_photo → confirm → result
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
    handleSendText,
    handleSendImages,
    handleFileSelect,
    removePendingImage,
  } = useClaimFlow()

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
