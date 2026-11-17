"""Copia la configuración anterior a una extracción nueva, sin modificar el origen."""
import argparse,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from certificados.core import load_public_key,load_private_key,fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--desde',type=Path,required=True);args=parser.parse_args()
    old=args.desde.resolve()
    if old==ROOT:raise SystemExit('Ya está en la carpeta original; conserve su configuración y reconstruya los contenedores.')
    if (ROOT/'.env').exists() or (ROOT/'.local').exists():raise SystemExit('El destino ya tiene configuración. No se sobrescribe.')
    paths=['.env','.local/config.json','.local/signing.pem','.local/public.pem','.local/credenciales.txt']
    if not all((old/p).is_file() for p in paths):raise SystemExit('Falta algún archivo de configuración en la carpeta anterior.')
    private=load_private_key((old/'.local/signing.pem').read_bytes());public=load_public_key((old/'.local/public.pem').read_bytes())
    if fingerprint(private.public_key())!=fingerprint(public):raise SystemExit('El par de claves anterior no coincide.')
    cfg=json.loads((old/'.local/config.json').read_text(encoding='utf-8'))
    if cfg.get('VERDEAZUL_IDENTITY_KEY_FILE'):
        if not (old/'.local/identity.key').is_file():
            raise SystemExit('Falta la clave de identidad anterior. Recupérela antes de continuar.')
        paths.append('.local/identity.key')
        cfg['VERDEAZUL_IDENTITY_KEY_FILE']=str(ROOT/'.local/identity.key')
    cfg['VERDEAZUL_SIGNING_PRIVATE_KEY_FILE']=str(ROOT/'.local/signing.pem')
    cfg['VERDEAZUL_TRUSTED_PUBLIC_KEYS']=str(ROOT/'.local/public.pem')
    (ROOT/'.local').mkdir(mode=0o700)
    try:
        for p in paths:
            if p=='.local/config.json':continue
            shutil.copyfile(old/p,ROOT/p);(ROOT/p).chmod(0o600)
        (ROOT/'.local/config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8');(ROOT/'.local/config.json').chmod(0o600)
    except Exception:
        # Se conserva el origen; una copia parcial nunca se utiliza automáticamente.
        raise SystemExit('No se completó la copia. Conserve la carpeta original y revise el destino antes de iniciar.')
    print('Configuración y claves anteriores copiadas. El origen no se modificó.')
    print('Se mantiene el proyecto Compose verdeazul-p3-p4 y su volumen existente.')

if __name__=='__main__':main()
