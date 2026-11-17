"""Ayuda interna de preparación: no contiene credenciales ni crea recursos externos."""
import os
import json
import secrets
from pathlib import Path


def load_local_config(root):
    local=root/'.local'
    if not (local/'config.json').is_file():
        raise RuntimeError('Ejecute scripts/setup_local.py primero.')
    os.environ.update(json.loads((local/'config.json').read_text()))
