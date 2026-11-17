"""Genera secretos nuevos excluidos de Git. No sobrescribe la configuración existente."""
import json
import secrets
import sys
import os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from certificados.cli import generate_keys

root=Path(__file__).resolve().parent.parent
local=root/'.local'; local.mkdir(exist_ok=True,mode=0o700)
if (root/'.env').exists() or (local/'config.json').exists():
    raise SystemExit('La configuración ya existe. Se conserva; no se regeneran claves ni contraseñas.')
dbpassword=secrets.token_urlsafe(32); secret=secrets.token_urlsafe(64); password=secrets.token_urlsafe(20)
generate_keys(local/'signing.pem',local/'public.pem')
env={'POSTGRES_PASSWORD':dbpassword,'DJANGO_SECRET_KEY':secret,'DEMO_PASSWORD':password}
with (root/'.env').open('x',encoding='utf-8') as file:
    file.write('\n'.join(f'{k}={v}' for k,v in env.items())+'\n')
(root/'.env').chmod(0o600)
config={'DJANGO_LOCAL':'1','DJANGO_SECRET_KEY':secret,'DJANGO_ALLOWED_HOSTS':'localhost,127.0.0.1,testserver',
        'DATABASE_URL':f'postgresql://verdeazul:{dbpassword}@127.0.0.1:55432/verdeazul?sslmode=disable',
        'VERDEAZUL_SIGNING_PRIVATE_KEY_FILE':str(local/'signing.pem'),
        'VERDEAZUL_TRUSTED_PUBLIC_KEYS':str(local/'public.pem'),'ALLOW_DEMO':'1','DEMO_PASSWORD':password}
(local/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8'); (local/'config.json').chmod(0o600)
(local/'credenciales.txt').write_text('SOLO PRUEBAS LOCALES\nUsuarios: tecnico, verificador, administrador, auditor, propietario, gerente, supervisor, seguridad, propietario_ajeno, verificador_2\nContraseña de estas cuentas: '+password+'\n',encoding='utf-8')
(local/'credenciales.txt').chmod(0o600)
print('Configuración local creada. Credenciales: .local/credenciales.txt')
from configurar_identidad import configure
configure(root)
