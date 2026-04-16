"""Feature engineering module - prepares features for ML models."""
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder


# Goiania coordinates (main traffic generator)
GOIANIA_LAT = -16.6869
GOIANIA_LON = -49.2648


def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))


def build_features(gdf):
    """Build feature matrix for ML models."""
    print("[Features] Building feature matrix...")
    df = gdf.copy()

    # Spatial features
    df['dist_to_goiania'] = haversine_km(
        df['lat_centroid'], df['lon_centroid'],
        GOIANIA_LAT, GOIANIA_LON
    )

    # GO-level features
    if 'go' in df.columns:
        go_col = 'go' if df['go'].notna().any() else 'go_vol'
        go_stats = df.groupby(go_col).agg(
            go_total_length=('extensao', 'sum'),
            go_segment_count=('sre', 'count')
        ).reset_index()
        df = df.merge(go_stats, on=go_col, how='left')

        # Relative position within GO
        go_min_km = df.groupby(go_col)['km_inicial'].transform('min')
        go_max_km = df.groupby(go_col)['km_final'].transform('max')
        km_range = (go_max_km - go_min_km).replace(0, 1)
        df['relative_position'] = (df['km_inicial'] - go_min_km) / km_range

    # Regional VMD stats (only from observed)
    observed = df[df['has_vmd']]
    regional_col = 'regional' if 'regional' in df.columns and df['regional'].notna().any() else None
    if regional_col:
        reg_stats = observed.groupby(regional_col)['vmd'].agg(['mean', 'median']).reset_index()
        reg_stats.columns = [regional_col, 'regional_mean_vmd', 'regional_median_vmd']
        df = df.merge(reg_stats, on=regional_col, how='left')

    # Encode categorical features
    cat_features = {}
    for col in ['classe', 'revest', 'situacao', 'trecho', 'jurisdicao']:
        if col not in df.columns:
            continue
        df[col] = df[col].fillna('UNKNOWN').astype(str)
        dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
        for d_col in dummies.columns:
            df[d_col] = dummies[d_col].astype(int)
        cat_features[col] = list(dummies.columns)

    # Binary features
    if 'federal' in df.columns:
        df['is_federal'] = (df['federal'].astype(str).str.lower().isin(['s', 'sim', 'true', '1'])).astype(int)
    if 'principal' in df.columns:
        df['is_principal'] = (df['principal'].astype(str).str.lower().isin(['s', 'sim', 'true', '1'])).astype(int)
    if 'perim_urb' in df.columns:
        df['is_urban'] = (df['perim_urb'].astype(str).str.lower().isin(['s', 'sim', 'true', '1'])).astype(int)

    # Define feature columns
    numeric_features = [
        'extensao', 'lat_centroid', 'lon_centroid', 'dist_to_goiania',
        'degree_centrality', 'betweenness_centrality', 'closeness_centrality',
        'is_intersection', 'neighbor_mean_vmd', 'distance_to_nearest_count',
        'go_total_length', 'go_segment_count', 'relative_position',
    ]
    if regional_col:
        numeric_features += ['regional_mean_vmd', 'regional_median_vmd']
        numeric_features.append(regional_col)

    binary_features = [c for c in ['is_federal', 'is_principal', 'is_urban'] if c in df.columns]
    encoded_features = [c for cols in cat_features.values() for c in cols]

    all_features = numeric_features + binary_features + encoded_features
    all_features = [f for f in all_features if f in df.columns]

    print(f"  Total features: {len(all_features)}")
    print(f"  Numeric: {len(numeric_features)}, Binary: {len(binary_features)}, Encoded: {len(encoded_features)}")

    return df, all_features
