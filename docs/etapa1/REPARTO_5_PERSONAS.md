# Distribución propuesta para cinco integrantes

Se toma la solicitud como una división entre cinco personas y el desarrollo de una de esas partes: **Olman se encarga de firma y verificación de certificados**. Los cuatro puestos restantes se mantienen numerados para no asignar nombres sin acuerdo. El archivo de integrantes de la Parte 1 contiene cuatro nombres; el quinto nombre y carné deberán agregarse en los documentos de la entrega.

Las cinco responsabilidades de desarrollo no reducen los ocho roles de la aplicación: técnico, verificador, administrador, auditor, propietario, gerente, supervisor y seguridad. La identidad técnica de emisión es no interactiva. El equipo debe implementar toda la matriz.

## Responsabilidades y entregables

| Integrante | Responsabilidad principal | Entregable verificable |
|---|---|---|
| Persona 1 | Identidad, autenticación y autorización central | Argon2id, política de contraseñas, MFA según el diseño, sesiones revocables, reautenticación, roles efectivos, separación técnico/verificador por persona y filtro común de permisos |
| Persona 2 | Fincas, mediciones y captura/sincronización | Catálogo, titularidad, asignaciones, versiones, edición/envío, borradores locales cifrados, idempotencia y conflictos sin pérdida silenciosa |
| Persona 3 | Revisión, gestión y reportes | Aprobación/devolución independiente, períodos, enmiendas, invalidación, persistencia transaccional de certificados, precios y proyecciones por rol |
| **Olman** | **Firma y verificación** | **Este paquete: firma, clave pública incrustada, confianza en emisor, pruebas y demostración. Integración conjunta con Persona 3 y configuración de clave con Persona 5** |
| Persona 5 | Infraestructura, auditoría y monitoreo | Cloud Run, Neon, Secret Manager, Artifact Registry, imágenes sin root, Dependabot activo, bitácora, alertas H1/H2 y evidencia del despliegue |

La persona 1 implementa la decisión común de autorización; cada responsable la aplica en todas sus rutas. La persona 5 define el contrato de eventos; cada responsable registra sus operaciones. No se deja auditoría ni control de acceso para el último día.

Para equilibrar trabajo, Olman también consolida la tabla de cobertura y la evidencia del informe, mientras cada integrante redacta y prueba su componente. La persona 5 coordina infraestructura, pero los Dockerfiles y la corrección de dependencias pertenecen a cada responsable.

## Cobertura de la matriz completa

| Objeto | Responsable de funcionalidad | Apoyo obligatorio |
|---|---|---|
| O1 Cuenta y perfil | Persona 1 | Persona 5: secretos y auditoría |
| O2 Catálogo de fincas | Persona 2 | Persona 1: alcance y campos |
| O3 Asignaciones | Persona 2 | Persona 1: roles y separación de funciones |
| O4 Períodos | Persona 3 | Persona 2: bloqueo de escritura ordinaria |
| O5 Mediciones/versiones | Persona 2 | Persona 3: estados y revisión |
| O6 Decisiones de revisión | Persona 3 | Persona 1: C3 e historial por persona |
| O7 Enmiendas | Persona 3 | Persona 2: nueva versión específica |
| O8 Certificado e historial | Persona 3 + Olman | Persona 1: alcance; Persona 5: clave y eventos |
| O9 Datos personales | Persona 2 | Persona 1: acceso propio/administrativo |
| O10 Precio | Persona 3 | Persona 1: permisos y proyecciones |
| O11 Reportes | Persona 3 | Todos: datos filtrados y descargas |
| O12 Bitácora | Persona 5 | Todos: eventos y filtros de lectura |
| O13 Alertas | Persona 5 | Persona 1: agregación por identidad |
| O14 Configuración | Persona 5 | Persona 1: administración/seguridad |
| O15 Sesiones | Persona 1 | Persona 5: vista de seguridad |
| O16 Cola de sincronización | Persona 2 | Persona 1: revalidación C1/C2 |

La tabla es un reparto, no evidencia de implementación. Para la entrega hay que expandir cada celda de la matriz en operación, rol, alcance, condición, ruta o servicio y prueba positiva/negativa. Mantener V-01 a V-22 como escenarios de integración, sin tomarlos como sustituto de todas las celdas.

## Orden de integración propuesto

| Fecha de noviembre de 2026 | Objetivo |
|---|---|
| 10 | Acordar reparto, repositorio, nombres de entidades/IDs y contrato del certificado. Confirmar el quinto integrante |
| 11 | Publicar una aplicación mínima en Cloud Run con conexión cifrada a Neon y secretos externos |
| 12-13 | Integrar identidad, permisos, fincas, mediciones y revisión; cada ruta registra eventos |
| 14-15 | Integrar firma y persistencia en la aprobación; completar reportes, enmiendas, invalidación y sincronización |
| 16 | Probar toda la matriz, concurrencia de emisiones, reintentos, revocación y alteración de certificados |
| 17 | Corregir fallos y recopilar capturas reales, cobertura de matriz y desviaciones |
| 18 | Cerrar informe de 6-10 páginas, probar desde otra red y ensayar 15 minutos |
| 19 | Presentación: URL pública, credenciales por rol y evidencia accesible |

## Presentación de 15 minutos

Distribución orientativa: Persona 1, 3 minutos para acceso, roles y rechazo; Persona 2, 3 minutos para flujo técnico y sincronización; Persona 3, 3 minutos para revisión, gestión y reportes; Olman, 3 minutos para firma, verificación y alteración; Persona 5, 3 minutos para auditoría, secretos, Dependabot e infraestructura. Preparar cuentas y pestañas para recorrer los ocho roles sin dedicar tiempo a configuraciones durante la exposición.

Todos deben poder explicar el sistema completo: la consigna permite preguntar a cualquier integrante por código de otra persona.
