/**
 * TypingIndicator — animated three-dot "AI is typing" bubble.
 * Shown while awaiting a /webhook response.
 * Matches WhatsApp style: left-aligned white bubble with bouncing dots.
 */
export default function TypingIndicator() {
  return (
    <div className="mb-1 flex justify-start">
      <div className="rounded-lg rounded-tl-none bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full bg-gray-400"
            style={{ animation: 'typing-bounce 1.2s infinite 0s' }}
          />
          <span
            className="h-2 w-2 rounded-full bg-gray-400"
            style={{ animation: 'typing-bounce 1.2s infinite 0.2s' }}
          />
          <span
            className="h-2 w-2 rounded-full bg-gray-400"
            style={{ animation: 'typing-bounce 1.2s infinite 0.4s' }}
          />
        </div>
      </div>
    </div>
  )
}
