# Recorrido de prueba: personas 2, 3 y 4

En la versión 4.0.0 prepare primero las contraseñas individuales y MFA según `PRUEBA_PERSONA1.md`. Las cuentas iniciales dejan de utilizar una contraseña compartida permanente.

Use datos sintéticos. La prueba automática `scripts/probar_captura.py` crea una finca y período nuevos y comprueba la conexión hasta el certificado. Los pasos siguientes permiten recorrer las pantallas y verificar el comportamiento offline en su navegador.

## 1. Registrar propietario y finca

1. Entre como `administrador`; la contraseña sigue en `.local\credenciales.txt`.
2. Abra **Propietarios → Registrar propietario**. Use `Propietario de prueba P2` y un contacto ficticio.
3. En ese propietario, abra **Vincular cuenta de propietario o representante**. Seleccione `DEMO-PROPIETARIO` y registre una referencia de prueba, por ejemplo `Documento sintético revisado P2`. En operación real la referencia debe corresponder a una verificación administrativa real; el sistema registra esa comprobación, no verifica documentos legales externamente.
4. Abra **Fincas → Registrar finca**. Use un número registral nuevo, nombre `Finca de prueba P2`, el propietario recién creado y área declarada `10.50`.
5. Para la prueba puede utilizar este polígono sintético:

```text
-84.1000,9.9300
-84.0990,9.9300
-84.0990,9.9310
-84.1000,9.9310
-84.1000,9.9300
```

El área de ejemplo no se calcula a partir del polígono y no representa una finca real. Las coordenadas son longitud,latitud; la última repite la primera.

## 2. Preparar período y asignación

1. En el panel, como `administrador` o `gerente`, abra un **período nuevo** llamado `Prueba P2`. Esto permite trabajar aunque hubiera cerrado el período anterior.
2. Entre como `supervisor` y abra **Asignaciones**.
3. En la finca nueva, seleccione `DEMO-TECNICO`, registre un motivo y pulse **Asignar técnico**.

Asignar otro técnico a la finca no cambia al técnico original de una medición ya creada. Las correcciones de esa cadena siguen correspondiendo a su autor original.

## 3. Capturar, revisar y firmar

1. Como `tecnico`, abra **Capturar medición**. Seleccione la finca y período nuevos.
2. Complete fecha, metodología `Demostración sintética` y una fila: variable `carbono_reportado`, valor `125.50`, unidad `tCO2e`.
3. Pulse **Guardar borrador**. En el panel aparecerá **BORRADOR**. Puede usar **Editar borrador** sin escribir JSON.
4. Pulse **Enviar a revisión**. El estado cambia a **ENVIADA** y la edición se bloquea.
5. Como `supervisor`, abra **Asignaciones → Asignar verificador a medición**, identifique la finca/período y asigne `DEMO-VERIFICADOR` con un motivo.
6. Como `verificador`, apruebe esa medición. Se ejecuta el módulo de la persona 3 y se llama a la firma de Olman.
7. Como `propietario`, verá la finca vinculada y podrá descargar el certificado. En **Verificar archivo**, el original emitido por esa instalación debe indicar `VALIDO`.

Un auditor no recibe automáticamente acceso a la finca nueva: necesita un encargo vigente. El administrador no puede medir ni aprobar en nombre del técnico/verificador.

## 4. Comprobación local del navegador

Como `tecnico`, abra **Trabajo sin conexión**. En la parte inferior, abra **Comprobar cifrado y almacenamiento del navegador** y pulse **Ejecutar comprobación**.

Se esperan ocho resultados correctos: cifrado en IndexedDB, recuperación, rechazo de frase incorrecta, detección de alteración, conflicto de pestañas, conservación de datos ante conflicto, limpieza que no elimina pendientes y rechazo de una confirmación incompleta. Utiliza una base temporal distinta y no borra sus perfiles de trabajo.

Estas ocho verificaciones se proporcionan para su navegador; no están incluidas dentro de las 204 ejecutadas en el entorno de desarrollo.

## 5. Captura real sin conexión

