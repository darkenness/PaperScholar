import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#18181b', // Main background (Lighter dark, zinc-900)
          800: '#27272a', // Panel background (zinc-800)
          700: '#3f3f46', // Hover states (zinc-700)
          600: '#52525b', // Borders and dividers (zinc-600)
        },
        paper: {
          100: '#f5f4ed', // Lighter paper (panels)
          200: '#eae7db', // Base paper color (user provided)
          300: '#e0dcd0', // Darker paper (hover/active)
          700: '#a3a093', // Paper borders/dividers
          900: '#2d3748', // Deep ink color for text in light mode
        },
        primary: {
          300: '#93bbfd',
          400: '#60a5fa',
          500: '#2563eb', // Academic/Technical Blue
          600: '#1d4ed8',
          700: '#1e40af',
        },
        accent: {
          400: '#fbbf24',
          500: '#f59e0b', // Amber for technical warnings/highlights
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', '"Courier New"', 'monospace'],
      },
      backgroundImage: {
        'grid-pattern-dark': 'linear-gradient(to right, #52525b33 1px, transparent 1px), linear-gradient(to bottom, #52525b33 1px, transparent 1px)',
        'grid-pattern-light': 'linear-gradient(to right, #a3a09333 1px, transparent 1px), linear-gradient(to bottom, #a3a09333 1px, transparent 1px)',
      }
    },
  },
  plugins: [],
};

export default config;
