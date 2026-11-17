$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.13 o siga el README con Python 3.12.' }
}
$ProjectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $ProjectPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
& $ProjectPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas.' }
$DemoOutput = 'demo_salida_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
& $ProjectPython -m certificados demo --out $DemoOutput
if ($LASTEXITCODE -ne 0) { throw 'No se pudo completar la demostración.' }
Write-Host "Demostración finalizada. Archivos: $DemoOutput"
