# Despliegue local — INVENTRA

Guía para levantar el proyecto en un equipo de desarrollo.

- **Repositorio:** https://github.com/crimac90/inventra
- **Sistema operativo de referencia:** Windows 10/11 de 64 bits.

## 1. Requisitos previos

| Herramienta | Versión fijada | Comprobación |
|---|---|---|
| Python | 3.13.7 | `py --version` |
| Node.js | 22.19.0 | `node --version` |
| npm | 11.19.1 | `npm --version` |
| MySQL Community Server | 8.4 LTS | `mysql --version` |
| Git | 2.54 o superior | `git --version` |
| Editor | Visual Studio Code 1.132 o superior | `code --version` |

En Windows, el intérprete de Python se invoca con `py`. El comando `python3` no existe en
este sistema y `python` puede quedar capturado por el alias de la Tienda de Microsoft.

## 2. Instalación de MySQL

### 2.1 Descargar el instalador

Abrir `https://dev.mysql.com/downloads/mysql/8.4.html`, elegir el sistema operativo
*Microsoft Windows* y descargar el **MySQL Installer**. La página ofrece un enlace para
iniciar sesión o registrarse; debajo está la opción **No thanks, just start my download**,
que permite descargar sin cuenta.

### 2.2 Ejecutar el instalador

1. Abrir el archivo descargado. Si Windows pide permiso de administrador, aceptar.
2. En **Choosing a Setup Type**, seleccionar **Developer Default** y pulsar *Next*. Ese
   tipo instala el servidor, el cliente de línea de comandos y MySQL Workbench, que sirve
   para ver la base de datos con ventanas en lugar de comandos.
3. En **Check Requirements**, pulsar *Execute* si aparecen elementos pendientes y luego
   *Next*. Si algún componente opcional no se puede instalar, se puede continuar.
4. En **Installation**, pulsar *Execute* y esperar a que todos los elementos queden en
   verde. Después, *Next*.

### 2.3 Configurar el servidor

1. **Type and Networking:** tipo de configuración *Development Computer*, protocolo TCP/IP,
   puerto **3306** y la casilla de abrir el puerto en el firewall marcada. *Next*.
2. **Authentication Method:** elegir **Use Strong Password Encryption for Authentication**.
   Es el método moderno y el que espera la librería de conexión. *Next*.
3. **Accounts and Roles:** definir la contraseña del usuario `root`. Debe anotarse en un
   lugar seguro: sin ella no se puede administrar el servidor y no queda registrada en
   ningún archivo del proyecto. No se crean usuarios adicionales en este paso. *Next*.
4. **Windows Service:** dejar marcado *Configure MySQL Server as a Windows Service*,
   conservar el nombre propuesto y dejar marcado *Start the MySQL Server at System Startup*,
   para que la base de datos arranque sola con el equipo. *Next*.
5. **Apply Configuration:** pulsar *Execute*, esperar a que termine y *Finish*.
6. Completar el asistente hasta el final. Si al cerrar ofrece abrir MySQL Workbench, se
   puede cerrar sin abrirlo.

### 2.4 Agregar MySQL al PATH de Windows

El PATH es la lista de carpetas donde Windows busca los programas cuando se escribe un
comando en la consola. Si la carpeta de MySQL no está en esa lista, el comando `mysql`
responde «command not found» aunque el programa esté instalado.

1. Confirmar la ruta de instalación. Normalmente es
   `C:\Program Files\MySQL\MySQL Server 8.4\bin`. Para verificarlo, abrir esa carpeta en
   el Explorador de archivos y comprobar que dentro está el archivo `mysql.exe`.
2. Pulsar la tecla de Windows y escribir *variables de entorno*. Abrir la opción **Editar
   las variables de entorno del sistema**.
3. En la ventana que aparece, pulsar el botón **Variables de entorno…**, abajo a la derecha.
4. En el recuadro inferior, **Variables del sistema**, seleccionar la fila **Path** y pulsar
   **Editar…**.
