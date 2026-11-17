# Prueba de gestión y firma (personas 3 y 4)

Para fincas, captura y trabajo offline incorporados en 3.0.0 consulte `PRUEBA_PERSONA2.md`. Este recorrido sigue comprobando los módulos anteriores.

Todos los pasos utilizan datos sintéticos locales. No requiere una cuenta de Google Cloud ni Neon para esta prueba. La publicación de la Parte 2 se realiza después con la persona 5.

## 1. Preparar la aplicación

Extraiga el ZIP, entre en `verdeazul_integrado` y ejecute los cinco comandos de arranque del README. Mantenga Docker Desktop encendido. Espere a que `docker compose logs --tail 40 web` indique que Gunicorn escucha en el puerto 8080; desde Windows se accede por **http://localhost:8000**.

Lea `.local\credenciales.txt`. Contiene los usuarios y una contraseña aleatoria común **solo para la demostración**. En el sistema definitivo cada cuenta necesita su propia credencial y la política completa de identidad.

| Usuario | Propósito de prueba |
|---|---|
| `tecnico` | Correcciones y envío; no puede aprobar |
| `verificador`, `verificador_2` | Revisión independiente de las tres fincas asignadas |
| `administrador` | Autorizar enmiendas, invalidar y consultar historial |
| `gerente` | Períodos, precios y reportes de su proyección |
| `supervisor` | Consulta técnica; sin descarga directa del certificado |
| `auditor` | Reportes de un encargo que vence 30 días después de cargar la demo |
| `propietario` | Sus fincas, reportes y precios |
| `propietario_ajeno` | Control negativo: no puede ver las fincas del primer propietario |
| `seguridad` | Metadatos de bitácora; sin mediciones, precios o datos personales |

Use **Salir** antes de cambiar de usuario. Dos pestañas del mismo perfil comparten sesión; para dos usuarios simultáneos use perfiles distintos o una ventana privada.

## 2. Comprobar automáticamente la conexión

Antes de procesar fincas manualmente:

```powershell
.\.venv\Scripts\python.exe scripts\probar_integracion.py
```

Resultado esperado: `"resultado": "OK"` y todos los indicadores en `true`. La finca **A** queda aprobada con certificado. En **B**, la versión 1 queda devuelta y la versión 2 aprobada. **C** queda enviada para el recorrido manual. El script usa HTTP real, cookies de sesión y CSRF.

Si avisa que A/B ya fueron procesadas, no es una pérdida de funcionalidad: conserva la evidencia existente y no vuelve a ejecutar una emisión con otra identidad de operación. Continúe con los pasos manuales. Para repetir suites sin alterar la demo use los comandos `manage.py test` y `unittest` del README.

## 3. Verificar original y alterado

1. Abra **Verificar archivo**.
2. Seleccione `salida_prueba\certificado_original.json` y presione **Verificar firma**.
3. Debe aparecer `VALIDO`, firma correcta y clave reconocida.
4. Seleccione `salida_prueba\certificado_alterado.json` y repita. Debe indicar `FIRMA_INVALIDA`.

La alteración cambia el primer valor de medición a `9999.00` y conserva la firma original: el documento ya no coincide con lo firmado. El script cambia una copia descargada, no la base de datos.

`NO_CONSULTADO` en vigencia es esperado: verificar un archivo comprueba firma y confianza, mientras que su estado actual se consulta en el panel/reporte autenticado. El original podría seguir verificando correctamente aunque un administrador lo invalide después.

## 4. Revisar y corregir desde las pantallas

1. Entre como `verificador`. En **C · Concurrencia · Versión 1**, escriba un motivo y pulse **Devolver**.
2. Salga y entre como `tecnico`.
3. En esa versión, abra **Crear nueva versión de corrección**. Deje vacía la enmienda, pues el período sigue abierto y es una devolución. Pulse **Crear corrección**.
4. En la versión 2, abra **Editar borrador**. Cambie metodología o un valor en el formulario; conserve el nombre de la variable y su unidad.
5. Pulse **Guardar borrador**, luego **Enviar a revisión**.
6. Entre como `verificador` y pulse **Aprobar y emitir** sobre la versión 2.
7. En **Certificados**, descargue el original y verifíquelo.

