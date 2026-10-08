/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    fontFamily: {
      sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
      mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
    },
    fontSize: {
      xs: ['0.75rem', { lineHeight: '1.125rem' }],
      sm: ['0.875rem', { lineHeight: '1.375rem' }],
      base: ['1rem', { lineHeight: '1.625rem' }],
      lg: ['1.125rem', { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
      xl: ['1.25rem', { lineHeight: '1.75rem', letterSpacing: '-0.015em' }],
      '2xl': ['1.625rem', { lineHeight: '2.125rem', letterSpacing: '-0.02em' }],
    },
    extend: {
      colors: {
        'bg-primary': '#0f1117',
        'bg-secondary': '#1a1d2e',
        'bg-card': '#1e2235',
        'accent': '#6366f1',
        'accent-hover': '#4f46e5',
        border: '#2d3148',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        shimmer: 'shimmer 1.5s infinite linear',
      },
    },
  },
  plugins: [],
}
