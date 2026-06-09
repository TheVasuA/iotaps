import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

// Flat ESLint config for the Vite + React SPA.
export default [
  { ignores: ["dist", "node_modules"] },
  // Application source (browser, JSX).
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: "latest",
        ecmaFeatures: { jsx: true },
        sourceType: "module",
      },
    },
    settings: { react: { version: "detect" } },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      // Mark JSX-referenced identifiers as used (avoids false no-unused-vars).
      "react/jsx-uses-react": "error",
      "react/jsx-uses-vars": "error",
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  // Build/config files run under Node.
  {
    files: ["*.config.js", "postcss.config.js", "tailwind.config.js"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.node },
      sourceType: "module",
    },
    rules: {
      ...js.configs.recommended.rules,
    },
  },
];
