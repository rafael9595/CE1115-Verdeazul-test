# Aporte de gestión y certificados

Se implementó un backend Django conectado a PostgreSQL para gestionar revisiones, períodos, enmiendas, certificados y reportes. La aprobación consulta la identidad y asignación vigentes del verificador, comprueba que no haya participado como autor o corrector en la cadena de versiones y exige una versión enviada sin decisión previa.

Tras validar estas condiciones, el backend construye una instantánea desde la base de datos y llama al módulo de certificados desarrollado previamente. Ese módulo genera una firma Ed25519 sobre el contenido determinista e incluye la clave pública y su huella. La decisión, el cambio de estado, los bytes firmados y el evento de emisión se guardan dentro de una misma transacción. Un fallo de firma o de escritura del evento revierte la aprobación y evita conservar registros parciales.

PostgreSQL impone un máximo de un certificado vigente por finca mediante una restricción única condicional. La aplicación bloquea los registros afectados y utiliza una identidad de operación para reconocer reintentos. Se comprobaron solicitudes concurrentes de dos verificadores y reintentos concurrentes de una misma petición: en ambos casos se conservó un único certificado.

Las correcciones preservan la versión anterior y crean una nueva. Una versión aprobada, o una corrección dentro de un período cerrado, necesita una enmienda autorizada por un administrador recientemente autenticado y vinculada al técnico original. La autorización permite corregir esa versión específica sin reabrir el período ni sustituir la revisión independiente. La invalidación conserva el documento firmado y registra motivo, actor y fecha; un reemplazo relaciona ambos certificados.

Los reportes se filtran según rol y alcance. El propietario consulta su información; el auditor accede únicamente al encargo vigente y recibe una proyección sin datos personales del propietario ni precios. La descarga directa del certificado aplica su propia autorización. Los eventos y decisiones se protegen con triggers que rechazan modificaciones o eliminaciones ordinarias.

## Resultados ejecutados

| Comprobación | Resultado observado |
|---|---|
| Suite del módulo de firma | 31 pruebas correctas |
| Suite de gestión en PostgreSQL 17.11 | 51 pruebas correctas |
| Consistencia de migraciones y comprobación Django | Sin cambios pendientes ni problemas detectados |
| HTTP con Gunicorn, cookies y CSRF | Técnico rechazado; aprobación/descarga/verificación correctas; reintento conservó el certificado; alteración rechazada |
| Formularios HTTP de devolución y corrección | Versión 1 devuelta preservada; versión 2 editada, enviada y aprobada por verificador |

Los registros se incluyen en `evidencia/pruebas_criptografia.txt`, `evidencia/pruebas_integracion.txt` y `evidencia/prueba_http.txt`. Los archivos de `ejemplos_integracion/` provienen de la prueba HTTP con datos sintéticos. Contienen solo documentos y clave pública, no la privada.

Se utilizaron Python 3.12.14, Django 5.2.19, PostgreSQL 17.11, cryptography 50.0.0, psycopg 3.3.8, Argon2 y Shapely. La comprobación cartográfica utiliza Natural Earth, con las limitaciones de precisión descritas en `gestion/data/README.md`.

## Alcance del resultado

Se verificó la integración local de los módulos de gestión y firma. La inspección visual en Chromium no pudo ejecutarse por restricciones del entorno; las plantillas y sus formularios se verificaron mediante Django y HTTP. No se presentan evidencias de Docker Desktop, Windows, publicación en nube o CI porque esas ejecuciones no se realizaron. La identidad completa, captura/sincronización, RLS, infraestructura, alertas y auditoría independiente requieren el trabajo de los otros módulos. El detalle está en `COBERTURA_Y_LIMITES.md`.

Este texto es el aporte técnico de estas dos partes, no sustituye el informe final de 6–10 páginas ni permite afirmar que toda la consigna está terminada.
