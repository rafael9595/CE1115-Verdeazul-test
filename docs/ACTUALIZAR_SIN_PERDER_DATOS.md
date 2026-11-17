# Actualizar a 4.0.0 conservando lo anterior

Esta actualización añade la persona 1 a las personas 2/3/4. Conserva el proyecto Compose `verdeazul-p3-p4` y el volumen `verdeazul_db`; no cambia las claves de los certificados existentes.

## Extracción nueva: carpeta (3) → carpeta nueva

La ruta anterior utilizada por Olman es:

`C:\Users\irodr\Downloads\Parte2_Olman_Certificados (3)\verdeazul_integrado`

Extraiga el ZIP nuevo. Abra PowerShell **dentro de la nueva carpeta `verdeazul_integrado`**. No necesita activar el entorno Python. Docker Desktop debe indicar Engine running.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\adoptar_configuracion.py --desde "C:\Users\irodr\Downloads\Parte2_Olman_Certificados (3)\verdeazul_integrado"
.\.venv\Scripts\python.exe scripts\configurar_identidad.py
docker compose up -d db
.\.venv\Scripts\python.exe scripts\respaldar_bd.py
docker compose stop web
docker compose up --build -d
docker compose logs --tail 60 web
docker compose ps
```

**Si un comando da error, resuélvalo antes de continuar.** En especial, no continúe sin respaldo confirmado. Si su última instalación operativa está en otra ruta, cambie solo el valor de `--desde`.

El helper de importación copia `.env`, la configuración local y las claves anteriores; comprueba que las claves de firma coincidan y ajusta sus rutas. Si ya importó esa configuración al destino, no vuelva a ejecutar `adoptar_configuracion.py`: el helper se niega a sobrescribirla. Continúe con `configurar_identidad.py`, que sí puede repetirse y conserva su clave.

`respaldar_bd.py` escribe un respaldo binario PostgreSQL en `respaldos/`. Contiene datos y hashes de cuentas. Conserve además una copia privada de `.env` y `.local`, incluida la nueva `identity.key`; un respaldo de BD por sí solo no incluye las claves externas.

Use la carpeta nueva como única carpeta operativa. Ambas extracciones apuntan al mismo proyecto/volumen Docker; no representan dos bases independientes.

## Si copia el código sobre la misma carpeta

Conserve `.env`, `.local` y `.venv`. Reemplace únicamente los archivos entregados, luego:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\configurar_identidad.py
docker compose up -d db
.\.venv\Scripts\python.exe scripts\respaldar_bd.py
docker compose stop web
docker compose up --build -d
docker compose logs --tail 60 web
```

## Primer acceso después de actualizar

1. Abra http://localhost:8000. Las sesiones anteriores quedaron cerradas por la migración.
2. Entre como `administrador` con la contraseña que ya utilizaba. Si era la inicial, puede consultarla localmente con `Get-Content .local\credenciales.txt`.
3. Configure una aplicación autenticadora escaneando el QR o introduciendo su clave manual. Confirme el código de seis dígitos.
4. Guarde los ocho códigos de recuperación en un lugar privado. No envíe capturas del QR ni de estos códigos.
5. Pulse **Continuar: cambiar contraseña inicial**. Elija una contraseña individual de 15–128 caracteres. El cambio cierra las sesiones anteriores.
6. Entre con la nueva contraseña y un código MFA nuevo. Si acaba de usar un código de seis dígitos, espere a que cambie; los códigos usados se rechazan.
7. Verifique los certificados anteriores. Deben conservarse y estar disponibles según el rol.
8. Repita la preparación para las demás cuentas demo que vaya a usar. Cada una tiene contraseña y factor propios. Las cuentas creadas desde Cuentas se activan mediante un código privado temporal.

No regenere `signing.pem` ni `identity.key` ante errores. La primera protege la continuidad de firma; la segunda abre los secretos MFA ya registrados. Si falta una clave configurada, restaure su copia.

## Prueba completa

Una vez preparado el administrador:

```powershell
.\.venv\Scripts\python.exe scripts\probar_identidad.py
```

Se solicitan contraseña y código MFA. Resultado esperado: `"resultado": "OK"`. Consulte `docs/PRUEBA_PERSONA1.md` para el recorrido manual.

## Cambios de base y recuperación

- 0006: tablas de sesiones, factores, códigos, activaciones y limitación de intentos; roles adicionales y versiones de credenciales.
- 0007: guardas de identidad/roles/cuentas, unicidad sin diferencias de mayúsculas, cierre de sesiones y cambio obligatorio de las credenciales anteriores.
- No se eliminan personas, cuentas, asignaciones históricas, mediciones, certificados ni eventos. La prueba de migración 3→4 conserva el SHA-256 exacto del certificado.
- La baja de una persona termina asignaciones y revoca todas sus sesiones; la reactivación requiere volver a asignar sus funciones operativas.

La migración de guardas se declara irreversible. Volver a 3.0.0 requiere el respaldo previo y su código/configuración compatibles; no elimine tablas para forzar el retorno. No ejecute `setup_local.py` ni `docker compose down -v` para resolver un problema de actualización.
