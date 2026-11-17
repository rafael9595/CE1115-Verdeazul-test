import os
import sys
from pathlib import Path
from test_environment import load_local_config
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
load_local_config(root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
from django.core.management import execute_from_command_line
execute_from_command_line([str(root/'manage.py'),*sys.argv[1:]])
