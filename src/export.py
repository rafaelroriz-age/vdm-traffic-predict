"""Export module - generates GeoJSON, network graph, and analysis JSON for the web app.
Supports the 7-tab storytelling visualization."""
import json
import numpy as np
import networkx as nx
from pathlib import Path
from shapely.geometry import mapping
from shapely.ops import transform


def simplify_geometry(geom, tolerance=0.0005):
    """Simplify geometry with Douglas-Peucker, dropping Z coordinates."""
    if geom is None or geom.is_empty:
        return None
    geom_2d = transform(lambda x, y, z=None: (x, y), geom)
    simplified = geom_2d.simplify(tolerance, preserve_topology=True)
    return simplified


def _safe_float(val, default=0):
    """Safely convert to float, handling NaN and None."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if np.isnan(f) else round(f, 2)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=None):
    try:
        f = float(val)
        return None if np.isnan(f) else int(f)
    except (ValueError, TypeError):
        return default


def _truncate_coords(geom_dict, precision=6):
    """Truncate coordinate precision to reduce GeoJSON size."""
    def _round_coords(coords):
        if isinstance(coords[0], (list, tuple)):
            return [_round_coords(c) for c in coords]
        return [round(c, precision) for c in coords]

    geom_dict = dict(geom_dict)
    if 'coordinates' in geom_dict:
        geom_dict['coordinates'] = _round_coords(geom_dict['coordinates'])
    return geom_dict


def export_segments_geojson(gdf, G, output_dir):
    """Export segments with full VMD data from graph back to GeoJSON."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build edge lookup: sre -> edge data (aggregate CRESCENTE + DECRESCENTE)
    edge_data = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        sre = d.get('sre', '')
        if sre == 'connection':
            continue
        if sre not in edge_data:
            edge_data[sre] = {'volumes': [], 'sources': [], 'vc_ratios': []}
        vol = d.get('volume', np.nan)
        if not np.isnan(vol):
            edge_data[sre]['volumes'].append(vol)
            edge_data[sre]['sources'].append(d.get('vmd_source', 'unknown'))
            edge_data[sre]['vc_ratios'].append(d.get('vc_ratio', 0))

    features = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        # Geometries already simplified by mapshaper — just drop Z
        geom_clean = transform(lambda x, y, z=None: (x, y), geom)

        sre = str(row.get('sre', ''))
        ed = edge_data.get(sre, {})
        vols = ed.get('volumes', [])

        # VMD = sum of directional volumes (bidirectional total)
        vmd_final = sum(vols) if vols else _safe_float(row.get('vmd', 0))
        sources = ed.get('sources', [])
        vmd_source = sources[0] if sources else ('observed' if row.get('has_vmd') else 'estimated')
        vc_ratio = max(ed.get('vc_ratios', [0])) if ed.get('vc_ratios') else 0

        props = {
            'sre': sre,
            'go': _safe_int(row.get('go')),
            'regional': _safe_int(row.get('regional')),
            'classe': str(row.get('classe', '')),
            'revest': str(row.get('revest', '')),
            'situacao': str(row.get('situacao', '')),
            'extensao': _safe_float(row.get('extensao', 0)),
            'vmd': round(vmd_final, 1),
            'vmd_source': vmd_source,
            'vc_ratio': round(vc_ratio, 3),
            'capacity': _safe_float(row.get('capacity', 0)),
            'free_flow_speed': _safe_float(row.get('free_flow_speed', 0)),
            'is_federal': str(row.get('federal', '')).lower() in ('s', 'sim'),
            'is_urban': str(row.get('perim_urb', '')).lower() in ('s', 'sim'),
        }

        for col in ['pct_heavy', 'pct_light', 'pct_moto']:
            if col in row.index:
                props[col] = _safe_float(row.get(col, 0), 0)

        features.append({
            'type': 'Feature',
            'geometry': _truncate_coords(mapping(geom_clean)),
            'properties': props
        })

    geojson = {'type': 'FeatureCollection', 'features': features}
    path = output_dir / 'segments.geojson'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  segments.geojson: {len(features)} features ({size_mb:.1f} MB)")
    return path


