import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const here = fileURLToPath(new URL('.', import.meta.url))
const harness = resolve(here, '../../../../oss/deepseek-harness')

export default {
  resolve: {
    alias: {
      '@deepseek-ai/cordis': resolve(harness, 'vendor/cordis/src/index.ts'),
      '@deepseek-ai/cosmokit': resolve(harness, 'vendor/cosmokit/src/index.ts'),
    },
  },
  test: {
    include: ['tests/**/*.test.ts'],
    environment: 'node',
  },
}
