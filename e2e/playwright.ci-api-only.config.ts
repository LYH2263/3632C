import { defineConfig } from '@playwright/test';

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: './specs',
  fullyParallel: true,
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  workers: 1,
  retries: isCI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: './playwright-report', open: 'never' }]
  ],
  outputDir: './test-results',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    baseURL: 'http://127.0.0.1:8001'
  },
  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
  webServer: [
    {
      command: 'pnpm --filter backend run e2e:serve',
      url: 'http://127.0.0.1:8001/api/v1/merchants',
      timeout: 180_000,
      reuseExistingServer: !isCI
    }
  ],
  projects: [
    {
      name: 'api-only',
      testMatch: ['api/backend/**/*.spec.ts'],
      workers: 1
    }
  ]
});
