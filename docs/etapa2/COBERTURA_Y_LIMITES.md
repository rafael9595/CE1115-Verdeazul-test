# Cobertura y límites de la integración

## Fuentes y alcance

Se utilizaron las instrucciones `Proyecto_Parte2_Implementacion_CE1115.pdf` y los cinco documentos de Parte 1: Arquitectura, Atributo DI, Control de Acceso, Matriz y Políticas, grupo 3. Esta entrega implementa gestión/revisión/reportes de la persona 3 y conecta la firma de Olman. Los apoyos de acceso y captura son suficientes para probar esa integración, pero no equivalen a completar los módulos 1/2/5.

## Controles implementados

| Regla/objeto | Implementación | Evidencia en `gestion/tests/test_integration.py` |
|---|---|---|
| C3 / O6 | Verificador asignado, versión enviada, sin decisión previa, no autor/corrector de ninguna versión por identidad laboral | Autorización, rol cambiado, cuenta duplicada e historial |
| C2 / O5 | Borrador editable por técnico original asignado; enviado inmutable; devolución conserva origen y crea versión | Corrección, edición prohibida, técnico no disponible |
| O4 | Crear y cerrar períodos para administrador/gerente; no reabrir cerrados | Permisos y trigger de no reapertura |
| C7 / O7 | Solicitud y autorización específica; administrador con autenticación ≤5 minutos; técnico original; sin reapertura general | Flujo completo con período cerrado y roles negativos |
| C8 / O8 | Invalidar con motivo, autor y fecha; bytes originales preservados | Firma válida tras invalidación y guardas SQL |
| C9 | Un vigente por finca entre todos los períodos; firma y persistencia transaccionales; reemplazo con enmienda/antecedente invalidado | Restricción única, concurrencia, rollback de firma/auditoría |
| C9 / geografía | Polígono cerrado, simple, con área geométrica positiva y contenido en Costa Rica según Natural Earth | Rechazo de geometría inválida; límites de cartografía documentados |
| O8 | Descarga original restringida; auditor/supervisor/seguridad sin descarga directa | Matriz de descarga |
| O10 | Precio: escritura administrador/gerente, lectura adicional de propietario propio | Proyecciones positivas/negativas |
| O11 | Reporte según ámbito; auditor con encargo vigente y sin propietario/precio; cadena y original firmado preservados | Encargo vencido, propietario ajeno, historial sin acceso futuro |
| Integridad | Revisiones/eventos/operaciones de solo anexado; versiones enviadas y archivos firmados protegidos por triggers | UPDATE/DELETE rechazados; datos históricos preservados |
| Reintentos | UUID por persona + digest de petición; reautorización actual | Repetición, reutilización distinta, revocación y concurrencia |
| Apoyo C1 | Argon2, sesión inactiva 30 min/máxima 8 h, cambio de rol, CSRF, reautenticación y límite simple de intentos | Sesión, acceso real con contraseña, rol y CSRF |

## Diferencias y decisiones que deben registrarse

1. **Correcciones:** una devolución crea una versión nueva; no se sobrescribe la versión devuelta. Mantiene la trazabilidad y exige ajustar cualquier texto previo que suponga edición sobre el mismo registro.
2. **Identidad:** se utiliza un rol primario por persona con capacidades explícitas. No se ha implementado un motor de múltiples roles acumulables; el equipo debe acordar esa correspondencia al integrar identidad.
3. **Certificado:** se conserva el formato JSON `VA-CARBON-1` firmado con Ed25519 y clave pública incrustada. No es PDF firmado, JWS, una PKI comercial ni una validación jurídica de firma digital.
4. **Geografía:** Natural Earth 1:10m es una referencia general. No prueba concordancia catastral ni equivalencia entre el área declarada y el polígono. Cerca de límites/costas puede rechazar geometrías legítimas; el origen debe mejorarse si la validación exigida requiere precisión catastral. Los valores y polígonos de demo no son mediciones reales.
5. **Auditoría:** los triggers impiden cambios ordinarios de registros, pero un propietario/superusuario de BD puede alterar el esquema. No se afirma resistencia frente a ese administrador ni existencia de una copia independiente.
6. **Autorización:** los servicios y consultas aplican controles de fila y proyecciones en Django. **No se implementaron políticas PostgreSQL RLS** ni se verificaron roles de BD de mínimos privilegios en producción. Deben coordinarse entre personas 1/5 antes de afirmar conformidad completa con la arquitectura de Parte 1.
7. **Vigencia:** la firma offline no consulta revocaciones. El panel/reporte indica el estado de negocio. La invalidación anterior y la aprobación del reemplazo son dos actos autorizados; entre ellos puede no haber certificado vigente.
8. **Entorno:** ejecución comprobada en Python 3.12.14/PostgreSQL 17.11. La imagen propone Python 3.13, de acuerdo con la arquitectura; su construcción/ejecución sigue por comprobar en Docker.

## Lo que sigue pendiente para toda la Parte 2

| Componente pendiente | Responsable principal |
|---|---|
| Registro/administración de cuentas, recuperación, MFA según diseño, administración de sesiones y matriz completa O1/O15 | 1 |
| Catálogo final, titulares, administración de asignaciones, captura, cola local cifrada y sincronización/conflictos O2/O3/O5/O9/O16 | 2 |
| RLS, separación de credenciales de ejecución/migración y pruebas con rol restringido | 5 con 1 y 3 |
| Bitácora completa de todos los módulos, copia independiente/retención y alertas H1/H2 | 5 |
| Cloud Run, PostgreSQL Neon cifrado, Secret Manager, Artifact Registry y URL HTTPS accesible | 5 |
| Activación/evidencia de Dependabot y revisión de alertas reales en repositorio | 5 con todos |
| Cobertura celda por celda de toda la matriz, informe final de 6–10 páginas y presentación de 15 minutos | Todos |

Las 82 pruebas demuestran los casos definidos para estos módulos, no todas las celdas del proyecto. No se desplegó ningún servicio en nube, no se verificó acceso desde otra red y no se ejecutó GitHub Actions. Tampoco se probaron recuperación ante desastre, carga sostenida o mecanismos offline.
