import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './browser-tests', outputDir: '../artifacts/admin-browser-tests',
  fullyParallel: true, forbidOnly: !!process.env.CI, retries: process.env.CI ? 2 : 0,
  workers: 2, timeout: 45000, expect: { timeout: 10000 }, reporter: [['list']],
  use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 }, baseURL: 'http://127.0.0.1:5179', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: 'pnpm exec vite preview --host 127.0.0.1 --port 5179 --strictPort', url: 'http://127.0.0.1:5179/admin/', reuseExistingServer: false },
})
