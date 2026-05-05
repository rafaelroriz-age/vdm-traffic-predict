"""Build docs/data/segments.geojson and count_points.geojson from source files.

Sources:
  - Network geometry+attributes: sre_abr_2026_georef.xlsx
    * Geometry: WKT from 'geom' column (2050 rows) + JSON fallback for truncated ones (631)
    * Attributes: all network fields (classe, revest, extensao, etc.)
  - Observed VMD: volume_contagem_trafego_mv_202604161033.xlsx (813 SREs)
  - Estimated VMD fallback: data/export/segments.geojson (pipeline output)

Output:
  - docs/data/segments.geojson  — 2681 features, full geometry + all attributes
  - docs/data/count_points.geojson — 813 observed count points
"""
import json
import pandas as pd
import numpy as np
from shapely import wkt
from shapely.geometry import shape, mapping
from shapely.ops import transform
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GEOREF_FILE = BASE_DIR / "sre_abr_2026_georef.xlsx"
GEOMETRY_FILE = BASE_DIR / "data" / "export" / "SRE-GO_2026_ABR.json"
VOLUME_FILE = BASE_DIR / "volume_contagem_trafego_mv_202604161033.xlsx"
PIPELINE_GEOJSON = BASE_DIR / "data" / "export" / "segments.geojson"
OUT_SEGMENTS = BASE_DIR / "docs" / "data" / "segments.geojson"
OUT_POINTS = BASE_DIR / "docs" / "data" / "count_points.geojson"

VEHICLE_COLS = [
    'passeio', 'van', 'pickup', 'moto',
    '2cb', '3cb', '4cb', '2sb1', '2ib2',
    '2c', '3c', '4c', '4cd',
    '2s1', '2s2', '3s1', '2s3', '3s2',
    '2i2', '2i3', '2j3', '3i2', '3s3', '3i3', '3j3',
    '4r4', '2c2', '2c3', '3c2', '3c3', '3d3', '3d4', '3q4', '3q6', '3t6'
]
LIGHT_COLS = ['passeio', 'van', 'pickup']
MOTO_COL = 'moto'


def _drop_z(geom):
    return transform(lambda x, y, z=None: (x, y), geom)


def _safe(val, cast=str, default=None):
    if val is None:
        return default
    try:
        s = str(val).strip()
        if s in ('', 'nan', 'None'):
            return default
        return cast(s) if cast != str else s
    except (ValueError, TypeError):
        return default


def _round_coords(coords, prec=6):
    if isinstance(coords[0], (list, tuple)):
        return [_round_coords(c, prec) for c in coords]
    return [round(c, prec) for c in coords]


def load_volume():
    """Load volume Excel, compute total VMD per SRE (both directions summed)."""
    df = pd.read_excel(VOLUME_FILE)
    df['sre'] = df['sre'].astype(str).str.strip()

    veh_cols = [c for c in VEHICLE_COLS if c in df.columns]
    heavy_cols = [c for c in veh_cols if c not in LIGHT_COLS + [MOTO_COL]]

    df['total_veiculos'] = df[veh_cols].fillna(0).sum(axis=1)
    df['heavy'] = df[heavy_cols].fillna(0).sum(axis=1)
    df['light'] = df[[c for c in LIGHT_COLS if c in df.columns]].fillna(0).sum(axis=1)
    df['moto_v'] = df[MOTO_COL].fillna(0) if MOTO_COL in df.columns else 0

    # Total VMD per SRE: sum CRESCENTE + DECRESCENTE
    total = df.groupby('sre').agg(
        vmd=('vmd', 'sum'),
        vmdc=('vmdc', 'sum'),
        latitude=('latitude', 'first'),
        longitude=('longitude', 'first'),
        regional=('regional', 'first'),
        origem=('origem', 'first'),
    ).reset_index()

    # Vehicle composition fractions
    pct_df = df.groupby('sre')[['total_veiculos', 'heavy', 'light', 'moto_v']].sum().reset_index()
    pct_df['pct_heavy'] = (pct_df['heavy'] / pct_df['total_veiculos'].replace(0, np.nan)).fillna(0)
    pct_df['pct_light'] = (pct_df['light'] / pct_df['total_veiculos'].replace(0, np.nan)).fillna(0)
    pct_df['pct_moto'] = (pct_df['moto_v'] / pct_df['total_veiculos'].replace(0, np.nan)).fillna(0)

    vol = total.merge(pct_df[['sre', 'pct_heavy', 'pct_light', 'pct_moto']], on='sre')
    return {row['sre']: row for _, row in vol.iterrows()}