def export_count_points(gdf, output_dir):
    """Export observed count points as GeoJSON."""
    output_dir = Path(output_dir)
    observed = gdf[gdf['has_vmd']].copy()
    features = []

    for _, row in observed.iterrows():
        lat = row.get('latitude')
        lon = row.get('longitude')
        if lat is None or (isinstance(lat, float) and np.isnan(lat)):
            lat = row.get('lat_centroid', 0)
            lon = row.get('lon_centroid', 0)

        props = {
            'sre': str(row.get('sre', '')),
            'vmd': _safe_float(row.get('vmd', 0)),
            'vmdc': _safe_float(row.get('vmdc', 0)),
            'go': _safe_int(row.get('go')),
            'regional': _safe_int(row.get('regional')),
        }
        for col in ['pct_heavy', 'pct_light', 'pct_moto']:
            if col in row.index:
                props[col] = _safe_float(row.get(col, 0), 0)

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [float(lon), float(lat)]},
            'properties': props
        })

    geojson = {'type': 'FeatureCollection', 'features': features}
    path = output_dir / 'count_points.geojson'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f"  count_points.geojson: {len(features)} points")
    return path


def export_network_graph(G, centroids, output_dir):
    """Export network graph (nodes + edges) for web visualization."""
    output_dir = Path(output_dir)

    # Pre-compute degrees
    G_undirected = G.to_undirected()
    degree_map = dict(G_undirected.degree())

    nodes = []
    for nid, (lat, lon) in centroids.items():
        nodes.append({'id': int(nid), 'lat': round(lat, 6), 'lon': round(lon, 6),
                       'degree': degree_map.get(nid, 0)})

    edges = []
    seen = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        sre = d.get('sre', '')
        if sre == 'connection' or sre in seen:
            continue
        seen.add(sre)
        edges.append({
            'source': int(u), 'target': int(v), 'sre': sre,
            'volume': _safe_float(d.get('volume', 0)),
            'capacity': _safe_float(d.get('capacity', 0)),
        })

    data = {'nodes': nodes, 'edges': edges}
    path = output_dir / 'network_graph.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"  network_graph.json: {len(nodes)} nodes, {len(edges)} edges")
    return path


def export_propagation_frames(frames, output_dir):
    """Export propagation animation frames."""
    output_dir = Path(output_dir)
    # Limit frame data size — only keep edge keys + volumes for new edges
    clean = []
    for fr in frames:
        clean.append({
            'iteration': fr['iteration'],
            'coverage': fr['coverage'],
            'edges_known': fr['edges_known'],
            'new_count': len(fr.get('new_edges', {})),
        })

    path = output_dir / 'propagation_frames.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False)
    print(f"  propagation_frames.json: {len(clean)} frames")
    return path


def export_gravity_model(zones, od_dict, centroids, output_dir):
    """Export gravity model data (zones + top desire lines)."""
    output_dir = Path(output_dir)

    zone_list = []
    for nid, info in zones.items():
        zone_list.append({
            'id': int(nid),
            'lat': round(info['lat'], 6),
            'lon': round(info['lon'], 6),
            'degree': info['degree'],
            'is_urban': info['is_urban'],
            'is_federal': info['is_federal'],
        })

    # Top desire lines (limit for web)
    sorted_od = sorted(od_dict.items(), key=lambda x: x[1], reverse=True)[:200]
    desire_lines = []
    for (o, d), flow in sorted_od:
        if o in centroids and d in centroids:
            desire_lines.append({
                'origin': int(o), 'dest': int(d), 'flow': round(flow, 1),
                'o_lat': round(centroids[o][0], 6), 'o_lon': round(centroids[o][1], 6),
                'd_lat': round(centroids[d][0], 6), 'd_lon': round(centroids[d][1], 6),
            })

    data = {'zones': zone_list, 'desire_lines': desire_lines, 'total_od_pairs': len(od_dict)}
    path = output_dir / 'gravity_model.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"  gravity_model.json: {len(zone_list)} zones, {len(desire_lines)} desire lines")
    return path


def export_calibration_report(metrics, params, output_dir):
    """Export calibration results."""
    output_dir = Path(output_dir)

    report = {
        'metrics': {k: v for k, v in metrics.items() if k != 'scatter_data'},
        'scatter_data': metrics.get('scatter_data', []),
        'parameters': {k: round(v, 4) if isinstance(v, float) else v for k, v in params.items()},
    }

    path = output_dir / 'calibration_report.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  calibration_report.json: R²={metrics.get('r2', 0):.3f}, GEH<5={metrics.get('geh_pct_under_5', 0):.1f}%")
    return path


def export_all(gdf, G, centroids, frames, zones, od_dict, metrics, params, output_dir):
    """Master export function — generates all files for the web app."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n  Exporting data for web app...")
    export_segments_geojson(gdf, G, output_dir)
    export_count_points(gdf, output_dir)
    export_network_graph(G, centroids, output_dir)
    export_propagation_frames(frames, output_dir)
    export_gravity_model(zones, od_dict, centroids, output_dir)
    export_calibration_report(metrics, params, output_dir)
    print("  All exports complete.")
