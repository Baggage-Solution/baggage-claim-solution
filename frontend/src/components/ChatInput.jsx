import { useRef } from 'react'

/**
 * ChatInput — bottom bar with file upload, text field, and send button.
 *
 * T-003 scope: UI shell only — handlers are stubs that log to console.
 * Full backend wiring happens in T-013 (feature/simulator-full-flow).
 *
 * @param {string}   value         - Controlled text input value
 * @param {Function} onChange       - Text change handler
 * @param {Function} onSend         - Called when send button pressed or Enter hit
 * @param {Function} onFileSelect   - Called when files selected via picker
 * @param {boolean}  disabled       - Disable all inputs while awaiting reply
 */
export default function ChatInput({ value, onChange, onSend, onFileSelect, disabled = false }) {
  const fileInputRef = useRef(null)

  return (
    <div className="flex items-center gap-2 bg-[#F0F0F0] px-3 py-2">

      {/* Hidden multi-file input — triggered by paperclip button below */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={onFileSelect}
        disabled={disabled}
      />

      {/* Paperclip / attach button */}
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        aria-label="Attach photos"
        className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-200 disabled:opacity-40"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
          />
        </svg>
      </button>

      {/* Text input — Enter key also triggers send */}
      <input
        type="text"
        value={value}
        onChange={onChange}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && onSend()}
        placeholder="Type a message…"
        disabled={disabled}
        className="flex-1 rounded-full bg-white px-4 py-2 text-sm text-gray-800 placeholder-gray-400 outline-none ring-1 ring-transparent focus:ring-[#128C7E] disabled:opacity-40"
      />

      {/* Send button */}
      <button
        onClick={onSend}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-[#075E54] text-white transition-colors hover:bg-[#128C7E] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path d="M3.478 2.405a.75.75 0 0 0-.926.94l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.405Z" />
        </svg>
      </button>
    </div>
  )
}