def load_pipeline_estimates():
    """Load estimated VMD from pipeline output as fallback for unobserved SREs."""
    if not PIPELINE_GEOJSON.exists():
        return {}
    with open(PIPELINE_GEOJSON, encoding='utf-8') as f:
        fc = json.load(f)
    est = {}
    for feat in fc['features']:
        p = feat['properties']
        sre = p.get('sre', '')
        if sre and p.get('vmd_source') not in ('observed',):
            est[sre] = {
                'vmd': p.get('vmd', 0),
                'vmd_source': p.get('vmd_source', 'estimated'),
                'capacity': p.get('capacity', 0),
                'vc_ratio': p.get('vc_ratio', 0),
                'free_flow_speed': p.get('free_flow_speed', 0),
                'pct_heavy': p.get('pct_heavy', 0),
                'pct_light': p.get('pct_light', 0),
                'pct_moto': p.get('pct_moto', 0),
            }
    return est


def build_segments():
    print("[1/4] Loading volume data (813 SREs)...")
    vol_map = load_volume()

    print("[2/4] Loading pipeline estimates (fallback for unobserved)...")
    pipe_est = load_pipeline_estimates()

    print("[3/4] Building geometry from JSON (mapshaper-simplified) + WKT fallback...")
    df = pd.read_excel(GEOREF_FILE)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()

    with open(GEOMETRY_FILE, encoding='utf-8') as f:
        gc = json.load(f)
    json_geoms = gc['geometries']

    json_count = wkt_count = skip_count = 0
    features = []

    for i, row in df.iterrows():
        geom = None
        source_label = None

        # Primary: JSON geometry by row index (mapshaper-simplified, web-optimized)
        if i < len(json_geoms):
            try:
                g = shape(json_geoms[i])
                if not g.is_empty:
                    geom = g
                    source_label = 'json'
                    json_count += 1
            except Exception:
                pass

        # Fallback: WKT from Excel (for any rows where JSON is missing/empty)
        if geom is None:
            try:
                g = wkt.loads(str(row['geom']))
                if not g.is_empty:
                    geom = _drop_z(g)
                    source_label = 'wkt'
                    wkt_count += 1
            except Exception:
                pass

        if geom is None:
            skip_count += 1
            continue

        sre = str(row.get('sre', '')).strip()
        vol = vol_map.get(sre)
        pipe = pipe_est.get(sre, {})

        # Volume data: prefer observed, fallback to pipeline estimate
        if vol is not None:
            vmd = float(vol['vmd'])
            vmdc = float(vol['vmdc'])
            vmd_source = 'observed'
            pct_heavy = float(vol['pct_heavy'])
            pct_light = float(vol['pct_light'])
            pct_moto = float(vol['pct_moto'])
        else:
            vmd = float(pipe.get('vmd', 0) or 0)
            vmdc = round(vmd * float(pipe.get('pct_heavy', 0)), 1)
            vmd_source = pipe.get('vmd_source', 'estimated') if vmd > 0 else 'estimated'
            pct_heavy = float(pipe.get('pct_heavy', 0))
            pct_light = float(pipe.get('pct_light', 0))
            pct_moto = float(pipe.get('pct_moto', 0))

        # Capacity / vc_ratio from pipeline (all sources)
        capacity = float(pipe.get('capacity', 0)) if pipe else 0
        vc_ratio = float(pipe.get('vc_ratio', 0)) if pipe else 0
        free_flow_speed = float(pipe.get('free_flow_speed', 0)) if pipe else 0

        geom_dict = mapping(geom)
        geom_dict['coordinates'] = _round_coords(geom_dict['coordinates'])

        go_raw = str(row.get('go', '')).strip()
        go_int = _safe(go_raw, int)

        features.append({
            'type': 'Feature',
            'geometry': geom_dict,
            'properties': {
                'sre': sre,
                'go': go_int,
                'classe': _safe(row.get('classe')),
                'inicio': _safe(row.get('inicio')),
                'fim': _safe(row.get('fim')),
                'km_inicial': _safe(row.get('km_inicial'), float),
                'km_final': _safe(row.get('km_final'), float),
                'extensao': _safe(row.get('extensao'), float),
                'situacao': _safe(row.get('situacao')),
                'jurisdicao': _safe(row.get('jurisdicao')),
                'revest': _safe(row.get('revest')),
                'federal': _safe(row.get('federal')),
                'principal': _safe(row.get('principal')),
                'perim_urb': _safe(row.get('perim_urb')),
                'regional': _safe(row.get('regional'), int),
                'vmd': round(vmd, 1),
                'vmdc': round(vmdc, 1),
                'vmd_source': vmd_source,
                'has_vmd': vol is not None,
                'capacity': round(capacity, 1),
                'vc_ratio': round(vc_ratio, 3),
                'free_flow_speed': round(free_flow_speed, 1),
                'pct_heavy': round(pct_heavy, 4),
                'pct_light': round(pct_light, 4),
                'pct_moto': round(pct_moto, 4),
            }
        })

    print(f"   Geometry: {json_count} JSON, {wkt_count} WKT fallback, {skip_count} skipped")
    print(f"   Volume:   {sum(1 for f in features if f['properties']['has_vmd'])} observed, "
          f"{sum(1 for f in features if not f['properties']['has_vmd'])} estimated")
    return features, vol_map


