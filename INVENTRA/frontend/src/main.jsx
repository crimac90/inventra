/*
  Punto de entrada de la interfaz.

  Aqui se monta React dentro del elemento «raiz» del index.html y se envuelve la
  aplicacion en dos capas: el enrutador, que traduce la direccion del navegador a
  una pantalla, y el proveedor de sesion, que guarda quien entro.
*/

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { ProveedorSesion } from "./sesion/ContextoSesion";

import "./estilos/base.css";
import "./estilos/acceso.css";

createRoot(document.getElementById("raiz")).render(
  <StrictMode>
    <BrowserRouter>
      <ProveedorSesion>
        <App />
      </ProveedorSesion>
    </BrowserRouter>
  </StrictMode>,
);
