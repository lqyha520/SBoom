import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

// 保留现有紧凑排版，只检查影响行为的错误；类型边界由 vue-tsc 验证。
export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...vue.configs['flat/essential'],
  {
    files: ['src/**/*.{ts,vue}', 'scripts/**/*.mjs'],
    languageOptions: { parserOptions: { parser: tseslint.parser, ecmaVersion: 'latest', sourceType: 'module' } },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: {
      ...js.configs.recommended.rules,
      'no-undef': 'off', 'no-unused-vars': 'off', 'no-empty': ['error', { allowEmptyCatch: true }],
      'no-empty-pattern': 'off', 'no-constant-condition': ['error', { checkLoops: false }],
      'no-useless-escape': 'off', 'no-control-regex': 'off', 'vue/multi-word-component-names': 'off',
      'vue/no-parsing-error': ['error', { 'x-invalid-end-tag': false }],
    },
  },
  { files: ['src/services/checkout.ts'], rules: { 'no-unreachable': 'off' } },
  { files: ['src/**/*.ts'], languageOptions: { parser: tseslint.parser } },
]
