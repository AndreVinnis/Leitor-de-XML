import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Bind mount Windows -> container: inotify não pega as mudanças de
    // forma confiável, o Vite fica servindo um transform em cache até
    // reiniciar. Polling contorna isso.
    watch: { usePolling: true },
  },
});
