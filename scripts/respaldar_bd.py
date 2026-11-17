"""Respaldo binario de PostgreSQL local sin redirección de PowerShell."""
import argparse,os,subprocess,time
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--salida',type=Path,default=ROOT/'respaldos'/('verdeazul-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.dump'));args=p.parse_args()
    output=args.salida.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise SystemExit('Ese respaldo ya existe; no se sobrescribe.')
    for _ in range(30):
        ready=subprocess.run(['docker','compose','exec','-T','db','pg_isready','-U','verdeazul','-d','verdeazul'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if ready.returncode==0:break
        time.sleep(.5)
    else:raise SystemExit('PostgreSQL todavía no está disponible. Revise docker compose ps y vuelva a intentar.')
    temporary=output.with_suffix('.partial')
    with temporary.open('xb') as f:
        result=subprocess.run(['docker','compose','exec','-T','db','pg_dump','-U','verdeazul','-d','verdeazul','--format=custom'],cwd=ROOT,stdout=f,stderr=subprocess.PIPE)
    with temporary.open('rb') as f: header=f.read(5)
    if result.returncode or header!=b'PGDMP':
        temporary.unlink(missing_ok=True);raise SystemExit('No se completó el respaldo. Inicie el servicio db y revise Docker Desktop.')
    temporary.chmod(0o600);temporary.rename(output)
    print('Respaldo creado:',output)
    print('Contiene datos y hashes de cuentas. Consérvelo protegido y separado del código.')

if __name__=='__main__':main()
