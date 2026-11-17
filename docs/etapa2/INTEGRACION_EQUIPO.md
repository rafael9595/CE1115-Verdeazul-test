# Integración del equipo

## Responsabilidades después de esta entrega

| Persona | Parte | Estado y siguiente conexión |
|---|---|---|
| 1 | Identidad y autorización central | Sustituir/completar el acceso local con la política completa de cuentas, MFA, sesiones revocables, administración de roles y sus pruebas. Conservar la identidad laboral independiente de la cuenta |
| 2 | Fincas, mediciones e interfaz de captura | Conectar catálogo, titularidad, asignaciones y captura a los modelos compartidos; implementar sincronización y cola cifrada. Reutilizar servicios de edición/envío y la consulta del panel |
| 3 | Gestión y reportes | Implementado en esta entrega: revisión, períodos, enmiendas, invalidación, persistencia de certificados, precios y reportes. Integrar las entidades de entrada y las políticas definitivas de 1/2 |
| Olman (4) | Firma y verificación | Conservado e integrado. Mantener el contrato firmado y presentar la verificación, alteración y diferencia entre firma/vigencia |
| 5 | Infraestructura, auditoría y monitoreo | Publicar backend y PostgreSQL Neon, configurar Secret Manager, HTTPS, privilegios de BD, copia independiente de auditoría, alertas H1/H2, repositorio/Dependabot y evidencia |

La persona 5 coordina el ensamblaje y despliegue. La interfaz de captura principal es responsabilidad de la persona 2; cada módulo aporta sus pantallas. La base de datos es compartida: aquí quedan las tablas necesarias para gestión y firma, que deben coordinarse con las entidades de 1/2. No se necesitan cinco aplicaciones separadas.

## Conexión que ya existe

`POST aprobación` → sesión/CSRF → `gestion.services.execute` → permiso e historial → bloqueos PostgreSQL → decisión de revisión → `certificados.issue_certificate` → bytes firmados en `Certificate` → bitácora → confirmación de transacción.

La aprobación tiene una única transacción para decisión, estado, certificado, evento e idempotencia. La firma usa la instantánea obtenida desde la base de datos; no firma un payload arbitrario enviado por el navegador. Si falla la firma o el evento, se revierten esos cambios.

Los botones y la API llaman al mismo servicio. La API no permite que el cliente indique su rol, su persona o una hora de reautenticación. El actor se obtiene de la sesión y `authenticated_at` se obtiene del estado de sesión del servidor.

## Entidades compartidas

`Person` representa a la persona laboral; `Account` representa una cuenta de acceso. Una persona puede tener varias cuentas, pero aquí tiene un rol primario; todas comparten el historial de autoría. Los UUID de negocio se crean en servidor.

`Owner`/`OwnerLink`, `Farm`/`FarmAssignment`, `Measurement`/`ReviewAssignment` y `AuditorGrant` son el contrato inicial para los módulos 1/2. `Measurement.technician` identifica al técnico original, mientras `Version` conserva cada versión y autor. No crear tablas duplicadas con otra identidad para la misma persona o finca.

Si ya existe un proyecto Django del equipo, comparar los modelos antes de aplicar las migraciones. `AUTH_USER_MODEL=gestion.Account` se configura al iniciar una base nueva. Cambiar el modelo de usuarios de una base existente requiere una migración planificada; no copiar `0001_initial.py` sobre un esquema incompatible.

## Rutas

| Ruta | Método y finalidad |
|---|---|
| `/login/`, `/logout/`, `/reauth/` | Formularios de sesión; mutaciones por POST con CSRF |
| `/api/workspace/` | GET: proyección de panel según actor |
| `/api/action/<action>/<target>/` | POST JSON: operación transaccional; encabezado `Idempotency-Key` UUID y CSRF |
| `/action/<action>/<target>/` | POST de formulario: `request_id` UUID y CSRF |
| `/api/reports/<measurement_uuid>/` | GET: reporte filtrado; `?download=1` registra descarga |
| `/api/certificates/<certificate_uuid>/download/` | GET: bytes originales y autorización O8 |
| `/api/prices/<certificate_uuid>/` | GET: precio solo para roles/propietario autorizados |
| `/api/audit/` | GET: bitácora filtrada, hasta 1000 eventos recientes antes del filtro; no es exportación exhaustiva |
| `/verify/` | GET/POST: verifica un archivo que el usuario ya posee; no recupera datos privados de la BD |
| `/health/` | GET: disponibilidad del proceso; no acredita salud de BD o firma |

