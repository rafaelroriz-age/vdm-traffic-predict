"""Network construction - builds a NetworkX MultiDiGraph from georef data.
Uses DBSCAN to cluster endpoints into intersection nodes.
Adds GO-based connectivity for consecutive segments on the same highway."""
import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN


def _project_to_meters(lat, lon):
    """Approximate lat/lon to meters (good enough for DBSCAN clustering)."""
    lat_m = lat * 111320
    lon_m = lon * 111320 * np.cos(np.radians(lat))
    return lat_m, lon_m


def cluster_endpoints(gdf, eps_meters=500):
    """Cluster segment endpoints into nodes using DBSCAN."""
    points = []
    point_info = []

    for idx, row in gdf.iterrows():
        points.append((row['lat_inicial'], row['lon_inicial']))
        point_info.append((idx, 'start'))
        points.append((row['lat_final'], row['lon_final']))
        point_info.append((idx, 'end'))

    points_arr = np.array(points)
    projected = np.array([_project_to_meters(p[0], p[1]) for p in points_arr])

    db = DBSCAN(eps=eps_meters, min_samples=1).fit(projected)
    labels = db.labels_

    n_clusters = labels.max() + 1
    centroids = {}
    for i in range(n_clusters):
        mask = labels == i
        centroids[i] = (points_arr[mask, 0].mean(), points_arr[mask, 1].mean())

    seg_nodes = {}
    for i, (seg_idx, endpoint) in enumerate(point_info):
        seg_nodes[(seg_idx, endpoint)] = labels[i]

    return centroids, seg_nodes, n_clusters


def _force_go_connectivity(gdf, seg_nodes, centroids, G, max_gap_km=50):
    """Connect consecutive segments on the same GO road.
    This ensures highway continuity even when DBSCAN doesn't merge endpoints."""
    merged = 0
    for go_val in gdf['go'].unique():
        if pd.isna(go_val) or str(go_val).strip() in ('', 'nan', '0'):
            continue
        subset = gdf[gdf['go'] == go_val].copy()
        if len(subset) < 2:
            continue

        # Sort by km_inicial to get sequential order
        km_col = 'km_inicial' if 'km_inicial' in subset.columns else None
        if km_col:
            subset = subset.sort_values(km_col)

        indices = subset.index.tolist()
        for i in range(len(indices) - 1):
            idx1 = indices[i]
            idx2 = indices[i + 1]

            # Check if they already share a node
            end_of_1 = seg_nodes[(idx1, 'end')]
            start_of_2 = seg_nodes[(idx2, 'start')]

            if end_of_1 == start_of_2:
                continue

            # Check distance
            c1 = centroids[end_of_1]
            c2 = centroids[start_of_2]
            dist_deg = np.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)
            dist_km = dist_deg * 111.32

            if dist_km < max_gap_km:
                # Merge: redirect start_of_2 node to end_of_1
                old_node = start_of_2
                new_node = end_of_1

                # Re-map edges from old_node
                edges_to_remap = list(G.in_edges(old_node, keys=True, data=True)) + \
                                 list(G.out_edges(old_node, keys=True, data=True))
                for u, v, k, d in edges_to_remap:
                    G.remove_edge(u, v, key=k)
                    new_u = new_node if u == old_node else u
                    new_v = new_node if v == old_node else v
                    if new_u != new_v:  # avoid self-loops
                        G.add_edge(new_u, new_v, key=k, **d)

                # Update seg_nodes mapping
                for key, val in seg_nodes.items():
                    if val == old_node:
                        seg_nodes[key] = new_node

                merged += 1

    if merged > 0:
        # Remove isolated nodes
        isolated = list(nx.isolates(G))
        G.remove_nodes_from(isolated)
        print(f"  GO connectivity: merged {merged} node pairs, removed {len(isolated)} isolated nodes")

    return G, seg_nodes


