import { useState } from 'react'
import ChatHeader from './components/ChatHeader.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ChatInput from './components/ChatInput.jsx'
import { mockMessages } from './data/mockMessages.js'

/**
 * App — root component, composes the WhatsApp simulator shell.
 *
 * T-003 scope: static UI frame only.
 * Handlers are stubs — full backend wiring in T-013 (simulator-full-flow).
 */
export default function App() {
  const [inputValue, setInputValue] = useState('')

  /** T-003 stub — real send logic wired in T-013 */
  const handleSend = () => {
    if (!inputValue.trim()) return
    console.log('[T-003 stub] send:', inputValue)
    setInputValue('')
  }

  /** T-003 stub — real upload logic wired in T-013 */
  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files)
    console.log('[T-003 stub] files selected:', files.map((f) => f.name))
    // Reset input so same file can be re-selected
    e.target.value = ''
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-700">
      {/* Phone-width simulator frame */}
      <div className="flex h-[700px] w-[400px] flex-col overflow-hidden rounded-2xl shadow-2xl">
        <ChatHeader />
        <ChatWindow messages={mockMessages} />
        <ChatInput
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onSend={handleSend}
          onFileSelect={handleFileSelect}
        />
      </div>
    </div>
  )
}