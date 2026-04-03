// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name:             '暖心树洞 - AI 情绪疏导',
        short_name:       '暖心树洞',
        description:      '大学生专属 AI 情绪分析与疏导应用',
        theme_color:      '#6366f1',
        background_color: '#f4f6f9',
        display:          'standalone',
        start_url:        '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/.*\/api\/.*/i,
            handler: 'NetworkOnly', // API 不缓存，始终走网络
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, secure: false },
      '/emo_analysis': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react')) return 'vendor-react'
            if (id.includes('antd')) return 'vendor-antd'
            if (id.includes('axios')) return 'vendor-http'
            return 'vendor'
          }
        },
      },
    },
    chunkSizeWarningLimit: 1000,
  },
})