def build_network(gdf, eps_meters=500):
    """Build a MultiDiGraph from georef segments.
    Returns: G (MultiDiGraph), node_centroids dict
    """
    print("  Clustering endpoints (DBSCAN eps={}m)...".format(eps_meters))
    centroids, seg_nodes, n_clusters = cluster_endpoints(gdf, eps_meters)
    print(f"  {n_clusters} nodes from {len(gdf) * 2} endpoints")

    G = nx.MultiDiGraph()

    # Add nodes
    for node_id, (lat, lon) in centroids.items():
        G.add_node(node_id, lat=lat, lon=lon)

    # Add edges (bidirectional)
    for idx, row in gdf.iterrows():
        node_start = seg_nodes[(idx, 'start')]
        node_end = seg_nodes[(idx, 'end')]
        sre = row['sre']
        ext = row.get('extensao', 1.0)
        if pd.isna(ext) or ext <= 0:
            ext = 0.1

        base_attrs = {
            'sre': sre,
            'go': row.get('go', 0),
            'seg_idx': idx,
            'length_km': ext,
            'capacity': row.get('capacity', 3000),
            'free_flow_speed': row.get('free_flow_speed', 60),
            'free_flow_time': row.get('free_flow_time', ext / 60 * 60),
            'classe': str(row.get('classe', '')),
            'is_federal': str(row.get('federal', '')).lower() in ('s', 'sim'),
            'is_principal': str(row.get('principal', '')).lower() in ('s', 'sim'),
            'is_urban': str(row.get('perim_urb', '')).lower() in ('s', 'sim'),
            'surface': str(row.get('situacao', '')),
            'regional': row.get('regional', 0),
            'observed_vmd': row.get('vmd', np.nan),
            'volume': np.nan,
            'fixed': False,
        }

        if node_start == node_end:
            continue  # skip self-loops

        # CRESCENTE direction (start -> end)
        attrs_c = {**base_attrs, 'direction': 'CRESCENTE', 'edge_key': f"{sre}_C"}
        G.add_edge(node_start, node_end, key=f"{sre}_C", **attrs_c)

        # DECRESCENTE direction (end -> start)
        attrs_d = {**base_attrs, 'direction': 'DECRESCENTE', 'edge_key': f"{sre}_D"}
        G.add_edge(node_end, node_start, key=f"{sre}_D", **attrs_d)

    # Coin connections
    sre_to_idx = {row['sre']: idx for idx, row in gdf.iterrows()}
    for coin_col in ['coin_1', 'coin_2', 'coin_f1', 'coin_f2']:
        if coin_col not in gdf.columns:
            continue
        for idx, row in gdf.iterrows():
            coin_val = row.get(coin_col)
            if pd.isna(coin_val) or str(coin_val).strip() in ('', 'nan', 'None'):
                continue
            coin_sre = str(coin_val).strip()
            if coin_sre in sre_to_idx:
                other_idx = sre_to_idx[coin_sre]
                my_nodes = [seg_nodes[(idx, 'start')], seg_nodes[(idx, 'end')]]
                other_nodes = [seg_nodes[(other_idx, 'start')], seg_nodes[(other_idx, 'end')]]
                best_dist = float('inf')
                best_pair = None
                for n1 in my_nodes:
                    for n2 in other_nodes:
                        if n1 not in centroids or n2 not in centroids:
                            continue
                        c1, c2 = centroids[n1], centroids[n2]
                        d = np.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)
                        if d < best_dist:
                            best_dist = d
                            best_pair = (n1, n2)
                if best_pair and best_pair[0] != best_pair[1]:
                    G.add_edge(best_pair[0], best_pair[1], key=f"coin_{idx}_{other_idx}",
                               sre='connection', length_km=0.01, capacity=99999,
                               free_flow_time=0.001, volume=np.nan, fixed=False,
                               direction='CONN', edge_key=f"coin_{idx}_{other_idx}")

    # Force GO-based connectivity
    G, seg_nodes = _force_go_connectivity(gdf, seg_nodes, centroids, G)

    # Report connectivity
    G_undirected = G.to_undirected()
    components = list(nx.connected_components(G_undirected))
    largest = max(components, key=len) if components else set()
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  Components: {len(components)}, largest: {len(largest)} nodes ({100 * len(largest) / max(G.number_of_nodes(), 1):.1f}%)")

    return G, centroids


def assign_observed_vmd(G, df_dir):
    """Assign observed directional VMD to graph edges."""
    count = 0
    for u, v, k, data in G.edges(keys=True, data=True):
        sre = data.get('sre', '')
        direction = data.get('direction', '')
        if sre == 'connection':
            continue

        match = df_dir[(df_dir['sre'] == sre) & (df_dir['sentido'] == direction)]
        if len(match) > 0:
            data['observed_vmd'] = float(match.iloc[0]['vmd'])
            data['volume'] = float(match.iloc[0]['vmd'])
            data['fixed'] = True
            count += 1
        elif not pd.isna(data.get('observed_vmd', np.nan)):
            data['volume'] = data['observed_vmd'] / 2
            data['fixed'] = True
            count += 1

    for u, v, k, data in G.edges(keys=True, data=True):
        if data.get('fixed'):
            continue
        obs = data.get('observed_vmd', np.nan)
        if not pd.isna(obs) and obs > 0:
            data['volume'] = obs / 2
            data['fixed'] = True
            count += 1

    print(f"  Assigned observed VMD to {count} directed edges")
    return G
