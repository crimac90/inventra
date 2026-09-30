/*
  Estado de la suscripcion en el panel (RF-SUS-01 y RF-SUS-03).

  El manual de usuario lo promete con estas palabras: «En el panel principal
  veras cuantos dias te quedan». Por eso esta franja existe ya, aunque el plan
  del modulo la situara en un bloque posterior: un manual entregado que promete
  algo que no esta es la clase de contradiccion que llevamos dias corrigiendo.

  Tres situaciones y tres tonos:
    - en prueba, con dias de sobra: informativo;
    - en prueba, con tres dias o menos: de advertencia, porque ya hay que actuar;
    - sin suscripcion vigente: de error, porque el negocio dejo de poder registrar.
  Cuando el plan esta contratado y al dia no se muestra nada: una franja
  permanente que dice «todo bien» deja de leerse a los dos dias.
*/

import { useEffect, useState } from "react";

import { consultarMiSuscripcion } from "../api/suscripciones";

const DIAS_DE_AVISO = 3;

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

  if (!suscripcion.es_prueba) return null;

  const dias = suscripcion.dias_restantes;
  const urgente = dias <= DIAS_DE_AVISO;

  return (
    <div className={urgente ? "aviso err" : "aviso ok"} role="status">
      <b>
        {dias === 0
          ? "Hoy es el último día de tu prueba gratuita."
          : dias === 1
            ? "Queda 1 día de tu prueba gratuita."
            : `Quedan ${dias} días de tu prueba gratuita.`}
      </b>{" "}
      Durante la prueba tienes disponibles todas las funciones del plan {suscripcion.plan}.
      Al terminar, tu información se conserva y la puedes seguir consultando.
    </div>
  );
}
