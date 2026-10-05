/*
  Ayudas de redaccion de la interfaz.

  POR QUE EXISTE ESTE ARCHIVO
  El manual de marca fija que se escribe el plural y no «(s)», y con el plural
  viene la concordancia: «1 cuentas registradas» hace dudar al lector de que el
  sistema haya contado bien, que es lo contrario de lo que un indicador debe
  transmitir.

  La regla estaba resuelta TRES veces en el frontend, cada una dentro de la
  pantalla que la necesito: una funcion propia en el aviso de suscripcion, un
  condicional escrito a mano en la lista de usuarios, y en el panel ni siquiera
  eso —ahi decia «1 cuentas registradas»—. No se incumplio por olvido: se
  incumplio porque no habia donde cumplirla. Una regla resuelta dentro del
  primer caso que la necesita es media regla (regla 14).

  Es el gemelo de `suscripciones/texto.py`, que hace lo mismo para los mensajes
  que salen por consola.
*/

export function plural(cantidad, singular, pluralIrregular) {
  if (cantidad === 1) return `${cantidad} ${singular}`;
  return `${cantidad} ${pluralIrregular || `${singular}s`}`;
}
