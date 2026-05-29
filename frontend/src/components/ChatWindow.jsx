import { useEffect, useRef } from 'react'
import ClaimResultCard from './ClaimResultCard.jsx'
import MessageBubble from './MessageBubble.jsx'
import TypingIndicator from './TypingIndicator.jsx'

/**
 * ChatWindow — scrollable message list with WhatsApp wallpaper background.
 * Auto-scrolls to the newest message on every render.
 *
 * @param {Array}       messages    - Array of message objects
 * @param {boolean}     isLoading   - True while awaiting webhook response
 * @param {object|null} claimResult - { lane, status, voucherCode, claimId, compensation } or null
 */
export default function ChatWindow({ messages, isLoading, claimResult }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, claimResult])

  return (
    <div className="chat-scroll flex-1 overflow-y-auto bg-[#ECE5DD] px-4 py-3">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          sender={msg.sender}
          text={msg.text}
          timestamp={msg.timestamp}
          imagePreviews={msg.imagePreviews}
        />
      ))}

      {/* Typing indicator — shown while awaiting AI reply */}
      {isLoading && <TypingIndicator />}

      {/* Terminal result card — shown after A4 routes the claim, and updated
          live when a Lane 2 claim is approved/rejected by staff. */}
      {claimResult && (
        <ClaimResultCard
          lane={claimResult.lane}
          status={claimResult.status}
          voucherCode={claimResult.voucherCode}
          claimId={claimResult.claimId}
          compensation={claimResult.compensation}
        />
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
  )
}