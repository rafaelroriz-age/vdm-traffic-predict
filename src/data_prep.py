"""Data preparation - loads, cleans, and prepares volume and georef datasets.
Geometry: parsed from 'geom' WKT column in Excel (per-row safe mapping).
For rows where WKT is truncated by Excel, falls back to SRE-GO JSON by row index.
Volume: contagem.csv filtered to origem='DPL' (15-min intervals, full 24h coverage)."""
import json
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely import wkt
from shapely.geometry import shape
from shapely.ops import transform
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).resolve().parent.parent
CONTAGEM_FILE = BASE_DIR.parent / "exports_SGP" / "contagem.csv"
GEOREF_FILE = BASE_DIR / "sre_abr_2026_georef.xlsx"
GEOMETRY_FILE = BASE_DIR / "data" / "export" / "SRE-GO_2026_ABR.json"

# All vehicle classification columns in contagem.csv
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


def load_volume():
    """Load contagem.csv, filter to DPL, compute VMD from 15-min intervals.

    DPL data has full 24h coverage (96 intervals/direction/day).
    VMD = mean daily total across all counted days (both directions combined).
    """
    df = pd.read_csv(CONTAGEM_FILE)
    df = df[df['origem'] == 'DPL'].copy()
    df['sre'] = df['codigo_rodovia'].str.strip()

    veh_cols = [c for c in VEHICLE_COLS if c in df.columns]
    df['total_veiculos'] = df[veh_cols].fillna(0).sum(axis=1)

    # Daily total per SRE (sum both directions)
    daily = df.groupby(['sre', 'data'])['total_veiculos'].sum().reset_index()
    vmd_total = daily.groupby('sre')['total_veiculos'].mean().reset_index()
    vmd_total.columns = ['sre', 'vmd']

    # Directional split for pct_heavy/light/moto
    heavy_cols = [c for c in veh_cols if c not in LIGHT_COLS + [MOTO_COL]]
    df['heavy'] = df[heavy_cols].fillna(0).sum(axis=1)
    df['light'] = df[[c for c in LIGHT_COLS if c in df.columns]].fillna(0).sum(axis=1)
    df['moto_v'] = df[MOTO_COL].fillna(0) if MOTO_COL in df.columns else 0

    pct = df.groupby('sre')[['total_veiculos', 'heavy', 'light', 'moto_v']].mean()
    pct['pct_heavy'] = pct['heavy'] / pct['total_veiculos'].replace(0, np.nan)
    pct['pct_light'] = pct['light'] / pct['total_veiculos'].replace(0, np.nan)
    pct['pct_moto'] = pct['moto_v'] / pct['total_veiculos'].replace(0, np.nan)
    pct = pct[['pct_heavy', 'pct_light', 'pct_moto']].reset_index()

    # Directional VMD for network flow
    daily_dir = df.groupby(['sre', 'sentido', 'data'])['total_veiculos'].sum().reset_index()
    df_dir = daily_dir.groupby(['sre', 'sentido'])['total_veiculos'].mean().reset_index()
    df_dir.columns = ['sre', 'sentido', 'vmd']

    df_total = vmd_total.merge(pct, on='sre', how='left')
    df_total['sentido'] = 'TOTAL'

    # Lat/lon from contagem.csv for point layer
    coords = df.groupby('sre').agg(
        latitude=('latitude_km_inicial', 'first'),
        longitude=('longitude_km_inicial', 'first'),
        regional=('regional', 'first'),
        go=('codigo_rodovia', 'first')
    ).reset_index()
    coords['go'] = coords['go'].str.extract(r'^(\d+)').astype(float)
    df_total = df_total.merge(coords, on='sre', how='left')
    df_dir = df_dir.merge(coords, on='sre', how='left')

    return df_dir, df_total


