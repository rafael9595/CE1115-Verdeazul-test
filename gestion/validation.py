"""Validación compartida para captura online, correcciones y sincronización."""
import re
from datetime import date
from .policy import require, DomainError

DECIMAL=re.compile(r'-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?\Z')


def text(value,minimum,maximum,label):
    require(isinstance(value,str) and minimum<=len(value.strip())<=maximum and
            not any(ord(c)<32 and c not in '\n\t' for c in value),
            f'{label}: longitud o contenido inválido.','CAMPOS',400)
    return value.strip()


def measurement_data(data):
    try: measured=date.fromisoformat(data['measured_at'])
    except (ValueError,TypeError,KeyError): raise DomainError('Fecha de medición inválida.','CAMPOS',400)
    methodology=text(data.get('methodology'),1,300,'Metodología')
    values=data.get('values')
    require(isinstance(values,list) and 1<=len(values)<=50,'Incluya de 1 a 50 valores.','CAMPOS',400)
    cleaned=[]
    for item in values:
        require(isinstance(item,dict) and set(item)=={'name','value','unit'},'Valor incompleto.','CAMPOS',400)
        name=text(item['name'],1,80,'Nombre'); unit=text(item['unit'],1,30,'Unidad')
        value=item['value']
        require(isinstance(value,str) and DECIMAL.fullmatch(value) is not None,
                'Use un decimal como texto, con punto y hasta 12 decimales.','CAMPOS',400)
        cleaned.append({'name':name,'value':value,'unit':unit})
    return {'measured_at':measured,'methodology':methodology,'values':cleaned}


def expected_revision(value,current):
    # Formularios transportan cadenas; las API también aceptan enteros positivos.
    require(type(value) is int or (isinstance(value,str) and value.isdecimal()),
            'Falta la revisión base del borrador.','VERSION',400)
    require(int(value)==current,'Los datos cambiaron. Recargue y compare antes de guardar; no se sobrescribió nada.',
            'CONFLICTO_VERSION',409)