Se conservan ambas versiones. El técnico no dispone de un botón de aprobación y el servidor rechaza ese intento aunque se invoque la ruta directamente. La edición utiliza el formulario de valores incorporado por la persona 2.

## 5. Probar precio y filtrado

1. Entre como `gerente` y abra **Registrar precio** en un certificado. Guarde `25000.00` en CRC.
2. Abra su reporte autorizado. Debe contener el precio y omitir el nombre/contacto del propietario.
3. Entre como `propietario` y consulte el reporte: puede ver su precio y datos propios.
4. Entre como `auditor`: dispone del reporte del encargo, con versiones y documento firmado, sin las propiedades `price` y `owner`. No tiene descarga directa O8.
5. Entre como `propietario_ajeno`: no verá las fincas de prueba. Conocer un UUID ajeno no concede acceso.
6. Entre como `seguridad` y abra la bitácora: encontrará acción, actor, fecha, resultado y regla; no valores de medición ni datos del propietario.

La representación firmada dentro del reporte del auditor es la proyección permitida de O11; no equivale a habilitarle la ruta de descarga O8.

## 6. Enmienda con período cerrado y reemplazo

Haga este recorrido **al final**, porque cerrar el período bloquea las correcciones ordinarias de todas las fincas de esa carga.

1. Como `gerente`, cierre **Período de demostración** con motivo `Cierre de prueba`.
2. Como `propietario`, en la versión aprobada de **A**, abra **Solicitar enmienda**, escriba un motivo y envíela.
3. Como `administrador`, localice la solicitud en **Enmiendas**. Si lleva más de cinco minutos autenticado, abra **Renovar autenticación**, ingrese la contraseña y confirme.
4. Escriba el motivo de autorización y pulse **Autorizar corrección**. Copie el UUID de esa enmienda. Autorizar no emite ni aprueba un certificado.
5. Como `tecnico`, en la versión aprobada original de A, abra **Crear nueva versión de corrección**, pegue el UUID y cree la versión nueva.
6. Edite el borrador y envíelo. El período continúa **CERRADA**; la excepción aplica únicamente a esa enmienda y técnico original.
7. Como `verificador`, intente aprobar. Debe rechazarse porque A todavía tiene un certificado vigente. Vuelva al panel.
8. Como `administrador`, renueve autenticación si hace falta e **invalide el certificado anterior** con motivo `Reemplazo por corrección autorizada`.
9. Como `verificador`, apruebe la versión corregida. Ahora se crea un certificado nuevo con `predecessor_certificate_id` que señala al anterior.
10. Consulte el reporte: aparecen versiones, enmienda, motivo/fecha/autor de invalidación, certificado anterior invalidado y nuevo vigente.

El archivo anterior conserva sus mismos bytes y su firma. Invalidación es un cambio de estado registrado, no una edición del documento histórico. Si falla la aprobación entre los pasos 8 y 9, la finca permanece sin certificado vigente hasta resolverla; no se presenta el reemplazo administrativo completo como una única transacción.

## 7. Qué revisar si no inicia

| Situación | Comprobación |
|---|---|
| `docker` no se reconoce | Instale/inicie Docker Desktop y abra otra terminal |
| Docker no conecta | Espere al motor de contenedores Linux y ejecute `docker info` |
| Página no disponible | `docker compose ps` y `docker compose logs --tail 60 web` |
| Puerto 8000/55432 ocupado | Detenga el otro servicio o ajuste el puerto publicado y la URL de prueba |
| Configuración ya existe | Es normal al repetir `setup_local.py`; conserva claves y contraseña |
| Firma con clave no reconocida | Use el archivo producido por su instancia y su clave pública; las muestras del ZIP tienen otra clave |
| Error de autenticación reciente | Renueve la identidad como administrador y repita la acción |
| `salida_prueba` ya existe | Conserve esa evidencia. Un nombre nuevo de salida no restablece el estado de A/B |

Si necesita ayuda, conserve el texto del error y los últimos registros del servicio. No incluya `.env`, `.local/config.json`, la contraseña ni la clave privada.
