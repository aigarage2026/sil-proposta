// ESLint v9 flat-config — replaces the legacy .eslintrc.* that was removed.
// Mirrors what the Vite React-TS template ships: typescript-eslint recommended +
// react-hooks rules of hooks + react-refresh "only-export-components" so HMR
// keeps working when authors export non-components from a route file.

import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Don't lint generated/external dirs.
  { ignores: ['dist', 'build', 'node_modules', 'coverage'] },

  // Base recommended rules + TypeScript rules.
  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // The codebase uses `any` in a few hand-rolled API client utilities;
      // tighten to warn so it shows up in review without blocking CI.
      '@typescript-eslint/no-explicit-any': 'warn',
      // i18n string keys are sometimes accessed dynamically.
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
)
