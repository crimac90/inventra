-- ============================================================
--  INVENTRA — Inventario y ventas para licoreras
--  Estructura de la base de datos (DDL)
-- ============================================================
--  Generado el 2026-09-21 con py manage.py generar_scripts_sql
--  Django 5.2.17 · motor mysql · base «inventra»
-- ============================================================

-- Generado a partir de las migraciones de Django. No se edita a mano:
-- se cambia el modelo, se crea la migración y se vuelve a generar.


-- ----------------------------------------------------------
-- contenttypes.0001_initial
-- ----------------------------------------------------------
--
-- Create model ContentType
--
CREATE TABLE `django_content_type` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(100) NOT NULL, `app_label` varchar(100) NOT NULL, `model` varchar(100) NOT NULL);
--
-- Alter unique_together for contenttype (1 constraint(s))
--
ALTER TABLE `django_content_type` ADD CONSTRAINT `django_content_type_app_label_model_76bd3d3b_uniq` UNIQUE (`app_label`, `model`);


-- ----------------------------------------------------------
-- contenttypes.0002_remove_content_type_name
-- ----------------------------------------------------------
--
-- Change Meta options on contenttype
--
-- (no-op)
--
-- Alter field name on contenttype
--
ALTER TABLE `django_content_type` MODIFY `name` varchar(100) NULL;
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL
--
-- Remove field name from contenttype
--
ALTER TABLE `django_content_type` DROP COLUMN `name`;


-- ----------------------------------------------------------
-- auth.0001_initial
-- ----------------------------------------------------------
--
-- Create model Permission
--
CREATE TABLE `auth_permission` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(50) NOT NULL, `content_type_id` integer NOT NULL, `codename` varchar(100) NOT NULL);
--
-- Create model Group
--
CREATE TABLE `auth_group` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(80) NOT NULL UNIQUE);
CREATE TABLE `auth_group_permissions` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `group_id` integer NOT NULL, `permission_id` integer NOT NULL);
--
-- Create model User
--
-- (no-op)
ALTER TABLE `auth_permission` ADD CONSTRAINT `auth_permission_content_type_id_codename_01ab375a_uniq` UNIQUE (`content_type_id`, `codename`);
ALTER TABLE `auth_permission` ADD CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` UNIQUE (`group_id`, `permission_id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`);
ALTER TABLE `auth_group_permissions` ADD CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`);


-- ----------------------------------------------------------
-- auth.0002_alter_permission_name_max_length
-- ----------------------------------------------------------
--
-- Alter field name on permission
--
ALTER TABLE `auth_permission` MODIFY `name` varchar(255) NOT NULL;

-- auth.0003_alter_user_email_max_length: migración de datos, sin estructura

-- auth.0004_alter_user_username_opts: migración de datos, sin estructura

-- auth.0005_alter_user_last_login_null: migración de datos, sin estructura

-- auth.0006_require_contenttypes_0002: migración de datos, sin estructura

-- auth.0007_alter_validators_add_error_messages: migración de datos, sin estructura

-- auth.0008_alter_user_username_max_length: migración de datos, sin estructura

-- auth.0009_alter_user_last_name_max_length: migración de datos, sin estructura


-- ----------------------------------------------------------
-- auth.0010_alter_group_name_max_length
-- ----------------------------------------------------------
--
-- Alter field name on group
--
ALTER TABLE `auth_group` MODIFY `name` varchar(150) NOT NULL;

-- auth.0011_update_proxy_permissions: migración de datos, sin estructura

-- auth.0012_alter_user_first_name_max_length: migración de datos, sin estructura


