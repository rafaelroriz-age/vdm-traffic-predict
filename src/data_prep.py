"""Data preparation module - loads, cleans, and merges the volume and georef datasets."""
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely import wkt
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).resolve().parent.parent
VOLUME_FILE = BASE_DIR / "volume_contagem_trafego_mv_202604161033.xlsx"
GEOREF_FILE = BASE_DIR / "sre_abr_2026_georef.xlsx"

TRUCK_COLS = [
    '2cb', '3cb', '4cb', '2sb1', '2ib2', '3sb1', '3ib2', '2sb2', '2ib3',
    '3sb2', '3ib3', '2sb3', '3sb3', '2s1', '2i1', '2s2', '2i2', '3s1',
    '3i1', '2s3', '2i3', '3s2', '3i2', '3s3', '3i3', '2j3', '3j3',
    '2t4', '3t4', '2t6', '3t6', '2b1', '3b1', '3d4', '3q4'
]
LIGHT_COLS = ['passeio', 'van', 'pickup']
MOTO_COLS = ['moto']


def load_volume():
    """Load and clean the volume/traffic count dataset."""
    df = pd.read_excel(VOLUME_FILE)
    str_cols = df.select_dtypes(include='object').columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
    return df


def load_georef():
    """Load the georef dataset and parse WKT geometry."""
    df = pd.read_excel(GEOREF_FILE)
    str_cols = df.select_dtypes(include='object').columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    geometries = []
    valid_mask = []
    for idx, geom_str in enumerate(df['geom']):
        try:
            g = wkt.loads(geom_str)
            geometries.append(g)
            valid_mask.append(True)
        except Exception:
            geometries.append(None)
            valid_mask.append(False)

    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
    gdf = gdf[valid_mask].reset_index(drop=True)
    return gdf


def aggregate_volume(df_vol):
    """Aggregate volume data by SRE: most recent year, average across directions."""
    df = df_vol.copy()

    # Keep most recent year per SRE
    most_recent = df.groupby('sre')['ano'].max().reset_index()
    most_recent.columns = ['sre', 'max_ano']
    df = df.merge(most_recent, on='sre')
    df = df[df['ano'] == df['max_ano']].drop(columns=['max_ano'])

    # Numeric columns to aggregate
    num_cols = ['vmd', 'vmdc', 'total_registros', 'n_aashto', 'n_usace',
                'latitude', 'longitude']
    vehicle_cols = [c for c in TRUCK_COLS + LIGHT_COLS + MOTO_COLS if c in df.columns]
    agg_cols = num_cols + vehicle_cols

    agg_dict = {c: 'mean' for c in agg_cols if c in df.columns}
    agg_dict['ano'] = 'first'
    agg_dict['go'] = 'first'
    agg_dict['regional'] = 'first'
    if 'classe' in df.columns:
        agg_dict['classe'] = 'first'

    df_agg = df.groupby('sre').agg(agg_dict).reset_index()

    # Vehicle mix proportions
    total = df_agg[vehicle_cols].sum(axis=1).replace(0, np.nan)
    truck_sum = df_agg[[c for c in TRUCK_COLS if c in df_agg.columns]].sum(axis=1)
    light_sum = df_agg[[c for c in LIGHT_COLS if c in df_agg.columns]].sum(axis=1)
    moto_sum = df_agg[[c for c in MOTO_COLS if c in df_agg.columns]].sum(axis=1)

    df_agg['pct_heavy'] = truck_sum / total
    df_agg['pct_light'] = light_sum / total
    df_agg['pct_moto'] = moto_sum / total
    df_agg['vmdc_ratio'] = df_agg['vmdc'] / df_agg['vmd'].replace(0, np.nan)

    return df_agg


def merge_datasets(df_vol_agg, gdf_georef):
    """Merge aggregated volume data with georef on SRE."""
    gdf = gdf_georef.copy()
    gdf = gdf.merge(df_vol_agg, on='sre', how='left', suffixes=('', '_vol'))

    # Mark observed vs prediction target
    gdf['has_vmd'] = gdf['vmd'].notna()

    # Fill latitude/longitude from georef if missing
    if 'lat_inicial' in gdf.columns:
        gdf['lat_centroid'] = (gdf['lat_inicial'] + gdf['lat_final']) / 2
        gdf['lon_centroid'] = (gdf['lon_inicial'] + gdf['lon_final']) / 2

    return gdf


def prepare_data():
    """Main data preparation pipeline. Returns merged GeoDataFrame."""
    print("[1/4] Loading volume data...")
    df_vol = load_volume()
    print(f"       {len(df_vol)} records loaded")

    print("[2/4] Loading georef data...")
    gdf_geo = load_georef()
    print(f"       {len(gdf_geo)} segments loaded")

    print("[3/4] Aggregating volume by SRE...")
    df_vol_agg = aggregate_volume(df_vol)
    print(f"       {len(df_vol_agg)} unique SREs with volume data")

    print("[4/4] Merging datasets...")
    gdf = merge_datasets(df_vol_agg, gdf_geo)
    n_observed = gdf['has_vmd'].sum()
    n_predict = (~gdf['has_vmd']).sum()
    print(f"       {n_observed} observed, {n_predict} to predict")

    return gdf


if __name__ == "__main__":
    gdf = prepare_data()
    print(f"\nFinal dataset: {len(gdf)} rows, {len(gdf.columns)} columns")
    print(f"VMD range: {gdf['vmd'].min():.0f} - {gdf['vmd'].max():.0f}")
