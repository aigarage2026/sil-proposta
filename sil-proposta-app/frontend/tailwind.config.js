/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#3B7BF8', dark: '#2563EB', light: '#EFF6FF' },
        teal: { DEFAULT: '#0D9488', light: '#F0FDFA' },
        surface: { DEFAULT: '#F4F6FA', card: '#FFFFFF', dark: '#0F172A' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
