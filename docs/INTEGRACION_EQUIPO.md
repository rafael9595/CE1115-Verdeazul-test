# Integración del equipo

## Responsabilidades después de esta entrega

| Persona | Parte | Estado y siguiente conexión |
|---|---|---|
| 1 | Identidad y autorización central | Implementado en 4.0.0: cuentas, roles, MFA, recuperación, O1/O15, sesiones y política de acceso. Mantiene identidad laboral histórica |
| 2 | Fincas, mediciones e interfaz de captura | Implementado en 3.0.0: catálogo, propietarios, vínculos, asignaciones, formularios de medición, cola cifrada y sincronización. Completar la validación específica en Windows y Safari/iOS |
| 3 | Gestión y reportes | Implementado en esta entrega: revisión, períodos, enmiendas, invalidación, persistencia de certificados, precios y reportes. Ya conectado con las entidades de entrada de 2; ya conectado con la identidad y sesiones de 1 |
| Olman (4) | Firma y verificación | Conservado e integrado. Mantener el contrato firmado y presentar la verificación, alteración y diferencia entre firma/vigencia |
| 5 | Infraestructura, auditoría y monitoreo | Publicar backend y PostgreSQL Neon, configurar Secret Manager, HTTPS, privilegios de BD, copia independiente de auditoría, alertas H1/H2, repositorio/Dependabot y evidencia |

La persona 5 coordina el ensamblaje y despliegue. La interfaz de captura principal es responsabilidad de la persona 2; cada módulo aporta sus pantallas. La base de datos es compartida: aquí quedan las tablas necesarias para gestión y firma, que deben coordinarse con las entidades de 1/2. No se necesitan cinco aplicaciones separadas.

## Conexión que ya existe

`POST aprobación` → sesión/CSRF → `gestion.services.execute` → permiso e historial → bloqueos PostgreSQL → decisión de revisión → `certificados.issue_certificate` → bytes firmados en `Certificate` → bitácora → confirmación de transacción.

La aprobación tiene una única transacción para decisión, estado, certificado, evento e idempotencia. La firma usa la instantánea obtenida desde la base de datos; no firma un payload arbitrario enviado por el navegador. Si falla la firma o el evento, se revierten esos cambios.

Los botones y la API llaman al mismo servicio. La API no permite que el cliente indique su rol, su persona o una hora de reautenticación. El actor se obtiene de la sesión y `authenticated_at` se obtiene del estado de sesión del servidor.

## Entidades compartidas

`Person` representa a la persona laboral; `Account` representa una cuenta de acceso. Una persona puede tener varias cuentas, con un rol principal y roles adicionales compartidos; todas comparten el historial de autoría. Los UUID de negocio se crean en servidor.

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
| `edit` | borrador | `{"expected_revision":1,"measured_at":"AAAA-MM-DD","methodology":"...","values":[{"name":"carbono_reportado","value":"120.00","unit":"tCO2e"}]}` |
| `submit` | borrador | `{"expected_revision":1}` |
| `invalidate` | certificado | `{"reason":"..."}` |
| `set_price` | certificado | `{"amount":"25000.00","currency":"CRC"}` |
| `open_period` | `new` | `{"name":"Período nuevo"}` |
| `close_period` | período | `{"reason":"..."}` |

Un UUID de operación solo se reutiliza para el mismo actor, acción, target y contenido. El reintento revalida permisos actuales. Una operación nueva necesita un UUID nuevo. Ningún rol humano tiene permiso para llamar directamente al firmador mediante una ruta pública.

## Integración de la persona 1

Implementada en 4.0.0. `identity.py`, `identity_views.py` y el middleware validan cuenta, persona, función activa, MFA, versiones y sesión. Cambiar roles revoca todas las sesiones de la persona; la baja finaliza asignaciones vigentes. Se conserva la identidad histórica y los servicios siguen rechazando autoaprobación. Las rutas y decisiones O1/O15 están en `PERSONA1_IDENTIDAD.md`.

La persona 5 debe montar `VERDEAZUL_IDENTITY_KEY_FILE` con una clave persistente independiente de la firma. El QR se genera localmente; no hace falta un servicio externo de QR. Pwned Passwords sí requiere salida HTTPS para verificar contraseñas nuevas. No se implementó envío de correo.

## Integración de la persona 2

Crear fincas/asignaciones y versiones con los campos acordados. Toda transición posterior pasa por los servicios. Una versión enviada no se edita; una devolución genera una nueva versión de corrección para preservar el historial. La asignación de autor y técnico original debe venir de la sesión validada, nunca del JSON del cliente.

La captura offline, el cifrado local, la sincronización y la comparación manual de conflictos están implementados en `assets/` y `gestion/capture.py`. Las correcciones ya utilizan un formulario de valores. Las operaciones `edit` y `submit` requieren `expected_revision`, obtenido de la consulta autorizada; una pantalla obsoleta recibe 409. Las pruebas de navegador por plataforma permanecen pendientes.

## Integración de la persona 5

Usar `Dockerfile` como base del backend; `compose.yaml` es exclusivamente local. Producción debe usar `DJANGO_LOCAL=0`, hosts y orígenes concretos, `DATABASE_URL` con `sslmode=verify-full`, secreto Django aleatorio y clave de firma externa. El comando normal de la imagen no aplica migraciones ni crea cuentas demo: ejecutar las migraciones como tarea de despliegue controlada antes de servir tráfico.

