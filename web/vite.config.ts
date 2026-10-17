import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Explicit port: 5173 is Vite's default and collides with other local
    // projects (Playwright's reuseExistingServer can then hit the wrong app).
    port: 5273,
    strictPort: true,
    proxy: {
      "/v1": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
