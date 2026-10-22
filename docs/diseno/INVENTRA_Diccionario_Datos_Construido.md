# INVENTRA — Diccionario de datos del sistema construido

> Generado el 2026-10-22 con `py manage.py generar_diccionario_datos`  
> Django 5.2.17 · motor mysql · base «inventra»  
> **No se edita a mano:** se cambia el modelo y se vuelve a generar.

## Cómo leer este documento

Cada tabla del sistema construido, con el tipo **real** de cada columna en MySQL. Se genera
desde los modelos con `py manage.py generar_diccionario_datos`, así que no puede contradecir
a la base de datos.

El modelo entidad-relación del proyecto (`INVENTRA_MER_MR_Diccionario.docx`) sigue siendo el
documento de diseño y no se modifica: describe las veinticuatro entidades del sistema
completo tal como se concibieron. Este anexo describe lo que hay construido hasta la fecha.

## Dos convenciones del marco de trabajo

Hay dos diferencias sistemáticas entre los tipos del diseño y los de la base construida. No
son descuidos: cada una responde a una razón, que se explica a continuación.

**Las llaves primarias y foráneas son `bigint`, no `int unsigned`.** Es el tipo que Django
aplica por defecto a los identificadores automáticos, para no agotar el rango en tablas que
crecen sin parar —el kardex y las ventas lo hacen—. Una llave foránea copia el tipo de la
llave a la que apunta, así que la convención se propaga. Se adoptó tal cual: bajarlo a
`int unsigned` exigiría una migración de alteración en cada tabla y en cada módulo nuevo, y
no ganaría nada medible para el tamaño de negocio al que apunta INVENTRA.

**Las columnas de lista cerrada son `varchar`, no `ENUM`.** Django no genera `ENUM` en
ningún caso, y es deliberado: alterar un `ENUM` en MySQL obliga a reescribir la tabla
completa y no es portable entre motores. Lo que hace es guardar el valor como texto y
comprobar la lista de valores válidos en la aplicación, lo que da el mismo resultado para el
usuario y permite añadir un estado nuevo con una migración trivial. Los valores admitidos de
cada una de estas columnas se indican en su descripción.

---

## Módulo SUS — Suscripciones

### Tabla: `licorera`

El cliente de INVENTRA.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `nombre` | varchar(100) | No | — | Nombre comercial del negocio. |
| `nit` | varchar(20) | Sí | UQ | NIT o cédula del propietario. Único si se registra. |
| `direccion` | varchar(150) | Sí | — | Dirección principal del negocio. |
| `telefono` | varchar(20) | Sí | — | Teléfono de contacto. |
| `correo` | varchar(100) | No | — | Correo de contacto del negocio. |
| `fecha_registro` | datetime(6) | No | — | Cuándo se creó la cuenta en la plataforma. |
| `activo` | bool | No | — | Baja lógica: una licorera retirada conserva su historial. |

### Tabla: `plan`

Catálogo de planes comerciales.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `nombre` | varchar(30) | No | UQ | Nombre comercial del plan: Básico o Pro. |
| `precio_mensual` | numeric(12, 2) | No | — | Precio de lista de la suscripción mensual. |
| `maximo_sedes` | integer UNSIGNED | Sí | — | Límite de sedes. Vacío significa sin límite. |
| `maximo_usuarios` | integer UNSIGNED | Sí | — | Límite de usuarios. Vacío significa sin límite. |
| `permite_facturacion` | bool | No | — | Si el plan habilita la facturación electrónica. |
| `permite_reportes_avanzados` | bool | No | — | Si el plan habilita rotación y utilidad. |
| `activo` | bool | No | — | Permite retirar un plan sin borrar su historial. |

### Tabla: `suscripcion`

