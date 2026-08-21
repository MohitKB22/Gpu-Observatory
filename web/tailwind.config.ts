import type { Config } from 'tailwindcss';

/**
 * NVIDIA-inspired dark technical palette: graphite surfaces, the NVIDIA green
 * accent used sparingly for signal rather than decoration, and severity colours
 * chosen to stay distinguishable for the common forms of colour blindness.
 */
const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './features/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#0a0c0b',
        surface: '#111413',
        elevated: '#171b19',
        overlay: '#1e2320',
        line: '#262b28',
        'line-strong': '#343a36',
        ink: '#e8ebe9',
        'ink-muted': '#9aa5a0',
        'ink-faint': '#6b756f',
        nvidia: {
          DEFAULT: '#76b900',
          bright: '#8fd400',
          dim: '#5a8c00',
          faint: 'rgba(118, 185, 0, 0.12)',
        },
        severity: {
          info: '#5b9dd9',
          low: '#4fb286',
          medium: '#d9a441',
          high: '#e0703c',
          critical: '#e05252',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '3px',
        md: '4px',
        lg: '6px',
      },
    },
  },
  plugins: [],
};

export default config;
