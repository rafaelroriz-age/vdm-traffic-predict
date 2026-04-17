"""Data preparation - loads, cleans, and prepares volume and georef datasets.
Uses simplified geometries from mapshaper JSON + attributes from Excel.
Preserves directional (CRESCENTE/DECRESCENTE) volume data for network flow analysis."""
import json
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import shape
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).resolve().parent.parent
VOLUME_FILE = BASE_DIR / "volume_contagem_trafego_mv_202604161033.xlsx"
GEOREF_FILE = BASE_DIR / "sre_abr_2026_georef.xlsx"
GEOMETRY_FILE = BASE_DIR / "data" / "export" / "SRE-GO_2026_ABR.json"


def load_volume():
    df = pd.read_excel(VOLUME_FILE)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def load_georef():
    """Load georef attributes from Excel + simplified geometries from JSON.
    Returns GeoDataFrame with all 2,681 segments."""
    df = pd.read_excel(GEOREF_FILE)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()

    # Load simplified geometries (mapshaper output, same row order as Excel)
    with open(GEOMETRY_FILE, 'r', encoding='utf-8') as f:
        gc = json.load(f)

    geometries = []
    valid = []
    for i, geom_dict in enumerate(gc['geometries']):
        try:
            geom = shape(geom_dict)
            if geom.is_empty:
                geometries.append(None)
                valid.append(False)
            else:
                geometries.append(geom)
                valid.append(True)
        except Exception:
            geometries.append(None)
            valid.append(False)

    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
    gdf = gdf[valid].reset_index(drop=True)

    # Compute centroids from geometry (more reliable than lat/lon columns)
    centroids = gdf.geometry.centroid
    gdf['lat_centroid'] = centroids.y
    gdf['lon_centroid'] = centroids.x

    # Extract start/end coords from LineString for network building
    start_coords = []
    end_coords = []
    for geom in gdf.geometry:
        coords = list(geom.coords) if geom.geom_type == 'LineString' else list(geom.geoms[0].coords)
        start_coords.append((coords[0][1], coords[0][0]))   # (lat, lon)
        end_coords.append((coords[-1][1], coords[-1][0]))    # (lat, lon)

    gdf['lat_inicial'] = [c[0] for c in start_coords]
    gdf['lon_inicial'] = [c[1] for c in start_coords]
    gdf['lat_final'] = [c[0] for c in end_coords]
    gdf['lon_final'] = [c[1] for c in end_coords]

    return gdf


def aggregate_volume_directional(df_vol):
    """Aggregate volume by (SRE, direction), keeping most recent year."""
    df = df_vol.copy()
    most_recent = df.groupby('sre')['ano'].max().reset_index()
    most_recent.columns = ['sre', 'max_ano']
    df = df.merge(most_recent, on='sre')
    df = df[df['ano'] == df['max_ano']].drop(columns=['max_ano'])

    agg_dict = {'vmd': 'mean', 'vmdc': 'mean', 'total_registros': 'mean',
                'latitude': 'first', 'longitude': 'first',
                'go': 'first', 'regional': 'first', 'ano': 'first'}
    vehicle_cols = [c for c in df.columns if c in [
        'passeio', 'van', 'pickup', 'moto', '2cb', '3cb', '4cb',
        '2sb1', '2ib2', '3sb1', '3ib2', '2sb2', '2ib3', '3sb2', '3ib3',
        '2sb3', '3sb3', '2s1', '2i1', '2s2', '2i2', '3s1', '3i1',
        '2s3', '2i3', '3s2', '3i2', '3s3', '3i3', '2j3', '3j3',
        '2t4', '3t4', '2t6', '3t6', '2b1', '3b1', '3d4', '3q4'
    ]]
    for vc in vehicle_cols:
        agg_dict[vc] = 'mean'

    df_dir = df.groupby(['sre', 'sentido']).agg(agg_dict).reset_index()
    df_total = df.groupby('sre').agg(agg_dict).reset_index()
    df_total['sentido'] = 'TOTAL'

    for d in [df_dir, df_total]:
        truck_cols = [c for c in vehicle_cols if c not in ['passeio', 'van', 'pickup', 'moto']]
        light_cols = [c for c in ['passeio', 'van', 'pickup'] if c in d.columns]
        total_v = d[vehicle_cols].sum(axis=1).replace(0, np.nan)
        d['pct_heavy'] = d[truck_cols].sum(axis=1) / total_v
        d['pct_light'] = d[light_cols].sum(axis=1) / total_v
        d['pct_moto'] = d.get('moto', 0) / total_v if 'moto' in d.columns else 0

    return df_dir, df_total


def merge_datasets(df_total, gdf_georef):
    """Merge total volume with georef. Returns gdf with observed VMD where available."""
    gdf = gdf_georef.copy()
    vol_cols = ['sre', 'vmd', 'vmdc', 'latitude', 'longitude',
                'pct_heavy', 'pct_light', 'pct_moto']
    vol_merge = df_total[[c for c in vol_cols if c in df_total.columns]].copy()
    gdf = gdf.merge(vol_merge, on='sre', how='left', suffixes=('', '_vol'))
    gdf['has_vmd'] = gdf['vmd'].notna()
    return gdf


def prepare_data():
    """Main data preparation pipeline."""
    print("[1/4] Loading volume data...")
    df_vol = load_volume()
    print(f"       {len(df_vol)} records, {df_vol['sre'].nunique()} unique SREs")

    print("[2/4] Loading georef + simplified geometries...")
    gdf_geo = load_georef()
    print(f"       {len(gdf_geo)} segments (from {GEOMETRY_FILE.name})")

    print("[3/4] Aggregating volume (directional + total)...")
    df_dir, df_total = aggregate_volume_directional(df_vol)
    print(f"       {len(df_total)} SREs with volume data")

    print("[4/4] Merging datasets...")
    gdf = merge_datasets(df_total, gdf_geo)
    n_obs = gdf['has_vmd'].sum()
    n_pred = (~gdf['has_vmd']).sum()
    print(f"       {n_obs} observed, {n_pred} to estimate")

    return gdf, df_dir, df_total


if __name__ == "__main__":
    gdf, df_dir, df_total = prepare_data()
    print(f"\nFinal: {len(gdf)} segments, VMD range: {gdf['vmd'].min():.0f} - {gdf['vmd'].max():.0f}")
