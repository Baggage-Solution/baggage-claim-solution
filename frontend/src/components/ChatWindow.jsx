import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble.jsx'

/**
 * ChatWindow — scrollable message list with WhatsApp wallpaper background.
 * Auto-scrolls to the newest message on every render.
 *
 * @param {Array} messages - Array of message objects from mockMessages / state
 */
export default function ChatWindow({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
      {/* Scroll anchor — always stays at bottom */}
      <div ref={bottomRef} />
    </div>
  )
}