5. Pulsar **Nuevo**, pegar la ruta de la carpeta `bin` del paso 1 y pulsar **Aceptar** en
   las tres ventanas abiertas, una por una.
6. Cerrar todas las consolas que estén abiertas y abrir una nueva. El PATH solo se recarga
   en las consolas que se abren después del cambio.

### 2.5 Verificar la instalación

En una consola nueva:

```
mysql --version
```

Debe responder con la versión del cliente. Si aún dice que el comando no existe, revisar
que la ruta agregada al PATH sea exactamente la carpeta que contiene `mysql.exe`.

## 3. Base de datos del proyecto

### 3.1 Entrar al cliente de MySQL

En Windows conviene usar **Símbolo del sistema** o **PowerShell** para esta parte. Git Bash
no maneja bien las ventanas que piden contraseña; si se usa Git Bash, el comando debe
anteponerse con `winpty`.

```
mysql -u root -p
```

Pide la contraseña de `root` definida en el paso 2.3. Al escribirla no se ve nada en
pantalla, ni asteriscos: es el comportamiento normal. El indicador cambia a `mysql>`.

### 3.2 Crear la base de datos y el usuario de la aplicación

Copiar y ejecutar, reemplazando la contraseña de ejemplo por una propia:

```sql
CREATE DATABASE inventra CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'inventra_app'@'localhost' IDENTIFIED BY 'la-contrasena-que-definas';
GRANT ALL PRIVILEGES ON inventra.* TO 'inventra_app'@'localhost';
FLUSH PRIVILEGES;
```

Qué hace cada línea:

- La primera crea la base de datos con codificación `utf8mb4`, que admite tildes, eñes y
  cualquier carácter del idioma.
- La segunda crea el usuario con el que se conecta la aplicación, válido solo desde el
  mismo equipo.
- La tercera le concede permisos únicamente sobre la base de datos `inventra`, no sobre
  todo el servidor.
- La cuarta recarga la tabla de privilegios para que los permisos queden activos.

La aplicación se conecta con `inventra_app`, nunca con `root`: si esas credenciales se
filtran, el daño queda limitado a esta base de datos.

### 3.3 Permisos para la base de datos de pruebas

Las pruebas automáticas se ejecutan sobre una base de datos temporal llamada
`test_inventra`, que el sistema crea y borra en cada corrida. El usuario de la
aplicación necesita permiso para crearla:

```sql
GRANT ALL PRIVILEGES ON test_inventra.* TO 'inventra_app'@'localhost';
GRANT ALL PRIVILEGES ON test_inventra.* TO 'inventra_app'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### 3.4 Comprobar y salir

```sql
SHOW DATABASES;
EXIT;
```

En el listado debe aparecer `inventra`. Después, verificar que el usuario de la aplicación
puede entrar:

```
mysql -u inventra_app -p inventra
```

Si entra sin error, la base de datos quedó lista. Salir con `EXIT;`.

## 4. Librerías del backend

| Librería | Versión | Para qué |
|---|---|---|
| Django | 5.2 LTS | Marco de trabajo del servidor |
| djangorestframework | 3.18 | Publicación de la API REST |
| mysqlclient | 2.2.8 | Conexión con MySQL |
| djangorestframework-simplejwt | última | Autenticación por token |
| django-cors-headers | última | Permite que el frontend consuma la API |
| python-dotenv | última | Lectura de las variables de entorno |

Se fija Django 5.2 LTS, con soporte hasta abril de 2028, por ser la versión estable de
mayor respaldo y estar declarada como compatible por Django REST Framework.

## 5. Entorno de desarrollo

El proyecto se trabaja en **Visual Studio Code**, con la terminal integrada del propio
editor. Todos los comandos de esta guía se ejecutan desde ahí.

### 5.1 Abrir el proyecto

1. Abrir Visual Studio Code.
2. Menú **Archivo → Abrir carpeta…** y seleccionar `Documents\Proyecto Sena`.
3. Si aparece el aviso «¿Confías en los autores de los archivos de esta carpeta?»,
   responder que sí.

### 5.2 Extensiones

Se instalan desde el icono de extensiones de la barra lateral (el de los cuadros) buscando
por nombre:

| Extensión | Para qué sirve |
|---|---|
| Python (Microsoft) | Ejecuta e interpreta el código de Python; incluye Pylance, que señala los errores mientras se escribe |
| Django (Baptiste Darthenay) | Reconoce la sintaxis de las plantillas de Django |
| SQLTools y SQLTools MySQL/MariaDB | Permite consultar la base de datos desde el editor |
| ESLint | Señala errores en el código del frontend |
| Prettier | Da formato uniforme al código del frontend |

### 5.3 Terminal integrada

Se abre con **Ver → Terminal** o con las teclas `Ctrl + Ñ`. Se ubica automáticamente en la
carpeta del proyecto.

La terminal por defecto en Windows es PowerShell. Antes de usar el entorno virtual de
Python hay que habilitar la ejecución de guiones, que Windows bloquea de fábrica. Se hace
una sola vez, en una terminal de PowerShell:

```
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Responder `S` o `A` cuando pida confirmación. Este permiso aplica solo al usuario actual y
solo a guiones firmados o creados localmente.

