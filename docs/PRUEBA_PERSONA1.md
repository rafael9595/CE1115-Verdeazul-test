# Prueba de persona 1 e integración con 2/3/4

Actualice primero según `ACTUALIZAR_SIN_PERDER_DATOS.md`. Abra http://localhost:8000. Utilice datos sintéticos para las pruebas.

## 1. Primer acceso del administrador

Entre con `administrador` y la contraseña anterior. Para la clave inicial de demo:

```powershell
Get-Content .local\credenciales.txt
```

El sistema debe mostrar **Configurar segundo factor**. Escanee el QR desde una aplicación autenticadora compatible con TOTP o introduzca su clave manual. Confirme un código de seis dígitos; guarde los ocho códigos de recuperación que aparecen una sola vez.

Pulse **Continuar: cambiar contraseña inicial**, elija una contraseña propia de 15–128 caracteres y confirme. Debe cerrar la sesión. Vuelva a entrar con su contraseña nueva y otro código del autenticador. No utilice el mismo código de seis dígitos dos veces: espere al siguiente o utilice un código de recuperación sin usar.

Esperado: aparece el panel; **Mi cuenta**, **Sesiones** y **Cuentas** están disponibles. La clave vieja deja de servir para esa cuenta. No necesita modificar `DEMO_PASSWORD`: solo se usa para cuentas demo que todavía no se han preparado.

## 2. Prueba automática de las cuatro partes

Desde PowerShell en la carpeta nueva:

```powershell
.\.venv\Scripts\python.exe scripts\probar_identidad.py
```

El script pide la contraseña individual del administrador si la inicial ya no funciona. Luego pide un código TOTP nuevo o de recuperación. Los secretos se introducen sin mostrarse en la terminal.

Esperado: `"resultado": "OK"`. En `salida_identidad` quedan resultado, certificado original, certificado alterado y clave pública de esa prueba. El script comprueba:

- Alta y activación de cuentas nuevas de técnico, verificador y propietario.
- Rechazo de acceso solo con contraseña antes de MFA, de reutilizar un TOTP y de reutilizar un código de recuperación.
- Cierre de sesión real y rechazo de administración de cuentas por el técnico.
- Creación de finca/asignaciones, captura, envío, aprobación independiente y descarga del propietario.
- Firma original aceptada y contenido alterado rechazado.
- Revocación administrativa de la sesión del técnico y rechazo de su posterior sincronización.

Al terminar, las tres cuentas sintéticas quedan deshabilitadas; los datos/certificados de prueba se conservan. Su administrador mantiene su contraseña y MFA.

Para repetir sin sobrescribir evidencia:

```powershell
.\.venv\Scripts\python.exe scripts\probar_identidad.py --out salida_identidad_2
```

Si aparece 503 al activar una cuenta, la comprobación de contraseñas comprometidas no respondió o la clave MFA no se pudo cargar. Revise el mensaje de la página, conexión y `docker compose logs --tail 60 web`. Corrija la causa y repita con otra carpeta de salida; no desactive la comprobación para forzar un resultado.

## 3. Crear una cuenta desde la interfaz

En **Cuentas → Crear cuenta**, introduzca usuario e identidad laboral nuevos, nombre/contacto sintéticos, rol Técnico, referencia de identidad verificada y motivo. No agregue Verificador al mismo tiempo.

Al confirmar aparece **Entrega de acceso** con un código temporal. Abra otra sesión de navegador (ventana privada), visite http://localhost:8000/identity/recover/ y use ese código con una contraseña nueva. Configure su autenticador y conserve sus códigos. Esperado: la cuenta técnica entra; no dispone de administración de cuentas. El código de activación no puede canjearse nuevamente.

Si repite el alta con el mismo identificador laboral y otro usuario, los roles deben coincidir y el historial se comparte. Una persona deshabilitada debe habilitarse antes de crearle otra cuenta.

## 4. Sesiones y cierre

Desde la cuenta técnica abra **Sesiones**: debe ver solo sesiones de su identidad. Pulse **Revocar sesión** sobre la actual. Debe volver al login y el panel debe requerir entrar otra vez.

Entre nuevamente. Desde el administrador abra **Sesiones** y revoque la sesión técnica. Al actualizar el panel técnico debe pedir login. El administrador puede ver metadatos globales; no se muestran cookies ni tokens. El rol Seguridad puede consultar globalmente, pero no tiene el botón administrativo de revocación.

## 5. Roles y baja

Use una cuenta sintética, sin cambiar su único administrador:

1. Intente asignar Técnico y Verificador a la misma persona: debe rechazarse.
2. Cambie su rol a otro permitido con motivo: sus sesiones anteriores deben dejar de funcionar.
3. Si tenía asignaciones de una función retirada, deben quedar terminadas; el historial se conserva.
4. Deshabilite la persona: todas sus cuentas deben perder acceso.
5. Habilítela: debe poder preparar acceso nuevamente, pero necesita nuevas asignaciones operativas.

Cambiar el rol de un técnico a verificador no le permite aprobar mediciones propias anteriores. La suite comprueba ese caso también con cuentas múltiples.

## 6. Perfil y recuperación

En **Mi cuenta**, cambie el correo propio con autenticación reciente. No debe existir un control para cambiar su identidad legal, roles o titularidad.

Para recuperación, desde un administrador verifique la identidad de una cuenta sintética, registre referencia/motivo y emita un código. Si perdió el factor, marque explícitamente **Autorizar restablecimiento del segundo factor perdido**. En la otra sesión canjee el código, elija contraseña y configure/valide MFA. Deben revocarse las sesiones anteriores y el código no puede volver a usarse.

Si no autorizó reemplazar MFA, se requiere el factor anterior al canjear el código; después de canjear debe confirmar otro código nuevo para entrar. La recuperación no modifica roles ni asignaciones.

## 7. Autenticación reciente y límites

Tras cinco minutos, una operación sensible debe requerir **Renovar autenticación**; navegar por el panel no renueva ese plazo. Confirme contraseña y un código MFA nuevo. Una sesión sin actividad vence a los treinta minutos y toda sesión vence a las ocho horas. Las pruebas automatizadas verifican estos plazos sin esperar esas duraciones.

El límite es diez intentos fallidos en quince minutos, seguidos de una pausa de quince minutos. Si desea comprobarlo manualmente, utilice una cuenta sintética; las pruebas automatizadas cubren el límite y su funcionamiento entre varias cuentas de la misma identidad.

## 8. Comprobar lo anterior

- Abra un certificado emitido antes de actualizar; compruebe su firma con la clave pública correspondiente.
- Use `docs/PRUEBA_PERSONA2.md` para fincas, mediciones y trabajo sin conexión. Prepare antes contraseña/MFA de las cuentas que use.
- En **Trabajo sin conexión → Comprobar cifrado y almacenamiento del navegador**, deben pasar ocho comprobaciones. Luego pruebe preparar perfil, desconectar, recargar, guardar borrador, reconectar y sincronizar.
- Si la sesión venció o fue revocada, los pendientes locales deben conservarse. Entre de nuevo en otra pestaña y sincronice con la misma persona autorizada.

La frase que abre los borradores locales es distinta de la contraseña de la cuenta. Cambiar la contraseña del servidor no cambia la frase local ni recupera una frase local perdida.

## 9. Detener

```powershell
docker compose stop
```

Para continuar:

```powershell
docker compose start
```

No utilice `down -v`: elimina el volumen de datos.
