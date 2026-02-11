import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const DEFAULT_API_BASE_PATH = '/api'
const DEFAULT_PROXY_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBasePath = normalizeApiBasePath(env.VITE_API_BASE_PATH)
  const proxyTarget = env.DEV_API_PROXY_TARGET || DEFAULT_PROXY_TARGET

  return {
    plugins: [react()],
    server: {
      proxy: {
        [apiBasePath]: {
          target: proxyTarget,
          changeOrigin: true,
          secure: false,
          rewrite: (path) =>
            path.replace(new RegExp(`^${escapeRegExp(apiBasePath)}`), ''),
        },
      },
    },
  }
})

function normalizeApiBasePath(value: string | undefined): string {
  if (!value) {
    return DEFAULT_API_BASE_PATH
  }
  const withLeadingSlash = value.startsWith('/') ? value : `/${value}`
  const withoutTrailingSlash = withLeadingSlash.replace(/\/+$/, '')
  return withoutTrailingSlash || DEFAULT_API_BASE_PATH
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