def load_georef():
    """Load georef from Excel, parse geometry from 'geom' WKT column.
    Falls back to SRE-GO JSON (by row index) when WKT is truncated by Excel.
    """
    df = pd.read_excel(GEOREF_FILE)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()

    # Load JSON fallback geometries (same row order as Excel)
    with open(GEOMETRY_FILE, 'r', encoding='utf-8') as f:
        gc = json.load(f)
    json_geoms = gc['geometries']

    def _drop_z(geom):
        return transform(lambda x, y, z=None: (x, y), geom)

    geometries = []
    valid = []
    sources = []
    for i, row in df.iterrows():
        geom = None
        source = None
        # Try WKT first (accurate, per-row mapping)
        try:
            g = wkt.loads(str(row['geom']))
            if not g.is_empty:
                geom = _drop_z(g)
                source = 'wkt'
        except Exception:
            pass

        # Fallback to JSON geometry by row index
        if geom is None and i < len(json_geoms):
            try:
                g = shape(json_geoms[i])
                if not g.is_empty:
                    geom = g
                    source = 'json'
            except Exception:
                pass

        geometries.append(geom)
        valid.append(geom is not None)
        sources.append(source)

    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
    gdf['_geom_source'] = sources
    gdf = gdf[valid].reset_index(drop=True)

    centroids = gdf.geometry.centroid
    gdf['lat_centroid'] = centroids.y
    gdf['lon_centroid'] = centroids.x

    def _first_coord(geom):
        if geom.geom_type == 'LineString':
            c = list(geom.coords)[0]
        else:
            c = list(geom.geoms[0].coords)[0]
        return c[1], c[0]  # lat, lon

    def _last_coord(geom):
        if geom.geom_type == 'LineString':
            c = list(geom.coords)[-1]
        else:
            c = list(geom.geoms[-1].coords)[-1]
        return c[1], c[0]  # lat, lon

    start = [_first_coord(g) for g in gdf.geometry]
    end = [_last_coord(g) for g in gdf.geometry]
    gdf['lat_inicial'] = [c[0] for c in start]
    gdf['lon_inicial'] = [c[1] for c in start]
    gdf['lat_final'] = [c[0] for c in end]
    gdf['lon_final'] = [c[1] for c in end]

    wkt_count = sum(1 for s in gdf['_geom_source'] if s == 'wkt')
    json_count = sum(1 for s in gdf['_geom_source'] if s == 'json')
    print(f"       Geometry sources: {wkt_count} from WKT, {json_count} from JSON fallback")
    return gdf


def merge_datasets(df_total, gdf_georef):
    """Merge total volume with georef. Returns gdf with observed VMD where available."""
    gdf = gdf_georef.copy()
    vol_cols = ['sre', 'vmd', 'pct_heavy', 'pct_light', 'pct_moto', 'latitude', 'longitude']
    vol_merge = df_total[[c for c in vol_cols if c in df_total.columns]].copy()
    gdf = gdf.merge(vol_merge, on='sre', how='left', suffixes=('', '_vol'))
    gdf['has_vmd'] = gdf['vmd'].notna()
    # vmdc: heavy fraction of VMD (for compatibility with export)
    gdf['vmdc'] = (gdf['vmd'] * gdf['pct_heavy'].fillna(0)).where(gdf['has_vmd'])
    return gdf


def prepare_data():
    """Main data preparation pipeline."""
    print("[1/3] Loading volume data from contagem.csv (origem=DPL)...")
    df_dir, df_total = load_volume()
    print(f"       {len(df_total)} SREs with DPL count data, VMD range: {df_total['vmd'].min():.0f}-{df_total['vmd'].max():.0f}")

    print("[2/3] Loading georef + WKT geometries from Excel...")
    gdf_geo = load_georef()
    print(f"       {len(gdf_geo)} segments loaded with geometry")

    print("[3/3] Merging datasets...")
    gdf = merge_datasets(df_total, gdf_geo)
    n_obs = gdf['has_vmd'].sum()
    n_pred = (~gdf['has_vmd']).sum()
    print(f"       {n_obs} observed (DPL), {n_pred} to estimate")

    return gdf, df_dir, df_total


if __name__ == "__main__":
    gdf, df_dir, df_total = prepare_data()
    print(f"\nFinal: {len(gdf)} segments, observed VMD range: {gdf['vmd'].dropna().min():.0f} - {gdf['vmd'].dropna().max():.0f}")
