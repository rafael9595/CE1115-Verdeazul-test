# Aporte del módulo de certificados al informe de implementación

Este texto documenta el módulo entregado y sus pruebas locales. No reemplaza el informe grupal de 6 a 10 páginas ni acredita configuración de nube. Debe incorporarse al informe final junto con los resultados reales de integración.

## Implementación

Se implementó un módulo Python para firmar y verificar certificados de carbono mediante Ed25519. La firma protege una instantánea que contiene la identificación del certificado, datos históricos de finca, medición y versión, aprobación, participantes de la cadena y eventual antecedente. El archivo incorpora la clave pública utilizada y su huella SHA-256. Se excluyeron campos de propietario, precio y secretos para conservar las restricciones de información de la Parte 1.

La aplicación principal debe construir la instantánea con información autorizada de PostgreSQL. El módulo criptográfico comprueba el esquema y genera la firma; la aprobación independiente, los permisos por objeto, la unicidad de vigencia y la persistencia corresponden al servicio de negocio. La integración se diseñó para guardar aprobación, archivo firmado y evento local dentro de una transacción, de modo que un error no produzca una confirmación parcial. Esta transacción todavía requiere implementación y prueba sobre los modelos del repositorio común.

La verificación diferencia integridad y confianza en el emisor. Primero comprueba la firma con la clave incluida. Después compara su huella con una lista de claves públicas reconocidas, distribuida por un canal independiente. Esta segunda operación evita aceptar como oficial un archivo que un tercero haya firmado con su propia clave. La vigencia administrativa no se infiere del resultado criptográfico: el verificador local la señala como no consultada.

## Controles y evidencia disponible

| Control | Ubicación | Comprobación realizada | Estado |
|---|---|---|---|
| Firma digital | `certificados/core.py`, `issue_certificate` | Original aceptado y alteraciones rechazadas | Probado localmente |
| Clave pública incrustada | `issue_certificate` | Verificación sin acceso a privada | Probado localmente |
| Emisor reconocido | `verify_certificate` | Documento firmado con otra clave no aceptado | Probado localmente |
| Validación del archivo | `parse_json`, `validate_payload` | Entradas duplicadas, demasiado grandes, algoritmo incorrecto y formato inválido rechazados | Probado localmente |
| Secreto externo | `load_private_key_from_environment` | Carga por entorno y archivo; error si falta o hay dos fuentes | Probado localmente; Secret Manager pendiente |
| Exclusión de campos sensibles | `validate_payload` | Propiedades adicionales de propietario/precio/secretos rechazadas | Probado localmente |
| Emisión autorizada C3/C9 | Servicio transaccional de Django | Requiere usuarios, modelos y Neon | Pendiente de integración |
| Restricción de vigencia única | Migración y transacción en PostgreSQL | Requiere prueba de concurrencia | Pendiente de integración |
| Invalidación C8 y auditoría C12 | Servicio de negocio y bitácora | Requiere sesiones, roles y eventos | Pendiente de integración |
| Contenedor sin root | `Dockerfile`, UID 10001 | Revisión del archivo; construcción/ejecución no realizada | Pendiente de ejecución |
| Dependabot | `.github/dependabot.yml` | Archivo de configuración preparado | Activación y evidencia pendientes |

La batería del módulo ejecutó 31 pruebas satisfactorias en Python 3.12.14 con cryptography 50.0.0. Incluyó validación de firma, alteraciones de secciones de negocio, sustitución de firma o clave, identidad no confiable, formato inválido, lectura de secretos y códigos de salida de la CLI. Los archivos de `ejemplos/` permiten repetir la comprobación sin clave privada. Esto no demuestra todavía los controles de toda la aplicación ni la cobertura completa de la matriz.

## Gestión de secretos prevista

El módulo no contiene credenciales fijas. La clave se carga mediante `VERDEAZUL_SIGNING_PRIVATE_KEY_PEM` o `VERDEAZUL_SIGNING_PRIVATE_KEY_FILE`. Para Cloud Run se prevé una referencia a una versión concreta en Secret Manager, accesible por la identidad de servicio del backend. La evidencia de esa configuración deberá recopilarse después del despliegue, ocultando siempre el valor secreto.

## Decisiones y límites

Se eligió un archivo JSON firmado porque la consigna no exige un formato documental específico y este permite probar directamente integridad y autenticidad del emisor. El formato usa un esquema cerrado y serialización determinista para evitar ambigüedades. No se presenta como firma PDF ni como una firma digital con certificación jurídica.

Los números de medición de la demostración son sintéticos. El módulo no valida la metodología científica, la correspondencia catastral, la asignación del verificador ni el historial completo de participantes. Esos controles deben completarse en la aplicación. La clave de firma se usa dentro del monolito, de modo que su separación como módulo no protege frente a un compromiso total del proceso de aplicación.

La migración de máquinas virtuales y réplica gestionada por el equipo a Cloud Run y Neon, así como la entrega de secretos por entorno, debe justificarse en las desviaciones de arquitectura del informe grupal. No se atribuyen garantías de RPO, retención o recuperación a un plan de Neon que todavía no se ha configurado y evaluado.

## Evidencia final pendiente de recopilar

1. Certificado emitido desde una aprobación válida en la URL pública y descargado con permisos correctos.
2. Verificación del original y rechazo de una copia con una medición alterada.
3. Rechazo del servidor cuando un rol no autorizado intenta aprobar, emitir o descargar.
4. Eventos correspondientes de aprobación, emisión, descarga e intento rechazado.
5. Secret Manager y vinculación del secreto con Cloud Run, sin exponer el valor.
6. Dependabot activo y, si hubo alertas, una corrección documentada.
7. Etiqueta/digest real de la imagen del backend que contiene el módulo.

## Fuentes técnicas

- Cryptography 50.0.0, Ed25519: https://cryptography.io/en/50.0.0/hazmat/primitives/asymmetric/ed25519/
- Django 5.2, transacciones: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Google Cloud Run, secretos: https://docs.cloud.google.com/run/docs/configuring/services/secrets

Las fuentes respaldan el uso de las API y el patrón de integración. La evidencia de ejecución corresponde al código, las pruebas y los archivos adjuntos, no a la documentación de los proveedores.
