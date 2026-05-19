/**
 * ChatHeader — WhatsApp-style top navigation bar.
 * Displays ABC Airline branding, online status indicator, and a lock icon
 * to indicate the conversation is running over a simulated secure channel.
 */
export default function ChatHeader() {
  return (
    <div className="flex items-center gap-3 bg-[#075E54] px-4 py-3 shadow-md">

      {/* Airline avatar circle */}
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-[#128C7E] text-sm font-bold text-white">
        ABC
      </div>

      {/* Contact name + online status */}
      <div className="flex-1">
        <p className="text-sm font-semibold leading-tight text-white">
          ABC Airline — Baggage Claims
        </p>
        <p className="flex items-center gap-1 text-xs text-[#c5e8e2]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#25D366]" />
          AI Assistant · Online
        </p>
      </div>

      {/* Lock icon — simulated secure channel indicator */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5 text-[#c5e8e2]"
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-label="Secure conversation"
      >
        <path
          fillRule="evenodd"
          d="M12 1.5a5.25 5.25 0 0 0-5.25 5.25v3a3 3 0 0 0-3 3v6.75a3 3 0 0 0 3 3h10.5a3 3 0 0 0 3-3v-6.75a3 3 0 0 0-3-3v-3c0-2.9-2.35-5.25-5.25-5.25Zm3.75 8.25v-3a3.75 3.75 0 1 0-7.5 0v3h7.5Z"
          clipRule="evenodd"
        />
      </svg>
    </div>
  )
}