Historial de contratación de planes.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `plan_id` | bigint | No | FK → `plan` | Plan contratado en este período. |
| `estado` | varchar(12) | No | — | Estado actual de la suscripción. Valores admitidos: `en_prueba`, `activa`, `en_mora`, `suspendida`, `cancelada`. |
| `fecha_inicio` | date | No | — | Inicio de la vigencia. |
| `fecha_fin` | date | Sí | — | Hasta cuándo vale esta suscripción. La define el Administrador INVENTRA al activar y al renovar, y no puede ser una fecha pasada (RF-SUS-03); al cambiar de plan se acorta al día del cambio. |
| `precio_pactado` | numeric(12, 2) | No | — | Precio congelado al contratar; los aumentos no cambian el histórico. |

---

## Módulo SEG — Seguridad

### Tabla: `rol`

Catálogo de roles del sistema (RF-SEG-05).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `nombre` | varchar(30) | No | UQ | «administrador_licorera», «vendedor» o «administrador_inventra». |
| `descripcion` | varchar(150) | No | — | Qué puede hacer el rol, en lenguaje claro. |

### Tabla: `usuario`

Cuentas de acceso al sistema (RF-SEG-01, 02, 04, 06 y 07).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | Sí | FK → `licorera` | Licorera a la que pertenece. Vacío para el personal de INVENTRA. |
| `rol_id` | bigint | No | FK → `rol` | Rol que define sus permisos. |
| `nombre_completo` | varchar(100) | No | — | Nombre de la persona. |
| `correo` | varchar(100) | No | UQ | Identificador de acceso; único en toda la plataforma. |
| `correo_verificado` | bool | No | — | Si la persona confirmó su correo abriendo el enlace que se le envió. Una cuenta sin verificar entra al sistema, pero ve un aviso. |
| `telefono` | varchar(20) | Sí | — | Teléfono de contacto. |
| `contrasena_hash` | varchar(255) | No | — | Contraseña cifrada con hash adaptativo; nunca en texto plano (RNF-02). |
| `intentos_fallidos` | smallint UNSIGNED | No | — | Contador para el bloqueo tras cinco intentos (RF-SEG-02). |
| `bloqueado_hasta` | datetime(6) | Sí | — | Fin del bloqueo temporal. Vacío si no está bloqueado. |
| `activo` | bool | No | — | Baja lógica: el inactivo no entra, su historial permanece. |
| `fecha_creacion` | datetime(6) | No | — | Cuándo se creó la cuenta. |
| `ultimo_acceso` | datetime(6) | Sí | — | Última vez que la persona entró al sistema. |

---

## Módulo SED — Sedes

### Tabla: `sede`

Punto de venta físico de una licorera (RF-SED-01).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `nombre` | varchar(80) | No | — | Nombre de la sede («Sede principal», «Sucursal Centro»…). |
| `direccion` | varchar(150) | Sí | — | Dirección física. |
| `telefono` | varchar(20) | Sí | — | Teléfono de la sede. |
| `activo` | bool | No | — | Baja lógica: una sede cerrada conserva su historial. |

---

## Módulo INV — Inventario

### Tabla: `categoria`

Categorías del catálogo, propias de cada licorera.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `nombre` | varchar(50) | No | — | Nombre de la categoría. |
| `margen_sugerido` | numeric(5, 2) | No | — | Porcentaje sobre el costo con el que se propone el precio de venta de sus productos. El sistema propone; nunca aplica. |
| `activo` | bool | No | — | Baja lógica. |

### Tabla: `entrada_mercancia`

Llegada de mercancía del proveedor (RF-INV-05).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `sede_id` | integer | No | FK → `sede` | Sede que recibe la mercancía. |
| `usuario_id` | bigint | No | FK → `usuario` | Quién registró la entrada. |
| `proveedor` | varchar(100) | Sí | — | Nombre del proveedor (texto libre en esta versión). |
| `fecha` | datetime(6) | No | — | Fecha y hora de la entrada. |
| `observacion` | varchar(255) | Sí | — | Nota opcional (número de factura del proveedor, etc.). |

