/**
 * MessageBubble — single chat message in WhatsApp style.
 * Supports text content, image upload previews, timestamp, and read ticks.
 *
 * @param {'user'|'bot'} sender       - Who sent the message
 * @param {string}       text         - Message body text
 * @param {string}       timestamp    - Display time string (e.g. '10:42')
 * @param {Array}        imagePreviews - Optional array of { name: string }
 */
export default function MessageBubble({ sender, text, timestamp, imagePreviews = [] }) {
  const isUser = sender === 'user'

  return (
    <div className={`mb-1 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`relative max-w-[75%] rounded-lg px-3 pb-1 pt-2 shadow-sm ${
          isUser ? 'rounded-tr-none bg-[#DCF8C6]' : 'rounded-tl-none bg-white'
        }`}
      >
        {/* Image upload previews */}
        {imagePreviews.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {imagePreviews.map((img, i) => (
              <div
                key={i}
                className="flex h-20 w-20 items-center justify-center rounded-md bg-gray-200 text-center text-xs text-gray-500"
              >
                📷
                <br />
                {img.name}
              </div>
            ))}
          </div>
        )}

        {/* Message text */}
        {text && (
          <p className="text-sm leading-relaxed text-gray-800">{text}</p>
        )}

        {/* Timestamp + double blue tick for sent messages */}
        <div className="mt-0.5 flex items-center justify-end gap-1">
          <span className="text-[10px] text-gray-400">{timestamp}</span>
          {isUser && (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-3.5 w-3.5 text-[#34B7F1]"
              aria-label="Read"
            >
              <path
                fillRule="evenodd"
                d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </div>
      </div>
    </div>
  )
}