| Acción | Target | Datos JSON |
|---|---|---|
| `approve` | versión | `{}` |
| `return` | versión | `{"reason":"..."}` |
| `request_amendment` | versión aprobada/devuelta | `{"reason":"..."}` |
| `authorize_amendment` | enmienda | `{"reason":"...","technician_id":"UUID del técnico original"}` |
| `correct` | versión origen | `{}` o `{"amendment_id":"UUID"}` |
| `edit` | borrador | `{"measured_at":"AAAA-MM-DD","methodology":"...","values":[{"name":"carbono_reportado","value":"120.00","unit":"tCO2e"}]}` |
| `submit` | borrador | `{}` |
| `invalidate` | certificado | `{"reason":"..."}` |
| `set_price` | certificado | `{"amount":"25000.00","currency":"CRC"}` |
| `open_period` | `new` | `{"name":"Período nuevo"}` |
| `close_period` | período | `{"reason":"..."}` |

Un UUID de operación solo se reutiliza para el mismo actor, acción, target y contenido. El reintento revalida permisos actuales. Una operación nueva necesita un UUID nuevo. Ningún rol humano tiene permiso para llamar directamente al firmador mediante una ruta pública.

## Integración de la persona 1

Conservar el control en servidor y la identidad histórica. Evitar sustituir `policy.py` por comprobaciones de botones. Los cambios de rol incrementan `Person.auth_version` mediante trigger y revocan sesiones existentes al siguiente acceso. Completar MFA, administración de cuentas, revocación explícita, recuperación, política de acceso y todas las celdas de O1/O15. El limitado login de demostración no las reemplaza.

## Integración de la persona 2

Crear fincas/asignaciones y versiones con los campos acordados. Toda transición posterior pasa por los servicios. Una versión enviada no se edita; una devolución genera una nueva versión de corrección para preservar el historial. La asignación de autor y técnico original debe venir de la sesión validada, nunca del JSON del cliente.

La captura offline, el cifrado local, la sincronización y la resolución de conflictos siguen pendientes. La pantalla JSON de corrección demuestra el flujo y puede sustituirse por un formulario de mediciones sin cambiar el contrato del servicio.

## Integración de la persona 5

Usar `Dockerfile` como base del backend; `compose.yaml` es exclusivamente local. Producción debe usar `DJANGO_LOCAL=0`, hosts y orígenes concretos, `DATABASE_URL` con `sslmode=verify-full`, secreto Django aleatorio y clave de firma externa. El comando normal de la imagen no aplica migraciones ni crea cuentas demo: ejecutar las migraciones como tarea de despliegue controlada antes de servir tráfico.

La clave se configura mediante **una sola** fuente: `VERDEAZUL_SIGNING_PRIVATE_KEY_FILE` o `VERDEAZUL_SIGNING_PRIVATE_KEY_PEM`. `VERDEAZUL_TRUSTED_PUBLIC_KEYS` contiene rutas de claves públicas confiables separadas por el separador de rutas del sistema (`:` en Linux). Secret Manager debe montarlas/injectarlas con permisos mínimos. Conservar claves públicas históricas para rotación.

Separar el rol de migración del rol de ejecución. El usuario de PostgreSQL de Compose es propietario/superusuario para la demo: no representa privilegios de producción. El rol de la aplicación no debe poder modificar triggers, ejecutar DDL/TRUNCATE o eliminar evidencia. Coordinar las políticas RLS de Parte 1 con la identidad de sesión de la persona 1 y probarlas con el rol de ejecución, no con superusuario.

Los eventos de `services.event` y `queries` ya aportan actor, cuenta, rol, acción, fecha, objeto, regla y resultado. Completar el contrato para todos los módulos y una copia independiente protegida de auditoría. Añadir H1/H2 y probar consultas masivas y calendario laboral. La configuración de Dependabot y CI existe en `.github/`; su presencia en un ZIP no significa que GitHub ya la ejecutó.