1. Con el servidor activo y sesión de `tecnico`, abra **Trabajo sin conexión** en **http://localhost:8000/campo/**. Use siempre el mismo origen; `localhost` y `127.0.0.1` tienen almacenamientos independientes.
2. Elija una frase local de al menos 15 caracteres, distinta a la contraseña de acceso, y pulse **Preparar perfil nuevo**. Si ya existe, seleccione su perfil y pulse **Desbloquear**.
3. Pulse **Actualizar fincas y borradores** mientras tiene conexión. Espere el mensaje de datos actualizados.
4. Para simular una caída del servicio, en PowerShell ejecute:

```powershell
docker compose stop web
```

5. Recargue `/campo/`. La página pública debe abrirse desde la copia precargada. Desbloquee su perfil con la frase local. Si el navegador no permite esta operación, conserve la evidencia y no considere validada su compatibilidad offline.
6. Seleccione **Nueva medición**, una finca preparada y un período abierto preparado. Complete fecha, metodología y valores. Pulse **Guardar borrador cifrado**.
7. Debe aparecer en **Pendientes**. **Exportar respaldo cifrado** permite guardar una copia; el archivo no contiene valores en texto claro ni la frase. La pérdida de la frase, del navegador o del dispositivo sin un respaldo puede hacer irrecuperables los pendientes.
8. Pulse **Bloquear**, recargue y desbloquee otra vez. El pendiente debe seguir disponible. No se guardan la frase ni la clave de cifrado en el almacenamiento.
9. Reactive el servicio:

```powershell
docker compose start web
```

10. En la página de campo, pulse **Sincronizar pendientes**. Si venció la sesión, utilice **Iniciar sesión en otra pestaña**, entre como el mismo técnico, vuelva y reintente. No necesita borrar ni recrear su perfil.
11. Debe aparecer una constancia con UUID y hora de recepción. El borrador ya recibido se consulta en el panel, donde puede enviarlo a revisión. Sincronizar no aprueba ni emite un certificado.

El perfil se bloquea tras cinco minutos sin actividad. **Guarde los cambios del formulario antes de ese tiempo o de cerrar la pestaña**; la garantía de conservación aplica a borradores que confirmaron guardado local, no a texto que nunca se guardó.

## 6. Comprobar conflicto sin pérdida

1. Cree una medición online y déjela en **BORRADOR**.
2. En la página de campo actualice datos y seleccione ese borrador como origen. Cambie un valor y guárdelo localmente.
3. Desde otra pestaña del mismo técnico, edite el borrador online y guarde otro valor. Esto incrementa su revisión.
4. En campo, sincronice. Debe aparecer un **CONFLICTO** y conservarse el contenido local. El valor del servidor no cambia.
5. Pulse **Comparar con servidor**. Revise los dos contenidos. Si corresponde conservar su propuesta local, pulse **Preparar nuevo intento con mis valores**; se crea otro UUID sobre la revisión actual y se conserva el intento anterior.
6. Sincronice explícitamente. Si nadie volvió a modificar el borrador, se confirma el nuevo intento y el anterior queda como resuelto, conservado localmente. Si cambió otra vez, vuelve a rechazarse sin sobrescribir.

Si el servidor ya recibió/aprobó la versión o retiró su asignación, no se habilita esa resolución. Conserve/exporte el pendiente y tramite la solución autorizada. No se convierte automáticamente una captura en una enmienda ni se reabre un período.

Una recepción con respuesta perdida se reintenta con el mismo UUID y contenido. Los intentos que pudieron llegar al servidor no se editan; así el reintento puede recuperar su confirmación sin crear otra medición.

## 7. Límites de lo que debe observar

- No se cachean sesiones, páginas de propietarios, reportes ni respuestas API. Solo la página pública de campo y sus recursos estáticos entran en Cache Storage; los datos de campo están dentro del almacén cifrado.
- La sesión del servidor puede vencer mientras trabaja offline. La frase local solo desbloquea el dispositivo y no reemplaza la autenticación al sincronizar.
- El estado de colas de administrador/supervisor muestra el último conteo recibido, no una lectura remota de un dispositivo desconectado.
- Se conservan constancias mínimas durante siete días, limpiadas al desbloquear. No se eliminan pendientes por vencimiento o error. El historial confirmado permanece en PostgreSQL.
- Los formularios y el servidor fueron probados por HTTP; falta confirmar Service Worker/IndexedDB y el recorrido completo en Windows y Safari/iOS. No se promete compatibilidad offline universal.
