import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      // SSE 需要对象格式，禁用代理超时，防止 http-proxy 因静默断连关闭长连接
      "/stream": {
        target: "http://localhost:8000",
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
});
