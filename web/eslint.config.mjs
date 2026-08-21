import coreWebVitals from 'eslint-config-next/core-web-vitals';
import typescriptConfig from 'eslint-config-next/typescript';

/**
 * ESLint flat config. eslint-config-next 16 exports flat-config arrays
 * directly, so no compatibility shim is required.
 */
export default [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts', 'coverage/**', '*.config.mjs'] },
  ...coreWebVitals,
  ...typescriptConfig,
  {
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
];
