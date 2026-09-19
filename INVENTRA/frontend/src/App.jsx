/*
  Mapa de rutas de la aplicacion.

  Cada direccion del navegador se corresponde con una pantalla. Las publicas son
  las del acceso y la recuperacion; las internas van envueltas en RutaPrivada,
  que exige sesion.
*/

import { Navigate, Route, Routes } from "react-router-dom";

import Acceso from "./paginas/Acceso";
import Panel from "./paginas/Panel";
import Perfil from "./paginas/Perfil";
import Recuperar from "./paginas/Recuperar";
import Registro from "./paginas/Registro";
import Restablecer from "./paginas/Restablecer";
import RutaPrivada from "./sesion/RutaPrivada";

export default function App() {
  return (
    <Routes>
      {/* La raiz manda al acceso; si ya hay sesion, RutaPrivada deja pasar al panel. */}
      <Route path="/" element={<Navigate to="/acceso" replace />} />

      {/* Publicas: quien las usa todavia no puede iniciar sesion. */}
      <Route path="/acceso" element={<Acceso />} />
      <Route path="/registro" element={<Registro />} />
      <Route path="/recuperar" element={<Recuperar />} />
      {/*
        Esta direccion la arma el backend en seguridad/correo.py. Si se cambia
        aqui, hay que cambiarla alli: el enlace del correo dejaria de funcionar.
      */}
      <Route path="/restablecer-contrasena" element={<Restablecer />} />

      {/* Internas: exigen sesion. */}
      <Route
        path="/panel"
        element={
          <RutaPrivada>
            <Panel />
          </RutaPrivada>
        }
      />
      <Route
        path="/perfil"
        element={
          <RutaPrivada>
            <Perfil />
          </RutaPrivada>
        }
      />

      {/* Cualquier direccion desconocida vuelve al acceso. */}
      <Route path="*" element={<Navigate to="/acceso" replace />} />
    </Routes>
  );
}