-- ----------------------------------------------------------
-- suscripciones.0001_initial
-- ----------------------------------------------------------
--
-- Create model Licorera
--
CREATE TABLE `licorera` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(100) NOT NULL, `nit` varchar(20) NULL UNIQUE, `direccion` varchar(150) NULL, `telefono` varchar(20) NULL, `correo` varchar(100) NOT NULL, `fecha_registro` datetime(6) NOT NULL, `activo` bool NOT NULL);
--
-- Create model Plan
--
CREATE TABLE `plan` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(30) NOT NULL UNIQUE, `precio_mensual` numeric(12, 2) NOT NULL, `maximo_sedes` integer UNSIGNED NULL CHECK (`maximo_sedes` >= 0), `maximo_usuarios` integer UNSIGNED NULL CHECK (`maximo_usuarios` >= 0), `permite_facturacion` bool NOT NULL, `permite_reportes_avanzados` bool NOT NULL, `activo` bool NOT NULL);
--
-- Create model Suscripcion
--
CREATE TABLE `suscripcion` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `estado` varchar(12) NOT NULL, `fecha_inicio` date NOT NULL, `fecha_fin` date NULL, `precio_pactado` numeric(12, 2) NOT NULL, `licorera_id` bigint NOT NULL, `plan_id` bigint NOT NULL);
ALTER TABLE `suscripcion` ADD CONSTRAINT `suscripcion_licorera_id_e266ca4f_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `suscripcion` ADD CONSTRAINT `suscripcion_plan_id_1321714a_fk_plan_id` FOREIGN KEY (`plan_id`) REFERENCES `plan` (`id`);


-- ----------------------------------------------------------
-- seguridad.0001_initial
-- ----------------------------------------------------------
--
-- Create model Rol
--
CREATE TABLE `rol` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre` varchar(30) NOT NULL UNIQUE, `descripcion` varchar(150) NOT NULL);
--
-- Create model Usuario
--
CREATE TABLE `usuario` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nombre_completo` varchar(100) NOT NULL, `correo` varchar(100) NOT NULL UNIQUE, `telefono` varchar(20) NULL, `contrasena_hash` varchar(255) NOT NULL, `intentos_fallidos` smallint UNSIGNED NOT NULL CHECK (`intentos_fallidos` >= 0), `bloqueado_hasta` datetime(6) NULL, `activo` bool NOT NULL, `fecha_creacion` datetime(6) NOT NULL, `ultimo_acceso` datetime(6) NULL, `licorera_id` bigint NULL, `rol_id` bigint NOT NULL);
ALTER TABLE `usuario` ADD CONSTRAINT `usuario_licorera_id_01ee3245_fk_licorera_id` FOREIGN KEY (`licorera_id`) REFERENCES `licorera` (`id`);
ALTER TABLE `usuario` ADD CONSTRAINT `usuario_rol_id_ac58b608_fk_rol_id` FOREIGN KEY (`rol_id`) REFERENCES `rol` (`id`);

-- seguridad.0002_datos_roles: migración de datos, sin estructura

-- suscripciones.0002_datos_planes: migración de datos, sin estructura


-- ----------------------------------------------------------
-- token_blacklist.0001_initial
-- ----------------------------------------------------------
--
-- Create model BlacklistedToken
--
CREATE TABLE `token_blacklist_blacklistedtoken` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `blacklisted_at` datetime(6) NOT NULL);
--
-- Create model OutstandingToken
--
CREATE TABLE `token_blacklist_outstandingtoken` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `jti` char(32) NOT NULL UNIQUE, `token` longtext NOT NULL, `created_at` datetime(6) NOT NULL, `expires_at` datetime(6) NOT NULL, `user_id` bigint NOT NULL);
--
-- Add field token to blacklistedtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` ADD COLUMN `token_id` integer NOT NULL UNIQUE , ADD CONSTRAINT `token_blacklist_blac_token_id_3cc7fe56_fk_token_bla` FOREIGN KEY (`token_id`) REFERENCES `token_blacklist_outstandingtoken`(`id`);
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id` FOREIGN KEY (`user_id`) REFERENCES `usuario` (`id`);


-- ----------------------------------------------------------
-- token_blacklist.0002_outstandingtoken_jti_hex
-- ----------------------------------------------------------
--
-- Add field jti_hex to outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` ADD COLUMN `jti_hex` varchar(255) NULL;

-- token_blacklist.0003_auto_20171017_2007: migración de datos, sin estructura


-- ----------------------------------------------------------
-- token_blacklist.0004_auto_20171017_2013
-- ----------------------------------------------------------
--
-- Alter field jti_hex on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `jti_hex` varchar(255) NOT NULL;
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq` UNIQUE (`jti_hex`);


-- ----------------------------------------------------------
-- token_blacklist.0005_remove_outstandingtoken_jti
-- ----------------------------------------------------------
--
-- Remove field jti from outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` DROP COLUMN `jti`;


-- ----------------------------------------------------------
-- token_blacklist.0006_auto_20171017_2113
-- ----------------------------------------------------------
--
-- Rename field jti_hex on outstandingtoken to jti
--
ALTER TABLE `token_blacklist_outstandingtoken` RENAME COLUMN `jti_hex` TO `jti`;


-- ----------------------------------------------------------
-- token_blacklist.0007_auto_20171017_2214
-- ----------------------------------------------------------
--
-- Alter field created_at on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `created_at` datetime(6) NULL;
--
-- Alter field user on outstandingtoken
--
ALTER TABLE `token_blacklist_outstandingtoken` DROP FOREIGN KEY `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id`;
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `user_id` bigint NULL;
ALTER TABLE `token_blacklist_outstandingtoken` ADD CONSTRAINT `token_blacklist_outstandingtoken_user_id_83bc629a_fk_usuario_id` FOREIGN KEY (`user_id`) REFERENCES `usuario` (`id`);


-- ----------------------------------------------------------
-- token_blacklist.0008_migrate_to_bigautofield
-- ----------------------------------------------------------
--
-- Alter field id on blacklistedtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` MODIFY `id` bigint AUTO_INCREMENT NOT NULL;
--
-- Alter field id on outstandingtoken
--
ALTER TABLE `token_blacklist_blacklistedtoken` DROP FOREIGN KEY `token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk`;
ALTER TABLE `token_blacklist_outstandingtoken` MODIFY `id` bigint AUTO_INCREMENT NOT NULL;
ALTER TABLE `token_blacklist_blacklistedtoken` MODIFY `token_id` bigint NOT NULL;
ALTER TABLE `token_blacklist_blacklistedtoken` ADD CONSTRAINT `token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk` FOREIGN KEY (`token_id`) REFERENCES `token_blacklist_outstandingtoken` (`id`);

-- token_blacklist.0010_fix_migrate_to_bigautofield: migración de datos, sin estructura

-- token_blacklist.0011_linearizes_history: migración de datos, sin estructura

-- token_blacklist.0012_alter_outstandingtoken_user: migración de datos, sin estructura

-- token_blacklist.0013_alter_blacklistedtoken_options_and_more: migración de datos, sin estructura

