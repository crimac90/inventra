/*
  Interruptor de modo claro y oscuro.

  Es un boton, no una casilla ni un desplegable: la accion es una sola y tiene
  dos estados. El icono muestra a donde lleva pulsarlo —la luna cuando se esta
  en claro, el sol cuando se esta en oscuro—, y como un icono solo no dice nada
  a quien no lo ve, el boton lleva su etiqueta escrita y `aria-pressed` para que
  un lector de pantalla anuncie si el modo oscuro esta activado.

  Los dos dibujos son de la misma familia que los de la barra lateral: reticula
  de 24 pixeles, trazo de 1,8 y sin relleno, de modo que toman el color del texto
  que los rodea.
*/

import useTema from "../tema/useTema";

const LUNA = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
  </svg>
);

const SOL = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
  </svg>
);

export default function InterruptorTema({ className = "nav", soloIcono = false }) {
  const { tema, alternarTema } = useTema();
  const oscuro = tema === "oscuro";
  const texto = oscuro ? "Modo claro" : "Modo oscuro";

  /*
    En la barra lateral el boton se lee; en el panel de marca del acceso no cabe
    mas que el icono, y entonces el texto pasa a `aria-label`, que es lo que
    anuncia un lector de pantalla. El icono nunca se queda solo ante quien no
    puede verlo.
  */
  return (
    <button
      type="button"
      className={className}
      onClick={alternarTema}
      aria-pressed={oscuro}
      aria-label={soloIcono ? texto : undefined}
      title={texto}
    >
      {oscuro ? SOL : LUNA}
      {!soloIcono && ` ${texto}`}
    </button>
  );
}
