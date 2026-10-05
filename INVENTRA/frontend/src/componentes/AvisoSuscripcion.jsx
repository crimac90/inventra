/*
  Estado de la suscripcion en el panel (RF-SUS-01 y RF-SUS-03).

  El manual de usuario lo promete con estas palabras: «En el panel principal
  veras cuantos dias te quedan». Por eso esta franja existe ya, aunque el plan
  del modulo la situara en un bloque posterior: un manual entregado que promete
  algo que no esta es la clase de contradiccion que llevamos dias corrigiendo.

  Cuatro situaciones y tres tonos:
    - sin suscripcion vigente: de error, porque el negocio dejo de poder registrar;
    - en mora: de error tambien, porque todavia opera pero hay que actuar hoy;
    - en prueba: informativo, y de advertencia en los ultimos dias;
    - plan contratado a punto de vencer: de advertencia.
  Con el plan contratado y al dia no se muestra nada: una franja permanente que
  dice «todo bien» deja de leerse a los dos dias.

  Ningun umbral se escribe aqui. Cuantos dias faltan, cuantos quedan antes de la
  suspension y si toca avisar los resuelve el servidor, donde estan las
  constantes; un numero repetido en dos lenguajes acaba valiendo cosas distintas
  en cada uno (regla 14).
*/

import { useEffect, useState } from "react";

import { consultarMiSuscripcion } from "../api/suscripciones";
import { plural as dias } from "../texto";

export default function AvisoSuscripcion() {
  const [suscripcion, setSuscripcion] = useState(null);

  useEffect(() => {
    let vigente = true;
    consultarMiSuscripcion()
      .then((datos) => vigente && setSuscripcion(datos))
      .catch(() => vigente && setSuscripcion(null));
    return () => {
      vigente = false;
    };
  }, []);

  if (!suscripcion) return null;

  if (!suscripcion.puede_operar) {
    return (
      <div className="aviso err" role="status">
        Tu suscripción no está vigente. Puedes consultar tu información, pero el sistema no
        admite registrar operaciones nuevas hasta que actives un plan.
      </div>
    );
  }

  /*
    En mora el negocio SIGUE OPERANDO: es una advertencia, no un error. Estuvo
    en rojo, que es el color de «no se pudo», mientras el sistema funcionaba con
    normalidad (punto 6.4 del documento de diseño).
  */
  if (suscripcion.estado === "en_mora") {
    const restantes = suscripcion.dias_para_suspension;
    return (
      <div className="aviso advertencia" role="status">
        <b>Tu plan venció y sigue funcionando {dias(restantes, "día más", "días más")}.</b>{" "}
        Comunícate para renovarlo. Si no lo haces, podrás seguir consultando tu información,
        pero no registrar operaciones nuevas.
      </div>
    );
  }

  if (suscripcion.es_prueba) {
    const restantes = suscripcion.dias_restantes;
    return (
      <div className={suscripcion.avisa_vencimiento ? "aviso advertencia" : "aviso ok"} role="status">
        <b>
          {restantes === 0
            ? "Hoy es el último día de tu prueba gratuita."
            : `${dias(restantes, "día", "días")} de tu prueba gratuita.`}
        </b>{" "}
        Durante la prueba tienes disponibles todas las funciones del plan {suscripcion.plan}.
        Al terminar, tu información se conserva y la puedes seguir consultando.
      </div>
    );
  }

  if (suscripcion.avisa_vencimiento) {
    const restantes = suscripcion.dias_restantes;
    return (
      <div className="aviso advertencia" role="status">
        <b>
          {restantes === 0
            ? "Tu plan vence hoy."
            : `Tu plan vence en ${dias(restantes, "día", "días")}.`}
        </b>{" "}
        Renuévalo para seguir registrando operaciones sin interrupción.
      </div>
    );
  }

  return null;
}
