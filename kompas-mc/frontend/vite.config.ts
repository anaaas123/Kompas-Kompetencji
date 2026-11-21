import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Wersja MC: frontend 5174, API 8002 (wersja 1: 5173 i 8001).
const api = process.env.KOMPAS_MC_API ?? "http://127.0.0.1:8002";

export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true, proxy: { "/api": api } },
});