## 6. Preparación del backend

### 6.1 Estructura de carpetas

El código vive dentro de la carpeta `INVENTRA` del proyecto:

```
INVENTRA/
  backend/      código del servidor (Django)
  frontend/     código del cliente (React)
  scripts_bd/   estructura y carga inicial de la base de datos
```

Desde la terminal integrada:

```
cd INVENTRA
mkdir backend, frontend, scripts_bd
```

### 6.2 Entorno virtual

Un entorno virtual es una carpeta donde se instalan las librerías de este proyecto sin
mezclarlas con las del resto del equipo. Así, el proyecto siempre corre con las versiones
que se fijaron, y esa carpeta no se sube al repositorio.

```
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Cuando el entorno está activo, la línea de la terminal empieza con `(.venv)`. Para salir de
él se usa `deactivate`. **El entorno debe estar activo cada vez que se trabaje en el
backend**; si al abrir una terminal nueva no aparece `(.venv)`, se vuelve a ejecutar la
línea de activación.

### 6.3 Instalación de las librerías

Con el entorno activo:

```
py -m pip install --upgrade pip
pip install "Django==5.2.*" "djangorestframework==3.18.*" mysqlclient django-cors-headers djangorestframework-simplejwt python-dotenv
pip freeze > requirements.txt
```

El archivo `requirements.txt` deja registradas las versiones exactas instaladas. Con él,
cualquier persona reproduce el mismo entorno con `pip install -r requirements.txt`.

Comprobación:

```
py -m django --version
```

### 6.4 Creación del proyecto Django

```
django-admin startproject config .
```

El punto final indica que el proyecto se cree en la carpeta actual, sin agregar un nivel
más de carpetas. El resultado es:

```
backend/
  .venv/            entorno virtual (no se sube)
  config/           configuración del proyecto
    settings.py     parámetros: base de datos, aplicaciones, idioma
    urls.py         direcciones principales
  manage.py         utilidad de línea de comandos de Django
  requirements.txt  librerías y versiones
```

Se llama `config` para distinguir la configuración general de las aplicaciones de cada
módulo, que se crean después con nombres propios: `seguridad`, `inventario`, `ventas` y
las demás.

Comprobación:

```
py manage.py runserver
```

Debe responder que el servidor está corriendo en `http://127.0.0.1:8000/`. Al abrir esa
dirección en el navegador aparece la página de bienvenida de Django. Se detiene con
`Ctrl + C`.

En este punto el servidor todavía usa una base de datos temporal; la conexión con MySQL se
configura en el paso siguiente.

## 7. Variables de entorno

Las credenciales y los parámetros que cambian entre un equipo y otro no se escriben dentro
del código: se leen de un archivo `.env` ubicado en `INVENTRA/backend/`. Ese archivo no se
sube al repositorio, porque contiene contraseñas.

