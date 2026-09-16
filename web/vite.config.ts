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
    // Same origem entre React e API, em dev também (produção já é assim --
    // ver Documentação/Deploy e Operação, "Sirva o React e a API na mesma
    // origem"). É o que faz o cookie HttpOnly de sessão (app/core/auth.py
    // ::cookie_backend) funcionar sem CORS com credenciais. O proxy roda no
    // servidor Vite, dentro do container -- por isso o alvo é o nome do
    // serviço na rede do Compose (api:8000), não localhost. O browser só
    // enxerga o caminho relativo /api/...
    proxy: {
      "/api": {
        target: "http://api:8000",
        changeOrigin: true,
      },
    },
  },
});
