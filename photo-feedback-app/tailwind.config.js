/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#2D7D9A',
        secondary: '#5BA88F',
        accent: '#E8A849',
        background: '#F8F6F3',
        card: '#FFFFFF',
        textPrimary: '#2C3E50',
        textSecondary: '#7F8C8D',
        danger: '#E74C3C',
        safe: '#27AE60',
        warning: '#F39C12',
      },
      fontFamily: {
        sans: ['Noto Sans SC', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'card': '16px',
        'button': '12px',
      },
    },
  },
  plugins: [],
}