### Tabla: `lote_inventario`

Un lote de mercancía con su costo congelado.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `producto_id` | integer | No | FK → `producto` | Referencia a la que pertenece el lote. |
| `sede_id` | integer | No | FK → `sede` | Sede donde está físicamente el lote (las existencias son por sede). |
| `origen` | varchar(15) | No | — | Cómo nació el lote. Valores admitidos: `compra`, `traslado`, `ajuste_positivo`. |
| `entrada_id` | integer | Sí | FK → `entrada_mercancia` | Entrada que lo creó (vacío si nació de un ajuste). |
| `cantidad_inicial` | integer UNSIGNED | No | — | Unidades con las que nació el lote. |
| `cantidad_disponible` | integer UNSIGNED | No | — | Unidades que aún quedan; el PEPS consume primero los más antiguos. |
| `costo_unitario` | numeric(12, 2) | No | — | Costo de adquisición congelado; no se altera por compras posteriores. |
| `fecha_ingreso` | datetime(6) | No | — | Define el orden PEPS (primero en entrar, primero en salir). |

### Tabla: `movimiento_inventario`

El kardex: registro **inmutable** de todo movimiento de existencias (RF-INV-06 y RF-INV-09).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `producto_id` | integer | No | FK → `producto` | Referencia afectada. |
| `sede_id` | integer | No | FK → `sede` | Sede afectada. |
| `lote_id` | integer | Sí | FK → `lote_inventario` | Lote afectado, si aplica. |
| `tipo` | varchar(16) | No | — | Naturaleza del movimiento. Valores admitidos: `entrada`, `venta`, `anulacion_venta`, `ajuste_positivo`, `ajuste_negativo`, `traslado_salida`, `traslado_entrada`. |
| `cantidad` | integer | No | — | Positiva si suma a las existencias, negativa si resta. |
| `costo_unitario` | numeric(12, 2) | Sí | — | Costo asociado al movimiento, para el kardex valorizado. |
| `documento_tipo` | varchar(10) | No | — | Tipo del documento que originó el movimiento. Valores admitidos: `entrada`, `venta`, `traslado`, `ajuste`. |
| `documento_id` | bigint | No | — | Identificador del documento origen (trazabilidad total). |
| `usuario_id` | bigint | No | FK → `usuario` | Quién causó el movimiento. |
| `motivo` | varchar(255) | Sí | — | Obligatorio en los ajustes (RF-INV-06): merma, rotura, conteo… |
| `saldo_resultante` | integer UNSIGNED | No | — | Existencias del producto en la sede después del movimiento. |
| `fecha` | datetime(6) | No | — | Fecha y hora del movimiento. |

### Tabla: `producto`

Referencia del catálogo de una licorera (RF-INV-01 a 04).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `categoria_id` | integer | No | FK → `categoria` | Categoría del producto. |
| `nombre` | varchar(120) | No | — | Nombre de la referencia («Aguardiente Antioqueño 750 ml»). |
| `presentacion` | varchar(10) | No | — | Presentación comercial de la referencia. Valores admitidos: `media`, `botella`, `litro`, `garrafa`, `unidad`. |
| `codigo_barras` | varchar(50) | Sí | — | Código de barras; único dentro de la licorera si se registra. |
| `precio_venta` | numeric(12, 2) | No | — | Precio de venta vigente. Vive separado del costo (RF-INV-11) y solo lo cambia el administrador; las ventas ya hechas conservan el suyo. |
| `stock_minimo` | integer UNSIGNED | No | — | Umbral de la alerta de existencias bajas (RF-INV-07). |
| `activo` | bool | No | — | Baja lógica (RF-INV-04): no aparece en el punto de venta, conserva historial. |
| `fecha_creacion` | datetime(6) | No | — | Cuándo se creó la referencia. |

---

## Módulo VEN — Ventas

### Tabla: `cierre_caja`

