import { useState } from 'react'
import ChatHeader from './components/ChatHeader.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ImageUploadPreview from './components/ImageUploadPreview.jsx'
import ManualTagEntry from './components/ManualTagEntry.jsx'
import { useClaimFlow } from './hooks/useClaimFlow.js'

/**
 * App — root component.
 *
 * Conversation state machine steps:
 *   greeting → damage_photos → tag_photo → confirm → result
 *
 * Manual tag entry (issue #3): when the backend sets offer_manual_entry, the
 * hook flips showManualEntry true and a structured form appears above the
 * input. The passenger can also just type the details directly in chat.
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

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-700">
      <div className="flex h-[700px] w-[400px] flex-col overflow-hidden rounded-2xl shadow-2xl">

        <div className="absolute right-4 top-4 z-10 hidden rounded-full bg-black/40 px-2 py-0.5 text-[10px] text-white md:block">
          step: {step}
        </div>

        <ChatHeader />

        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          claimResult={claimResult}
        />

        {/* Manual tag-entry form — shown when backend offers it (issue #3) */}
        {showManualEntry && !inputDisabled && (
          <ManualTagEntry
            onSubmit={submitManualTag}
            onCancel={() => setShowManualEntry(false)}
            disabled={isLoading}
          />
        )}

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
