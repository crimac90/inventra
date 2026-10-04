/*
  Mapa de rutas de la aplicacion.

  Cada direccion del navegador se corresponde con una pantalla. Las publicas son
  las del acceso y la recuperacion; las internas van envueltas en RutaPrivada,
  que exige sesion.
*/

import { Navigate, Route, Routes } from "react-router-dom";

import Acceso from "./paginas/Acceso";
import MiSuscripcion from "./paginas/MiSuscripcion";
import Panel from "./paginas/Panel";
import Perfil from "./paginas/Perfil";
import Plataforma from "./paginas/Plataforma";
import Recuperar from "./paginas/Recuperar";
import Registro from "./paginas/Registro";
import Usuarios from "./paginas/Usuarios";
import Restablecer from "./paginas/Restablecer";
import VerificarCorreo from "./paginas/VerificarCorreo";
import RutaPrivada from "./sesion/RutaPrivada";
import { ROLES_DE_NEGOCIO, ROL_DE_PLATAFORMA } from "./sesion/destino";

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
      {/* Igual que la anterior: la arma el backend en seguridad/correo.py. */}
      <Route path="/verificar-correo" element={<VerificarCorreo />} />

      {/*
        Internas: exigen sesion. Las tres siguientes son de un negocio, de modo
        que llevan la lista de roles que las puede ver; el operador de INVENTRA
        no tiene licorera y el panel principal le hablaria de «tu licorera» sin
        que exista ninguna.
      */}
      <Route
        path="/panel"
        element={
          <RutaPrivada roles={ROLES_DE_NEGOCIO}>
            <Panel />
          </RutaPrivada>
        }
      />
      <Route
        path="/usuarios"
        element={
          <RutaPrivada roles={ROLES_DE_NEGOCIO}>
            <Usuarios />
          </RutaPrivada>
        }
      />
      <Route
        path="/mi-suscripcion"
        element={
          <RutaPrivada roles={ROLES_DE_NEGOCIO}>
            <MiSuscripcion />
          </RutaPrivada>
        }
      />
      {/*
        Reservada al operador de INVENTRA. Un administrador de licorera que
        escriba esta direccion vuelve a su panel; no es un castigo, es que esta
        pantalla no tiene nada suyo.
      */}
      <Route
        path="/plataforma"
        element={
          <RutaPrivada roles={[ROL_DE_PLATAFORMA]}>
            <Plataforma />
          </RutaPrivada>
        }
      />
      {/* El perfil no lleva lista: todo el que tiene sesion tiene perfil. */}
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
