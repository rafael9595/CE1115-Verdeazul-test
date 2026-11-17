import json
from functools import lru_cache
from pathlib import Path
from shapely.geometry import Polygon, shape
from .policy import require, DomainError


@lru_cache(maxsize=1)
def country():
    return shape(json.loads((Path(__file__).parent/'data/costa_rica.geojson').read_text())['geometry'])


def validate_geography(farm):
    try:
        require(farm.country_code == 'CR', 'País no admitido.', 'C9', 400)
        require(isinstance(farm.polygon,list) and 4 <= len(farm.polygon) <= 500,
                'Polígono incompleto.', 'C9', 400)
        coordinates=[(float(p[0]),float(p[1])) for p in farm.polygon if len(p)==2]
        require(len(coordinates)==len(farm.polygon) and coordinates[0]==coordinates[-1],
                'El polígono debe cerrar.', 'C9', 400)
        polygon=Polygon(coordinates)
        require(polygon.is_valid and not polygon.is_empty and polygon.area > 0,
                'Polígono inválido o con autointersecciones.', 'C9', 400)
        require(country().covers(polygon), 'La finca no está dentro de Costa Rica según la referencia cartográfica.', 'C9', 400)
    except (ValueError,TypeError,IndexError,OverflowError):
        raise DomainError('Coordenadas inválidas.', 'C9', 400)
