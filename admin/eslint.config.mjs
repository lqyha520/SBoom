import vue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'

export default defineConfigWithVueTs(
  { ignores: ['dist/**', 'node_modules/**', '*.d.ts'] },
  vue.configs['flat/essential'],
  vueTsConfigs.base,
  {
    files: ['**/*.ts', '**/*.vue'],
    rules: {
      'no-debugger': 'error',
      'no-constant-condition': 'error',
      'no-dupe-else-if': 'error',
      'no-unreachable': 'error',
      // 卷面编辑组件按约定回写同一份响应式试卷；v-html 的净化由 sanitizeRich 统一负责。
      'vue/no-mutating-props': 'off',
      'vue/no-v-html': 'off',
      'vue/multi-word-component-names': ['error', { ignores: ['Dashboard', 'Reconciliations'] }],
    },
  },
)
