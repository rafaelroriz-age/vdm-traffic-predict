"""Export module - generates simplified GeoJSON and metrics JSON for the web app."""
import json
import numpy as np
from pathlib import Path
from shapely.geometry import mapping
from shapely.ops import transform


def simplify_geometry(geom, tolerance=0.0005):
    """Simplify geometry with Douglas-Peucker, dropping Z coordinates."""
    if geom is None or geom.is_empty:
        return None
    # Drop Z
    geom_2d = transform(lambda x, y, z=None: (x, y), geom)
    simplified = geom_2d.simplify(tolerance, preserve_topology=True)
    return simplified


def export_geojson(gdf, output_dir):
    """Export segments as GeoJSON for the web app."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    features = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        simplified = simplify_geometry(geom)
        if simplified is None or simplified.is_empty:
            continue

        props = {
            'sre': str(row.get('sre', '')),
            'go': int(row['go']) if 'go' in row and not np.isnan(row['go']) else None,
            'regional': int(row['regional']) if 'regional' in row and not np.isnan(row['regional']) else None,
            'classe': str(row.get('classe', '')),
            'revest': str(row.get('revest', '')),
            'situacao': str(row.get('situacao', '')),
            'extensao': round(float(row.get('extensao', 0)), 2),
            'vmd': round(float(row.get('vmd_final', 0)), 1),
            'vmd_source': str(row.get('vmd_source', 'unknown')),
            'confidence': str(row.get('prediction_confidence', 'unknown')),
            'best_model': str(row.get('best_model', '')),
            'vmd_rf': round(float(row.get('vmd_rf', 0)), 1) if 'vmd_rf' in row else None,
            'vmd_xgb': round(float(row.get('vmd_xgb', 0)), 1) if 'vmd_xgb' in row else None,
            'vmd_idw': round(float(row.get('vmd_idw', 0)), 1) if 'vmd_idw' in row else None,
            'vmd_ensemble': round(float(row.get('vmd_ensemble', 0)), 1) if 'vmd_ensemble' in row else None,
        }

        # Add traffic composition if available
        for col in ['pct_heavy', 'pct_light', 'pct_moto', 'vmdc_ratio', 'n_aashto', 'n_usace']:
            if col in row and not np.isnan(row[col]) if isinstance(row.get(col), float) else False:
                props[col] = round(float(row[col]), 3)

        # Add lat/lon for points layer
        if 'latitude' in row and not (isinstance(row.get('latitude'), float) and np.isnan(row['latitude'])):
            props['latitude'] = round(float(row['latitude']), 6)
            props['longitude'] = round(float(row['longitude']), 6)

        feature = {
            'type': 'Feature',
            'geometry': mapping(simplified),
            'properties': props
        }
        features.append(feature)

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    output_path = output_dir / 'segments.geojson'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Exported {len(features)} features to {output_path} ({size_mb:.1f} MB)")

    # Also create count points GeoJSON
    observed = gdf[gdf['has_vmd']].copy()
    point_features = []
    for idx, row in observed.iterrows():
        lat = row.get('latitude')
        lon = row.get('longitude')
        if lat is None or lon is None or (isinstance(lat, float) and np.isnan(lat)):
            # Use centroid
            lat = row.get('lat_centroid', 0)
            lon = row.get('lon_centroid', 0)

        props = {
            'sre': str(row.get('sre', '')),
            'vmd': round(float(row.get('vmd', 0)), 1),
            'vmdc': round(float(row.get('vmdc', 0)), 1) if 'vmdc' in row and not np.isnan(row.get('vmdc', float('nan'))) else None,
            'go': int(row['go']) if 'go' in row and not np.isnan(row['go']) else None,
            'regional': int(row['regional']) if 'regional' in row and not np.isnan(row['regional']) else None,
        }
        for col in ['pct_heavy', 'pct_light', 'pct_moto']:
            if col in row:
                val = row[col]
                if isinstance(val, float) and not np.isnan(val):
                    props[col] = round(val, 3)

        point_features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [float(lon), float(lat)]},
            'properties': props
        })

    points_geojson = {
        'type': 'FeatureCollection',
        'features': point_features
    }
    points_path = output_dir / 'count_points.geojson'
    with open(points_path, 'w', encoding='utf-8') as f:
        json.dump(points_geojson, f, ensure_ascii=False)
    print(f"  Exported {len(point_features)} count points to {points_path}")

    return output_path, points_path


def export_metrics(results, output_dir):
    """Export model comparison metrics as JSON."""
    output_dir = Path(output_dir)
    output_path = output_dir / 'model_metrics.json'

    # Clean up for JSON serialization
    clean_results = {}
    for model_name, metrics in results.items():
        if model_name == 'feature_importance':
            clean_results[model_name] = metrics
            continue
        clean_metrics = {}
        for metric_name, vals in metrics.items():
            if isinstance(vals, dict):
                clean_metrics[metric_name] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in vals.items()
                }
            else:
                clean_metrics[metric_name] = vals
        clean_results[model_name] = clean_metrics

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(clean_results, f, indent=2, ensure_ascii=False)

    print(f"  Exported metrics to {output_path}")
    return output_path