La clave se configura mediante **una sola** fuente: `VERDEAZUL_SIGNING_PRIVATE_KEY_FILE` o `VERDEAZUL_SIGNING_PRIVATE_KEY_PEM`. `VERDEAZUL_TRUSTED_PUBLIC_KEYS` contiene rutas de claves públicas confiables separadas por el separador de rutas del sistema (`:` en Linux). Secret Manager debe montarlas/injectarlas con permisos mínimos. Conservar claves públicas históricas para rotación.

Separar el rol de migración del rol de ejecución. El usuario de PostgreSQL de Compose es propietario/superusuario para la demo: no representa privilegios de producción. El rol de la aplicación no debe poder modificar triggers, ejecutar DDL/TRUNCATE o eliminar evidencia. Coordinar las políticas RLS de Parte 1 con la identidad de sesión de la persona 1 y probarlas con el rol de ejecución, no con superusuario.

Los eventos de `services.event` y `queries` ya aportan actor, cuenta, rol, acción, fecha, objeto, regla y resultado. Completar el contrato para todos los módulos y una copia independiente protegida de auditoría. Añadir H1/H2 y probar consultas masivas y calendario laboral. La configuración de Dependabot y CI existe en `.github/`; su presencia en un ZIP no significa que GitHub ya la ejecutó.

## Contrato añadido por la persona 2

`/api/capture/action/<acción>/<target>/` recibe POST JSON con sesión, CSRF e `Idempotency-Key`. Las mutaciones de catálogo y las sincronizaciones comparten la identidad de operación por persona con el módulo de gestión; reutilizar un UUID para otra operación se rechaza.

| Acción | Target y contenido |
|---|---|
| `create_owner` | `new`; nombre legal y contacto |
| `edit_owner` | UUID de propietario; contacto, revisión esperada y nombre solo para administrador |
| `link_owner` | UUID de propietario; `person_id` y `verification_reference`, solo administrador |
| `revoke_owner_link` | UUID de vínculo; motivo |
| `create_farm`, `edit_farm` | `new` o UUID de finca; registro, nombre, propietario, área, polígono; edición añade revisión esperada y motivo |
| `assign_tech` | UUID de finca; persona técnica y motivo |
| `assign_reviewer` | UUID de medición; persona verificadora independiente y motivo |
| `revoke_tech`, `revoke_reviewer` | UUID de asignación; motivo; conserva identidad e historial |
| `create_measurement` | `new`; finca, período, fecha, metodología y valores; autor siempre de la sesión |
| `sync` | `new`; campos de medición más autor declarado, versión destino o null, revisión base y fecha de captura con zona horaria |
| `queue_status` | `new`; UUID de dispositivo y conteos declarados `pending`/`conflicts`; nunca contenido de la cola |

`/api/capture/bootstrap/` devuelve solo datos técnicos propios autorizados y un token CSRF para la sesión actual. El JavaScript mantiene ese token en memoria; no lo incluye en el almacén cifrado ni en Cache Storage. `/api/capture/farms/`, `/owners/`, `/assignments/` y `/queues/` dentro del mismo prefijo aplican sus proyecciones de lectura.

Una sincronización válida guarda un BORRADOR y devuelve UUID de versión, revisión resultante, UUID de constancia y hora de recepción. No envía a revisión ni aprueba automáticamente. En edición se compara la revisión dentro del bloqueo transaccional. Un reintento confirmado devuelve la misma constancia después de revalidar cuenta, identidad y asignación, incluso si el período cerró después de su recepción original; no realiza una escritura nueva.

El propietario dispone además de `/measurements/<UUID>/download/`, filtrado a sus mediciones, sin precios ni documentos de otras personas. El reporte O11 conserva su proyección independiente.

## Protección local

El Service Worker tiene alcance `/campo/` y una lista cerrada de cuatro recursos públicos. IndexedDB guarda perfiles cifrados mediante AES-256-GCM, IV aleatorio de 96 bits, etiqueta de 128 bits y clave no exportable derivada de una frase mediante PBKDF2-HMAC-SHA-256 (600000 iteraciones y sal aleatoria de 128 bits). La frase se comprueba localmente y no se transmite ni persiste. La identidad y revisión del almacén se autentican como datos adicionales.

La escritura usa una transacción IndexedDB y compara su revisión para evitar sobrescrituras entre pestañas. Se solicita durabilidad estricta donde el navegador la admite. Un código malicioso ejecutándose en el mismo origen desbloqueado podría acceder a los datos; el cifrado local no protege frente a un navegador comprometido ni evita rollback de una copia cifrada antigua completa. El servidor sigue revalidando y evita duplicados por UUID.

Fuentes técnicas consultadas:

- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey
- https://developer.mozilla.org/en-US/docs/Web/API/AesGcmParams
- https://developer.mozilla.org/en-US/docs/Web/API/IDBTransaction
- https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

El costo PBKDF2 elegido es un parámetro de implementación; debe medirse en los dispositivos objetivo. La contraseña de acceso del servidor continúa usando Argon2, independientemente de la frase local.