En su lugar se publica `.env.example`, con la lista de variables y sin valores. Para
preparar un equipo nuevo se copia y se completa:

```
copy .env.example .env
```

| Variable | Para qué sirve |
|---|---|
| `DJANGO_SECRET_KEY` | Clave criptográfica del proyecto; se genera una distinta por instalación |
| `DJANGO_DEBUG` | `True` en desarrollo, `False` en el servidor publicado |
| `DJANGO_ALLOWED_HOSTS` | Direcciones desde las que se permite servir la aplicación |
| `DB_NOMBRE`, `DB_USUARIO`, `DB_CONTRASENA`, `DB_HOST`, `DB_PUERTO` | Conexión con MySQL |
| `CORS_ORIGENES` | Dirección del frontend autorizada a consumir la API |
| `FRONTEND_URL` | Dirección base del frontend; el enlace de recuperación de contraseña apunta allí |
| `EMAIL_BACKEND` | Forma de envío del correo saliente: consola en desarrollo, SMTP en el servidor |
| `EMAIL_SERVIDOR`, `EMAIL_PUERTO`, `EMAIL_TLS`, `EMAIL_USUARIO`, `EMAIL_CONTRASENA` | Datos del proveedor de correo; solo se completan cuando se usa SMTP |
| `EMAIL_REMITENTE` | Dirección que aparece como remitente de los mensajes |

Todas las variables de correo tienen un valor por defecto pensado para desarrollo, así que
un equipo recién preparado funciona sin completarlas.

La clave de Django se genera con:

```
py -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

El resultado se copia como valor de `DJANGO_SECRET_KEY` en el archivo `.env`.

---

## 8. Correo saliente y recuperación de contraseña

El módulo de seguridad envía un correo cuando un usuario olvida su contraseña (RF-SEG-04).
Para trabajar en local no hace falta contratar ni configurar un servidor de correo.

### 8.1 En desarrollo: el correo se imprime en la terminal

Con el valor por defecto de `EMAIL_BACKEND`, Django no envía nada a internet: escribe el
mensaje completo en la terminal donde está corriendo `py manage.py runserver`. Al solicitar
la recuperación aparece algo así:

```
Content-Type: text/plain; charset="utf-8"
Subject: Restablecimiento de contraseña en INVENTRA
From: INVENTRA <no-responder@inventra.co>
To: usuario@licorera.com

Hola, Nombre del Usuario:

Recibimos una solicitud para restablecer la contraseña de tu cuenta en INVENTRA.

Para definir una contraseña nueva, abre el siguiente enlace:

http://localhost:5173/restablecer-contrasena?uid=Mg&token=cs1a2b-...

El enlace vence en 30 minutos y solo puede usarse una vez.
```

De ahí se copia el enlace para continuar la prueba. Esa salida sirve además como evidencia
en el informe de resultados de pruebas.

### 8.2 En el servidor publicado: envío real

Se cambian estos valores en el `.env` del servidor y se reinicia la aplicación:

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_SERVIDOR=smtp.proveedor.com
EMAIL_PUERTO=587
EMAIL_TLS=True
EMAIL_USUARIO=la-cuenta-del-proveedor
EMAIL_CONTRASENA=la-clave-del-proveedor
EMAIL_REMITENTE=INVENTRA <no-responder@tu-dominio.com>
FRONTEND_URL=https://la-direccion-publica-del-frontend
```

### 8.3 Vigencia del enlace

Los treinta minutos que exige la especificación se configuran en `config/settings.py`, en
`PASSWORD_RESET_TIMEOUT`. No hay ninguna tabla que almacene los enlaces: el token es un
valor firmado que se comprueba con los datos de la propia cuenta, de modo que vence solo y
deja de servir en cuanto la contraseña cambia.

---

## 9. Frontend (React)

La interfaz vive en `INVENTRA/frontend/` y se construye con React sobre Vite. Es una
aplicación independiente del backend: se levanta en su propio puerto y consume la API por
HTTP.

