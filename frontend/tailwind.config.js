/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'wa-teal':        '#075E54',
        'wa-green':       '#128C7E',
        'wa-light-green': '#25D366',
        'wa-sent':        '#DCF8C6',
        'wa-bg':          '#ECE5DD',
      },
    },
  },
  plugins: [],
}