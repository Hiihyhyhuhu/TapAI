/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        panel: '#0B0D13',
        surface: '#11141D',
        elevated: '#171B26',
        highlight: '#1E2332',
        subtle: '#282F44',
        border: '#202637',
        'border-light': '#2D354D',
        brand: '#10B981',
        'brand-focus': '#059669',
        'brand-subtle': 'rgba(16, 185, 129, 0.08)',
      }
    },
  },
  plugins: [],
}