### 9.1 Instalación de las librerías

Con el proyecto abierto en Visual Studio Code, en una terminal situada en la carpeta del
frontend:

```
cd INVENTRA\frontend
npm install
```

El archivo `package.json` ya está en el repositorio con las versiones fijadas, así que
`npm install` reproduce exactamente el mismo conjunto de librerías en cualquier equipo. Se
crea la carpeta `node_modules`, que no se sube al repositorio porque se puede regenerar.

| Librería | Versión | Para qué sirve |
|---|---|---|
| react y react-dom | 19.3 | Construcción de la interfaz por componentes |
| react-router-dom | 7.18 | Traduce la dirección del navegador a una pantalla |
| vite | 8.3 | Servidor de desarrollo y empaquetado para publicar |
| @vitejs/plugin-react | 6.1 | Permite que Vite entienda la sintaxis de React |

No se usa ninguna librería de estilos ni de peticiones HTTP: los estilos son propios, con los
colores del manual de marca, y las peticiones se hacen con `fetch`, que ya viene en el
navegador.

### 9.2 Variables de entorno del frontend

```
copy .env.example .env
```

| Variable | Para qué sirve |
|---|---|
| `VITE_API_URL` | Dirección base de la API. En local, `http://127.0.0.1:8000/api` |

Vite solo expone al navegador las variables cuyo nombre empieza por `VITE_`; es una
protección para no publicar por descuido una credencial del servidor.

### 9.3 Puesta en marcha

Hacen falta **dos terminales abiertas al mismo tiempo**:

| Terminal | Carpeta | Comando | Resultado |
|---|---|---|---|
| 1 | `INVENTRA\backend` | `py manage.py runserver` | API en `http://127.0.0.1:8000` |
| 2 | `INVENTRA\frontend` | `npm run dev` | Interfaz en `http://localhost:5173` |

La primera con el entorno virtual activado.

**Importante: la interfaz se abre en `http://localhost:5173`, no en `http://127.0.0.1:5173`.**
Aunque las dos direcciones lleven al mismo sitio, el navegador las considera orígenes
distintos, y el backend solo autoriza la primera en `CORS_ORIGENES`. Si se entra por la
segunda, las peticiones se rechazan antes de salir del navegador.

### 9.4 Empaquetado para publicar

```
npm run build
```

Genera la carpeta `dist` con los archivos estáticos ya optimizados, que es lo que se sube al
servidor. `npm run preview` permite revisar ese resultado en local antes de publicarlo.

### 9.5 Estructura de la interfaz

```
INVENTRA/frontend/
  index.html                 página que carga la aplicación
  vite.config.js             configuración del servidor y del empaquetado
  src/
    main.jsx                 punto de entrada: monta React
    App.jsx                  mapa de rutas
    api/cliente.js           peticiones, token y errores, en un solo sitio
    api/seguridad.js         una función por dirección del módulo de seguridad
    sesion/                  estado de la sesión y guardia de rutas privadas
    componentes/             piezas reutilizables (campo de formulario, panel de marca)
    paginas/                 una pantalla por archivo
    estilos/                 colores del manual de marca y estilos de las pantallas
```

### 9.6 Una dirección que comparten el backend y el frontend

El enlace de recuperación de contraseña que envía el backend apunta a una pantalla concreta
del frontend:

```
{FRONTEND_URL}/restablecer-contrasena?uid=...&token=...
```

Esa dirección aparece en dos sitios y **tiene que coincidir en los dos**:

| Dónde | Archivo |
|---|---|
| Backend, al construir el enlace | `INVENTRA/backend/seguridad/correo.py` |
| Frontend, al declarar la ruta | `INVENTRA/frontend/src/App.jsx` |

Si se cambia en uno y no en el otro, los correos de recuperación llevan a una pantalla que no
existe. Conviene tenerlo presente al publicar, cuando `FRONTEND_URL` deja de ser
`http://localhost:5173` y pasa a ser el dominio real.

---

