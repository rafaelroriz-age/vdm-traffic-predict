"""Capacity and free-flow speed estimation from road attributes.
Based on DNIT/DNER standards for Brazilian highways."""
import numpy as np

# Base capacity (vehicles/day/direction) by surface and class
CAPACITY_TABLE = {
    # (surface_group, class_group) -> base capacity
    ('PAV', 'federal'):       8000,
    ('PAV', 'Radiais'):       6000,
    ('PAV', 'Longitudinais'): 5000,
    ('PAV', 'Transversais'):  4500,
    ('PAV', 'Diagonais'):     4500,
    ('PAV', 'Ligacoes'):      3000,
    ('PAV', 'other'):         2500,
    ('IMP', 'any'):           1500,
    ('LEN', 'any'):           800,
}

# Free-flow speed (km/h)
SPEED_TABLE = {
    ('PAV', 'federal', False): 80,
    ('PAV', 'federal', True):  60,
    ('PAV', 'state', False):   70,
    ('PAV', 'state', True):    50,
    ('IMP', 'any', False):     40,
    ('IMP', 'any', True):      30,
    ('LEN', 'any', False):     25,
    ('LEN', 'any', True):      20,
}


def _surface_group(situacao, revest):
    """Map situacao/revest to surface group."""
    sit = str(situacao).upper().strip()
    rev = str(revest).upper().strip()
    if sit in ('DUP', 'PAV') or rev in ('CBUQ', 'TSD', 'TSD+MICRO', 'PF', 'AA', 'PMF', 'PMQ'):
        return 'PAV'
    elif sit in ('IMP',) or rev in ('IMP',):
        return 'IMP'
    elif sit in ('LEN',):
        return 'LEN'
    elif sit in ('EOP', 'EOD', 'PLA'):
        return 'PAV'  # under construction, assume will be paved
    return 'IMP'  # default


def _class_group(classe, is_federal):
    """Map classe to capacity lookup key."""
    if is_federal:
        return 'federal'
    c = str(classe).strip()
    for key in ['Radiais', 'Longitudinais', 'Transversais', 'Diagonais']:
        if key.lower() in c.lower():
            return key
    if 'Liga' in c or 'liga' in c:
        return 'Ligacoes'
    return 'other'


def estimate_capacity(row, params=None):
    """Estimate capacity for a road segment (vehicles/day/direction)."""
    params = params or {}
    is_federal = str(row.get('federal', '')).lower() in ('s', 'sim', 'true', '1')
    is_principal = str(row.get('principal', '')).lower() in ('s', 'sim', 'true', '1')
    is_urban = str(row.get('perim_urb', '')).lower() in ('s', 'sim', 'true', '1')
    situacao = str(row.get('situacao', ''))
    revest = str(row.get('revest', ''))
    classe = str(row.get('classe', ''))

    surf = _surface_group(situacao, revest)
    cls_key = _class_group(classe, is_federal)

    if surf == 'PAV':
        cap = CAPACITY_TABLE.get(('PAV', cls_key), CAPACITY_TABLE[('PAV', 'other')])
    elif surf == 'IMP':
        cap = CAPACITY_TABLE[('IMP', 'any')]
    else:
        cap = CAPACITY_TABLE[('LEN', 'any')]

    # Multipliers
    mult_key = f'cap_mult_{cls_key.lower()}'
    cap *= params.get(mult_key, 1.0)
    if is_urban:
        cap *= params.get('urban_cap_mult', 1.5)
    if is_principal:
        cap *= params.get('principal_cap_mult', 1.3)
    if surf != 'PAV':
        cap *= params.get('unpaved_cap_mult', 1.0)

    return max(cap, 100)


def estimate_speed(row, params=None):
    """Estimate free-flow speed (km/h)."""
    params = params or {}
    is_federal = str(row.get('federal', '')).lower() in ('s', 'sim', 'true', '1')
    is_urban = str(row.get('perim_urb', '')).lower() in ('s', 'sim', 'true', '1')
    situacao = str(row.get('situacao', ''))
    revest = str(row.get('revest', ''))

    surf = _surface_group(situacao, revest)

    if surf == 'PAV':
        road_type = 'federal' if is_federal else 'state'
        speed = SPEED_TABLE.get(('PAV', road_type, is_urban), 60)
    elif surf == 'IMP':
        speed = SPEED_TABLE.get(('IMP', 'any', is_urban), 35)
    else:
        speed = SPEED_TABLE.get(('LEN', 'any', is_urban), 20)

    speed *= params.get('speed_mult', 1.0)
    return max(speed, 10)


def compute_capacities(gdf, params=None):
    """Add capacity, speed, and free-flow time to all segments."""
    caps = []
    speeds = []
    for _, row in gdf.iterrows():
        caps.append(estimate_capacity(row, params))
        speeds.append(estimate_speed(row, params))

    gdf = gdf.copy()
    gdf['capacity'] = caps
    gdf['free_flow_speed'] = speeds
    gdf['free_flow_time'] = gdf['extensao'] / gdf['free_flow_speed'] * 60  # minutes
    gdf.loc[gdf['free_flow_time'] <= 0, 'free_flow_time'] = 0.1
    return gdf
