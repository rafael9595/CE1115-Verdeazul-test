# Aporte de identidad, captura, gestión y certificados

Se implementó un backend Django conectado a PostgreSQL para gestionar revisiones, períodos, enmiendas, certificados y reportes. La aprobación consulta la identidad y asignación vigentes del verificador, comprueba que no haya participado como autor o corrector en la cadena de versiones y exige una versión enviada sin decisión previa.

Tras validar estas condiciones, el backend construye una instantánea desde la base de datos y llama al módulo de certificados desarrollado previamente. Ese módulo genera una firma Ed25519 sobre el contenido determinista e incluye la clave pública y su huella. La decisión, el cambio de estado, los bytes firmados y el evento de emisión se guardan dentro de una misma transacción. Un fallo de firma o de escritura del evento revierte la aprobación y evita conservar registros parciales.

PostgreSQL impone un máximo de un certificado vigente por finca mediante una restricción única condicional. La aplicación bloquea los registros afectados y utiliza una identidad de operación para reconocer reintentos. Se comprobaron solicitudes concurrentes de dos verificadores y reintentos concurrentes de una misma petición: en ambos casos se conservó un único certificado.

Las correcciones preservan la versión anterior y crean una nueva. Una versión aprobada, o una corrección dentro de un período cerrado, necesita una enmienda autorizada por un administrador recientemente autenticado y vinculada al técnico original. La autorización permite corregir esa versión específica sin reabrir el período ni sustituir la revisión independiente. La invalidación conserva el documento firmado y registra motivo, actor y fecha; un reemplazo relaciona ambos certificados.

Los reportes se filtran según rol y alcance. El propietario consulta su información; el auditor accede únicamente al encargo vigente y recibe una proyección sin datos personales del propietario ni precios. La descarga directa del certificado aplica su propia autorización. Los eventos y decisiones se protegen con triggers que rechazan modificaciones o eliminaciones ordinarias.

## Resultados ejecutados

| Comprobación | Resultado observado |
|---|---|
| Suite del módulo de firma | 31 pruebas correctas |
| Suite de gestión y captura en PostgreSQL 17.11 | 161 pruebas correctas |
| Cifrado y transiciones de cola en Node/Web Crypto | 12 pruebas correctas |
| Migración de la versión 3.0.0 a 4.0.0 | Certificado, cuentas, versiones y eventos conservados |
| Consistencia de migraciones y comprobación Django | Sin cambios pendientes ni problemas detectados |
| HTTP con Gunicorn, cookies y CSRF | Técnico rechazado; aprobación/descarga/verificación correctas; reintento conservó el certificado; alteración rechazada |
| Formularios HTTP de devolución y corrección | Versión 1 devuelta preservada; versión 2 editada, enviada y aprobada por verificador |

Los registros se incluyen en `evidencia/pruebas_criptografia.txt`, `evidencia/pruebas_integracion.txt` y `evidencia/prueba_http.txt`. Los archivos de `ejemplos_integracion/` provienen de la prueba HTTP con datos sintéticos. Contienen solo documentos y clave pública, no la privada.

Se utilizaron Python 3.12.14, Django 5.2.19, PostgreSQL 17.11, cryptography 50.0.0, psycopg 3.3.8, Argon2 y Shapely. La comprobación cartográfica utiliza Natural Earth, con las limitaciones de precisión descritas en `gestion/data/README.md`.

## Alcance del resultado

Se verificó la integración local de los módulos de gestión y firma. La inspección visual en Chromium no pudo ejecutarse por restricciones del entorno; las plantillas y sus formularios se verificaron mediante Django y HTTP. No se presentan evidencias de Docker Desktop, Windows, publicación en nube o CI porque esas ejecuciones no se realizaron. La identidad está integrada. RLS, infraestructura, alertas y auditoría independiente requieren el módulo de persona 5. La captura/sincronización está implementada; su recorrido completo en los navegadores objetivo requiere comprobación adicional. El detalle está en `COBERTURA_Y_LIMITES.md`.

Este texto es el aporte técnico de los módulos integrados, no sustituye el informe final de 6–10 páginas ni permite afirmar que toda la consigna está terminada.

## Captura y sincronización incorporadas

Se añadieron formularios para el alta/modificación de fincas, gestión de propietarios y asignación de técnicos/verificadores. Las consultas separan datos de catálogo y personales, y las escrituras validan función y alcance en servidor. El técnico crea la medición con su identidad de sesión; ni el administrador ni el supervisor pueden introducir valores en su nombre.

La edición utiliza un contador de revisión esperado. Si otra escritura cambió el borrador, la operación rechaza el contenido obsoleto dentro de la transacción. La recepción offline utiliza además UUID y huella de contenido por persona. Un reintento confirmado recupera la constancia original, y un UUID reutilizado con contenido distinto se rechaza. Se verificó que dos sincronizaciones concurrentes iguales generan una medición y una constancia, mientras dos ediciones sobre la misma revisión permiten solo una actualización.

El cliente almacena sus datos en IndexedDB cifrados mediante Web Crypto. La clave derivada de una frase local se mantiene en memoria; el perfil se bloquea por inactividad. El Service Worker precarga solo recursos públicos de captura. La cola conserva los borradores hasta una confirmación de servidor válida y permite exportarlos cifrados. Los conflictos de revisión pueden compararse y resolverse mediante un nuevo intento explícito, conservando el antecedente local.

La nueva prueba HTTP creó un propietario, finca, período, asignaciones y medición; actualizó el borrador mediante sincronización, rechazó una revisión obsoleta, envió a revisión y generó un certificado que pudo descargar el propietario vinculado. El auditor sin encargo sobre esa finca recibió rechazo. La evidencia está en `evidencia/prueba_captura_http.txt` y `ejemplos_captura/`.

La migración se probó sobre una base creada por la entrega anterior, con un certificado vigente. Se comprobó que su SHA-256 no cambió y se conservaron cuentas, versiones y eventos. El resultado se registra en `evidencia/prueba_actualizacion.json`.


## Identidad incorporada

Se integraron cuentas, roles múltiples por persona, activación y recuperación verificadas, contraseñas Argon2id y segundo factor TOTP. La identidad laboral permanece estable entre cuentas y cambios de rol. Se aplica incompatibilidad entre técnico y verificador y se conserva el control histórico que impide revisar mediciones propias.

Las sesiones se registran con metadatos y una huella del identificador, sin exponer el token. La revocación y los cambios de identidad/credenciales se comprueban en servidor antes de permitir operaciones. La baja afecta todas las cuentas de la persona y termina sus asignaciones sin eliminar evidencia. La reautenticación sensible exige contraseña y factor recientes.

La migración conservó los datos de la versión anterior y exigió convertir las credenciales iniciales en accesos individuales. Se añadieron 66 pruebas de identidad y se ejecutó un recorrido HTTP con cuentas nuevas, activación, MFA, captura, revisión, emisión y verificación del certificado. Se rechazaron la reutilización de códigos, los accesos indebidos y la sincronización tras revocar la sesión. Las suites actuales suman 204 pruebas; los recorridos HTTP y la migración son evidencia adicional.

La comprobación de contraseñas filtradas envía solo un prefijo del hash y falla de forma cerrada si el proveedor no responde. La recuperación de identidad requiere verificación por un administrador; la entrega privada de códigos no se automatiza por correo. Estos límites y la falta de una prueba visual en el entorno quedan documentados. El módulo se entrega integrado localmente, sin afirmar despliegue en nube ni cumplimiento de los controles pendientes de persona 5.