def build_count_points(features, vol_map):
    """Build count_points GeoJSON from observed features, using station GPS coords."""
    pts = []
    for f in features:
        p = f['properties']
        if not p.get('has_vmd'):
            continue

        sre = p['sre']
        vol = vol_map.get(sre)

        # Use station GPS coordinates from volume Excel (more precise than segment midpoint)
        if vol is not None and pd.notna(vol.get('latitude')) and pd.notna(vol.get('longitude')):
            lat, lon = float(vol['latitude']), float(vol['longitude'])
        else:
            # Fallback: midpoint of segment geometry
            geom = f['geometry']
            coords = geom['coordinates']
            if geom['type'] == 'LineString' and coords:
                mid = coords[len(coords) // 2]
                lon, lat = mid[0], mid[1]
            elif geom['type'] == 'MultiLineString' and coords:
                sub = coords[0]
                mid = sub[len(sub) // 2]
                lon, lat = mid[0], mid[1]
            else:
                continue

        pts.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [round(lon, 6), round(lat, 6)]},
            'properties': {
                'sre': sre,
                'go': p['go'],
                'regional': p['regional'],
                'vmd': p['vmd'],
                'vmdc': p['vmdc'],
                'pct_heavy': p['pct_heavy'],
                'pct_light': p['pct_light'],
                'pct_moto': p['pct_moto'],
            }
        })
    return pts


def main():
    print("=" * 55)
    print("Build Base GeoJSON for Web App")
    print("=" * 55)

    features, vol_map = build_segments()

    print("[4/4] Writing output files...")
    OUT_SEGMENTS.parent.mkdir(parents=True, exist_ok=True)

    seg_fc = {'type': 'FeatureCollection', 'features': features}
    with open(OUT_SEGMENTS, 'w', encoding='utf-8') as f:
        json.dump(seg_fc, f, ensure_ascii=False)
    size_mb = OUT_SEGMENTS.stat().st_size / 1024 / 1024
    print(f"   segments.geojson: {len(features)} features ({size_mb:.1f} MB)")

    pts = build_count_points(features, vol_map)
    pt_fc = {'type': 'FeatureCollection', 'features': pts}
    with open(OUT_POINTS, 'w', encoding='utf-8') as f:
        json.dump(pt_fc, f, ensure_ascii=False)
    size_kb = OUT_POINTS.stat().st_size / 1024
    print(f"   count_points.geojson: {len(pts)} points ({size_kb:.0f} KB)")

    print("\nDone.")


if __name__ == "__main__":
    main()
