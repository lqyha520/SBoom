import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: { setupFiles: ['src/__tests__/setup.ts'], environment: 'happy-dom', include: ['src/**/*.test.ts'], clearMocks: true, restoreMocks: true },
})