## 10. Cuentas del sistema

### 10.1 Los tres roles

INVENTRA distingue tres roles, cargados por una migración de datos al crear la base:

| Rol | ¿Pertenece a una licorera? | Alcance |
|---|---|---|
| Administrador de licorera | Sí | Administra su negocio: usuarios, inventario, ventas y reportes |
| Vendedor | Sí | Opera el punto de venta y consulta; no gestiona cuentas |
| Administrador de INVENTRA | **No** | Personal de la plataforma: administra licoreras y planes |

La diferencia importante es la segunda columna. Los permisos del sistema no preguntan solo
por el rol, también por la licorera: quien no pertenece a ninguna no puede administrar los
usuarios de ninguna, y eso incluye al administrador de la plataforma.

### 10.2 Crear el administrador de INVENTRA

Se crea desde la consola, porque es la primera cuenta del sistema y no hay quien la dé de
alta. Desde `INVENTRA\backend`, con el entorno virtual activado:

```
py manage.py createsuperuser
```

Pide el correo, el nombre y la contraseña dos veces. La contraseña cumple la misma política
que las demás: mínimo ocho caracteres, combinando letras y números.

La cuenta queda con el rol de administrador de INVENTRA y **sin licorera asociada**, que es
lo correcto: administra la plataforma, no un negocio.

> **Nota.** En un proyecto Django corriente este comando sirve para entrar al panel de
> administración incorporado. INVENTRA no lo tiene: se retiró a propósito, porque la interfaz
> es React y un segundo punto de entrada con su propia autenticación habría que proteger y
> auditar aparte. Así que este comando no abre ninguna puerta oculta; solo crea la cuenta del
> operador de la plataforma.

### 10.3 Registrar una licorera

Desde la pantalla de registro de la aplicación. En una sola operación se crea la licorera, su
suscripción al plan Básico y su usuario administrador, que entra directamente al panel.

### 10.4 Preparar datos para probar

Algunas reglas dependen de datos que todavía no se pueden producir desde la interfaz, porque
su pantalla pertenece a un módulo posterior. En esos casos los datos se preparan desde la
consola de Django. No es un atajo indebido: es la forma habitual de dejar el sistema en el
estado que una prueba necesita.

**Ver las suscripciones existentes:**

```
py manage.py shell -c "from suscripciones.models import Suscripcion; [print(s.id, '|', s.licorera.nombre, '|', s.licorera.correo, '|', s.plan.nombre, '|', s.estado) for s in Suscripcion.objects.select_related('licorera','plan')]"
```

**Pasar una licorera al plan Pro** (para comprobar el tope de usuarios), usando el
identificador de la suscripción que devolvió el comando anterior:

```
py manage.py shell -c "from suscripciones.models import Suscripcion, Plan; s=Suscripcion.objects.get(id=1); s.plan=Plan.objects.get(nombre__startswith='Pro'); s.save(); print(s.licorera.nombre, '->', s.plan.nombre, '| maximo_usuarios:', s.plan.maximo_usuarios)"
```

**Devolverla al plan Básico:**

```
py manage.py shell -c "from suscripciones.models import Suscripcion, Plan; s=Suscripcion.objects.get(id=1); s.plan=Plan.objects.get(nombre__startswith='B'); s.save(); print(s.licorera.nombre, '->', s.plan.nombre, '| maximo_usuarios:', s.plan.maximo_usuarios)"
```

> Los nombres de plan se buscan por `startswith` y no por su texto completo para evitar la
> tilde de «Básico», que según la configuración de la consola de Windows puede llegar mal al
> intérprete.

> **Advertencia sobre este atajo.** Cambiar el plan de una suscripción existente deja el
> `precio_pactado` congelado del plan anterior, que es una incoherencia aceptable en datos de
> prueba pero no en producción. El cambio de plan real (RF-SUS-02) no modifica la fila: cierra
> la suscripción vigente y crea una nueva con el plan y el precio del momento, de modo que el
> histórico de facturación quede correcto.

