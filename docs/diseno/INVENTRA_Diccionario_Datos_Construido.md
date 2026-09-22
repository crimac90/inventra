# INVENTRA — Diccionario de datos del sistema construido

> Generado el 2026-09-21 con `py manage.py generar_diccionario_datos`  
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
son descuidos; conviene saber explicarlas.

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
| `id` | bigint AUTO_INCREMENT | No | PK | Id |
| `nombre` | varchar(100) | No | — | Nombre comercial del negocio. |
| `nit` | varchar(20) | Sí | UQ | NIT o cédula del propietario. Único si se registra. |
| `direccion` | varchar(150) | Sí | — | Direccion |
| `telefono` | varchar(20) | Sí | — | Telefono |
| `correo` | varchar(100) | No | — | Correo de contacto del negocio. |
| `fecha_registro` | datetime(6) | No | — | Cuándo se creó la cuenta en la plataforma. |
| `activo` | bool | No | — | Baja lógica: una licorera retirada conserva su historial. |

### Tabla: `plan`

Catálogo de planes comerciales.

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Id |
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
| `id` | bigint AUTO_INCREMENT | No | PK | Id |
| `licorera_id` | bigint | No | FK → `licorera` | Licorera |
| `plan_id` | bigint | No | FK → `plan` | Plan |
| `estado` | varchar(12) | No | — | Estado actual de la suscripción. Valores admitidos: `activa`, `en_mora`, `suspendida`, `cancelada`. |
| `fecha_inicio` | date | No | — | Inicio de la vigencia. |
| `fecha_fin` | date | Sí | — | Fin de la vigencia. Vacío mientras esté vigente. |
| `precio_pactado` | numeric(12, 2) | No | — | Precio congelado al contratar; los aumentos no cambian el histórico. |

---

## Módulo SEG — Seguridad

### Tabla: `rol`

Catálogo de roles del sistema (RF-SEG-05).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Id |
| `nombre` | varchar(30) | No | UQ | Nombre |
| `descripcion` | varchar(150) | No | — | Qué puede hacer el rol, en lenguaje claro. |

### Tabla: `usuario`

Cuentas de acceso al sistema (RF-SEG-01, 02, 04, 06 y 07).

| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |
|---|---|---|---|---|
| `id` | bigint AUTO_INCREMENT | No | PK | Id |
| `licorera_id` | bigint | Sí | FK → `licorera` | Licorera a la que pertenece. Vacío para el personal de INVENTRA. |
| `rol_id` | bigint | No | FK → `rol` | Rol que define sus permisos. |
| `nombre_completo` | varchar(100) | No | — | Nombre completo |
| `correo` | varchar(100) | No | UQ | Identificador de acceso; único en toda la plataforma. |
| `telefono` | varchar(20) | Sí | — | Telefono |
| `contrasena_hash` | varchar(255) | No | — | Password |
| `intentos_fallidos` | smallint UNSIGNED | No | — | Contador para el bloqueo tras cinco intentos (RF-SEG-02). |
| `bloqueado_hasta` | datetime(6) | Sí | — | Fin del bloqueo temporal. Vacío si no está bloqueado. |
| `activo` | bool | No | — | Baja lógica: el inactivo no entra, su historial permanece. |
| `fecha_creacion` | datetime(6) | No | — | Fecha creacion |
| `ultimo_acceso` | datetime(6) | Sí | — | Last login |

