# Actualizar desde la entrega de personas 3 y 4

La nueva entrega conserva el nombre de carpeta `verdeazul_integrado` y el proyecto Compose `verdeazul-p3-p4`. Así puede reutilizar el volumen de PostgreSQL y las claves de firma anteriores.

## Método recomendado: conservar la carpeta que ya utilizó

1. Mantenga su carpeta anterior; puede hacer una copia de sus archivos antes de reemplazarlos. La base de datos está en un volumen de Docker, por lo que copiar esa carpeta por sí solo no respalda la base.
2. Extraiga el nuevo ZIP en otra ubicación.
3. Copie el contenido de la nueva carpeta `verdeazul_integrado` sobre la carpeta anterior. Reemplace los archivos de código/documentación cuando Windows lo solicite. **Conserve `.env`, `.local` y `.venv`**. El ZIP no incluye ni elimina esos archivos.
4. Abra Docker Desktop. Desde PowerShell en la carpeta anterior, ejecute:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe scripts\respaldar_bd.py
docker compose up --build -d
docker compose logs --tail 40 web
```

`respaldar_bd.py` genera un archivo PostgreSQL de formato custom dentro de `respaldos/`. Es una copia local con datos y hashes de cuentas; no debe subirse al repositorio. El script maneja la salida como binario, evitando la conversión de texto de PowerShell.

5. Espere a que terminen las migraciones `0004_capture_sync` y `0005_capture_guards` y el servicio indique que escucha en 8080. Abra **http://localhost:8000** y entre con las mismas credenciales.
6. Deben seguir apareciendo sus certificados previos, además de los nuevos enlaces **Fincas**, **Propietarios**, **Asignaciones**, **Capturar medición** y **Trabajo sin conexión** según el rol.

**No ejecute `setup_local.py` para regenerar claves sobre datos anteriores ni `docker compose down -v`.** Conservar las claves públicas antiguas es necesario para verificar la evidencia histórica. El script de configuración se niega a sobrescribir una configuración existente.

## Si prefiere trabajar desde una extracción nueva

Antes de iniciar los nuevos contenedores, copie la configuración con el helper. Sustituya la ruta de ejemplo por la carpeta real anterior:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\adoptar_configuracion.py --desde "C:\ruta\anterior\verdeazul_integrado"
docker compose up -d db
.\.venv\Scripts\python.exe scripts\respaldar_bd.py
docker compose up --build -d
```

El helper copia configuración/credenciales/claves, comprueba que el par de claves coincida y ajusta las rutas locales. Se niega a reemplazar una configuración de destino existente. No modifica el origen. Utilice una sola carpeta operativa a partir de ese momento: ambas comparten el mismo nombre de proyecto y volumen de Docker.

## Qué cambia en la base

Se añaden contadores de revisión a fincas, propietarios y borradores; información de responsables de asignación; constancias de sincronización y estados de cola. Las migraciones no borran certificados, eventos, propietarios ni cuentas. Una prueba de actualización desde el ZIP anterior comprobó la conservación exacta de un certificado y los conteos históricos.

Las operaciones de edición/envío ahora requieren `expected_revision`; los clientes y formularios incluidos ya lo envían. Los consumidores externos de la API deben incorporar ese campo.

La migración de protección de historial se declara irreversible. Un regreso completo a la versión anterior requiere el código anterior y un respaldo compatible; no se debe intentar eliminar tablas de evidencia para revertir. El respaldo conserva un punto de recuperación, pero no se afirma que se haya realizado una restauración en su computadora.
