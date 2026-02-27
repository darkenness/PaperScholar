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
          900: '#0a0a0a', // Deepest background
          800: '#121212', // Slightly lighter for panels
          700: '#1a1a1a', // Hover states
          600: '#2a2a2a', // Borders and dividers
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
        'grid-pattern': 'linear-gradient(to right, #2a2a2a 1px, transparent 1px), linear-gradient(to bottom, #2a2a2a 1px, transparent 1px)',
      }
    },
  },
  plugins: [],
};

export default config;
