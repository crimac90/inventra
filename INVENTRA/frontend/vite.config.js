// Configuracion de Vite, la herramienta que levanta el servidor de desarrollo y
// empaqueta la aplicacion para publicarla.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  /*
    Al compilar, los archivos de la interfaz cuelgan de /static/, que es la
    direccion por la que Django y el servidor publicado sirven los estaticos.
    Sin esto, el index.html pide /assets/... y ahi no hay nada: esa direccion
    la atiende el comodin que devuelve la propia pagina, de modo que el
    navegador recibe HTML donde espera una hoja de estilos.

    En desarrollo la base vuelve a ser la raiz, porque ahi quien sirve la
    interfaz es Vite en su propio puerto y no Django.
  */
  base: command === "build" ? "/static/" : "/",
  plugins: [react()],
  server: {
    // El puerto tiene que coincidir con CORS_ORIGENES del backend.
    port: 5173,
    strictPort: true,
  },
}));
