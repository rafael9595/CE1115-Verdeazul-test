"""Añade una clave MFA local sin regenerar contraseñas ni claves de firma."""
import json
from pathlib import Path
from cryptography.fernet import Fernet


def configure(root):
    local = root / '.local'
    config_path = local / 'config.json'
    if not config_path.is_file() or not (root / '.env').is_file():
        raise SystemExit('Primero importe la configuración anterior o configure una instalación nueva.')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    key = local / 'identity.key'
    if not key.exists():
        if config.get('VERDEAZUL_IDENTITY_KEY_FILE'):
            raise SystemExit('Falta la clave de identidad existente. Recupere identity.key; no genere otra sobre datos MFA.')
        with key.open('xb') as stream:
            stream.write(Fernet.generate_key())
        key.chmod(0o600)
    Fernet(key.read_bytes().strip())
    config['VERDEAZUL_IDENTITY_KEY_FILE'] = str(key.resolve())
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    config_path.chmod(0o600)
    print('Clave de identidad preparada. Se conservan las credenciales y la clave de firma anteriores.')


if __name__ == '__main__':
    configure(Path(__file__).resolve().parent.parent)
