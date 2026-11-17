$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Comprobar-Salida([string]$paso) {
    if ($LASTEXITCODE -ne 0) { throw "Fallo en: $paso. Revise el mensaje anterior." }
}
docker info | Out-Null
Comprobar-Salida 'Docker Desktop debe estar iniciado con contenedores Linux'
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3 -c "import sys; assert sys.version_info >= (3,12), 'Se necesita Python 3.12 o posterior'"
    Comprobar-Salida 'Comprobar Python'
    py -3 -m venv .venv
    Comprobar-Salida 'Crear entorno Python'
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
Comprobar-Salida 'Instalar biblioteca de firma para las herramientas locales'
if (-not (Test-Path '.env')) {
    & .\.venv\Scripts\python.exe scripts\setup_local.py
    Comprobar-Salida 'Crear configuración local'
}
if (-not (Test-Path '.local\signing.pem')) { throw 'Falta la clave privada de esta configuración. Restaure .local; no genere una clave diferente para datos existentes.' }
& .\.venv\Scripts\python.exe scripts\configurar_identidad.py
Comprobar-Salida 'Preparar clave de identidad conservando la configuración anterior'
docker compose up --build -d
Comprobar-Salida 'Iniciar aplicación'
Write-Host 'Abra http://localhost:8000 cuando el servicio termine de iniciar.'
Write-Host 'Primera entrada: configure MFA y cambie la contraseña inicial. Guía: docs\PRUEBA_PERSONA1.md'
Write-Host 'Diagnóstico: docker compose logs --tail 40 web'