El cierre de una jornada en una sede (RF-VEN-06).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `sede_id` | integer | No | FK → `sede` | Sede del cierre. |
| `fecha` | date | No | — | Jornada cerrada (de las 06:00 a las 06:00). |
| `total_efectivo` | numeric(12, 2) | No | — | Ventas en efectivo según el sistema. |
| `total_transferencia` | numeric(12, 2) | No | — | Ventas por transferencia según el sistema. |
| `total_tarjeta` | numeric(12, 2) | No | — | Ventas con tarjeta según el sistema. |
| `efectivo_contado` | numeric(12, 2) | No | — | Efectivo físico contado por el usuario. |
| `diferencia` | numeric(12, 2) | No | — | Contado menos lo que dice el sistema: negativo si falta dinero, positivo si sobra. Se guarda calculado para que el cierre se lea tal como quedó ese día. |
| `usuario_id` | bigint | No | FK → `usuario` | Quién hizo el cierre. |
| `observacion` | varchar(255) | Sí | — | Explicación de la diferencia. Mientras esté vacía, la jornada aparece avisada en el panel; se puede escribir después. |

### Tabla: `detalle_venta`

Una línea de la venta, con el precio congelado (RF-VEN-01).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `venta_id` | integer | No | FK → `venta` | Venta a la que pertenece la línea. |
| `producto_id` | integer | No | FK → `producto` | Referencia vendida. |
| `cantidad` | integer UNSIGNED | No | — | Unidades vendidas. |
| `precio_unitario` | numeric(12, 2) | No | — | Precio de venta congelado en el momento de vender. |
| `subtotal` | numeric(12, 2) | No | — | Cantidad por precio unitario. |

### Tabla: `medio_pago`

Cómo pagó el cliente (RF-VEN-02).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `nombre` | varchar(30) | No | UQ | Nombre del medio de pago. |
| `activo` | bool | No | — | Permite dejar de ofrecerlo sin borrar el historial que lo usa. |

### Tabla: `venta`

Encabezado de una venta del punto de venta (RF-VEN-01 a 05).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | integer AUTO_INCREMENT | No | PK | Identificador único interno de la fila. |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera dueña del registro; sostiene el aislamiento entre negocios. |
| `sede_id` | integer | No | FK → `sede` | Sede donde se vendió. |
| `usuario_id` | bigint | No | FK → `usuario` | Quién registró la venta. |
| `consecutivo` | integer UNSIGNED | No | — | Número visible para el negocio, único dentro de la licorera. Es el dato por el que un cliente nombra su compra. |
| `fecha` | datetime(6) | No | — | Fecha y hora; de ella se deriva la jornada a la que pertenece. |
| `total` | numeric(12, 2) | No | — | Suma de los subtotales del detalle. |
| `medio_pago_id` | integer | No | FK → `medio_pago` | Cómo pagó el cliente. |
| `monto_recibido` | numeric(12, 2) | Sí | — | Efectivo entregado por el cliente, para calcular el cambio. Vacío en los demás medios, donde no hay cambio que devolver. |
| `estado` | varchar(10) | No | — | Las ventas no se borran: se anulan (RF-VEN-04). Valores admitidos: `activa`, `anulada`. |
| `observacion` | varchar(60) | Sí | — | Nota corta para reconocer la venta: «mesa 1, pedido 3». El negocio también sirve mesas, y quien cobra necesita poder identificar después una venta que no se llevó el cliente en la mano. |
| `motivo_anulacion` | varchar(255) | Sí | — | Por qué se anuló; obligatorio al anular. |
| `anulada_por` | bigint | Sí | FK → `usuario` | Quién la anuló. No es quien la registró: anular es del administrador y cobrar es del vendedor. |
| `fecha_anulacion` | datetime(6) | Sí | — | Cuándo se anuló. No se deriva de la fecha de la venta: entre una y otra pueden pasar horas dentro de la misma jornada, y es el dato que ordena los hechos. |

