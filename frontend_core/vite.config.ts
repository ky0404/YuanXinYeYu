import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 所有 /api 开头的请求代理到后端 8000 端口
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      // 兼容旧路径 /emo_analysis
      '/emo_analysis': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 生产构建优化
    rollupOptions: {
      output: {
        // 仅仅这里改为了函数形式，解决了 TS2769 报错，其余逻辑完全保留你的原版
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react')) return 'vendor';
            if (id.includes('antd') || id.includes('@ant-design')) return 'antd';
            if (id.includes('axios')) return 'http';
          }
        },
      },
    },
    chunkSizeWarningLimit: 1000,
  },
})