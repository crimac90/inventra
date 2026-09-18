// Configuracion de Vite, la herramienta que levanta el servidor de desarrollo y
// empaqueta la aplicacion para publicarla.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // El puerto tiene que coincidir con CORS_ORIGENES del backend.
    port: 5173,
    strictPort: true,
  },
});
