/**
 * ImageUploadPreview — horizontal scrollable strip of staged photos.
 *
 * Shows before the user hits Send, so they can review / remove images.
 * Sits between the chat window and the input bar.
 *
 * @param {File[]}   files            - Staged File objects from pendingImages
 * @param {Function} onRemove(index)  - Remove a single file by index
 */
export default function ImageUploadPreview({ files, onRemove }) {
  if (files.length === 0) return null

  return (
    <div className="flex items-center gap-2 overflow-x-auto bg-[#F0F0F0] px-3 py-2">
      {files.map((file, idx) => {
        const url = URL.createObjectURL(file)
        return (
          <div key={idx} className="relative flex-shrink-0">
            <img
              src={url}
              alt={file.name}
              className="h-16 w-16 rounded-lg object-cover shadow-sm"
            />
            {/* Remove button */}
            <button
              onClick={() => onRemove(idx)}
              aria-label={`Remove ${file.name}`}
              className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-gray-700 text-white hover:bg-red-500"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-3 w-3"
              >
                <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
              </svg>
            </button>
          </div>
        )
      })}
      <p className="ml-1 flex-shrink-0 text-xs text-gray-500">
        {files.length} photo{files.length > 1 ? 's' : ''} ready to send
      </p>
    </div>
  )
}
