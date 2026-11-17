# Evidencia de la versión 4.0.0

Ejecuciones del 11 de noviembre de 2026, hora de Costa Rica, con datos sintéticos.

| Archivo | Evidencia |
|---|---|
| `pruebas_criptografia.txt` | 31 pruebas del núcleo original |
| `pruebas_integracion.txt` | 161 pruebas Django/PostgreSQL 17.11; 95 anteriores y 66 de identidad |
| `pruebas_cifrado_local.txt` | 12 pruebas JavaScript/Web Crypto en Node 24.22.1 |
| `prueba_http.txt` | Gestión y firma anteriores funcionando con MFA |
| `prueba_captura_http.txt` | Captura, sincronización, permisos, revisión y firma con accesos actuales |
| `prueba_identidad_http.txt` | Alta/activación/MFA, códigos no reutilizables, captura, revisión, firma y revocación |
| `prueba_actualizacion.json` | Migración 3.0.0 → 4.0.0; certificado e historial conservados |
| `prueba_configuracion.json` | Configuración nueva/importación, conservación de claves y rechazo de sobrescrituras |
| `prueba_navegador.json` | Limitación observada: Chromium no pudo iniciar por restricción de sockets |
| `pruebas.txt` | Registro histórico; no se suma al total actual |

Las suites suman **204 pruebas**. HTTP, migración y helpers son comprobaciones adicionales; no se suman pasos arbitrarios. Se utilizó Python 3.12.14, Django 5.2.19 y PostgreSQL 17.11 con Gunicorn de dos procesos para HTTP.

Las pruebas unitarias simulan la respuesta de la lista de contraseñas para tener resultados deterministas, y verifican consulta por prefijo, relleno y rechazo ante error. La prueba HTTP de identidad utilizó la consulta externa real. Una ejecución previa recibió 503 por una consulta no disponible; el recorrido posterior terminó correctamente. No se desactivó la política para la ejecución HTTP exitosa.

`ejemplos_integracion/`, `ejemplos_captura/` y `ejemplos_identidad/` contienen certificados sintéticos, resultados y claves públicas de esas pruebas. No contienen claves privadas, contraseñas, secretos MFA ni códigos temporales. Las muestras deben verificarse con sus claves públicas acompañantes; cada instalación tiene sus propias claves.

Las plantillas de identidad se comprobaron con Django para todos los roles y las acciones mediante HTTP/cookies/CSRF. El entorno bloqueó el inicio de Chromium; no se afirma una inspección visual ni ejecución de las ocho comprobaciones de IndexedDB/Service Worker. Se incluyen instrucciones para completarlas en el navegador del usuario.

Docker Desktop/Windows, Cloud Run/Neon y GitHub Actions no se ejecutaron aquí. La confirmación del usuario de que su aplicación funcionaba corresponde a 3.0.0; la nueva versión 4.0.0 debe probarse en su instalación.
