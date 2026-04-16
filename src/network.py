"""Network analysis module - builds road graph, computes centrality and neighbor features."""
import networkx as nx
import numpy as np
import pandas as pd
from collections import defaultdict


def build_road_graph(gdf):
    """Build a NetworkX graph from road segment endpoints.

    Nodes = endpoints (lat/lon rounded to 4 decimals).
    Edges = road segments weighted by extensao (length).
    """
    G = nx.Graph()

    for idx, row in gdf.iterrows():
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        lat_f = round(row['lat_final'], 4)
        lon_f = round(row['lon_final'], 4)

        node_start = (lat_i, lon_i)
        node_end = (lat_f, lon_f)

        weight = row.get('extensao', 1.0)
        if pd.isna(weight) or weight <= 0:
            weight = 1.0

        G.add_edge(node_start, node_end,
                    sre=row['sre'],
                    weight=weight,
                    idx=idx)

    # Add cross-GO connections via coin_1, coin_2 columns
    sre_to_nodes = {}
    for idx, row in gdf.iterrows():
        sre = row['sre']
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        lat_f = round(row['lat_final'], 4)
        lon_f = round(row['lon_final'], 4)
        sre_to_nodes[sre] = ((lat_i, lon_i), (lat_f, lon_f))

    for coin_col in ['coin_1', 'coin_2', 'coin_f1', 'coin_f2']:
        if coin_col not in gdf.columns:
            continue
        for idx, row in gdf.iterrows():
            coin_val = row.get(coin_col)
            if pd.isna(coin_val) or str(coin_val).strip() in ('', 'nan', 'None'):
                continue
            coin_sre = str(coin_val).strip()
            if coin_sre in sre_to_nodes:
                my_nodes = sre_to_nodes.get(row['sre'])
                other_nodes = sre_to_nodes[coin_sre]
                if my_nodes and other_nodes:
                    # Connect nearest endpoints
                    min_dist = float('inf')
                    best_pair = None
                    for n1 in my_nodes:
                        for n2 in other_nodes:
                            d = np.sqrt((n1[0]-n2[0])**2 + (n1[1]-n2[1])**2)
                            if d < min_dist:
                                min_dist = d
                                best_pair = (n1, n2)
                    if best_pair and min_dist < 0.01:  # ~1km threshold
                        G.add_edge(best_pair[0], best_pair[1], weight=0.01, connection='coin')

    # Connect nearby disconnected nodes (within ~500m)
    from scipy.spatial import cKDTree
    nodes = list(G.nodes())
    node_arr = np.array(nodes)
    tree = cKDTree(node_arr)
    threshold = 0.005  # ~500m in degrees
    pairs = tree.query_pairs(threshold)
    added = 0
    for i, j in pairs:
        n1, n2 = nodes[i], nodes[j]
        if not G.has_edge(n1, n2):
            dist = np.sqrt((n1[0]-n2[0])**2 + (n1[1]-n2[1])**2) * 111  # approx km
            G.add_edge(n1, n2, weight=max(dist, 0.01), connection='proximity')
            added += 1

    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges (added {added} proximity edges)")
    components = list(nx.connected_components(G))
    print(f"  Connected components: {len(components)}")
    if components:
        largest = max(components, key=len)
        print(f"  Largest component: {len(largest)} nodes ({100*len(largest)/G.number_of_nodes():.1f}%)")

    return G


def compute_centrality_features(G, gdf):
    """Compute network centrality metrics for each segment."""
    print("  Computing degree centrality...")
    degree_cent = nx.degree_centrality(G)

    print("  Computing betweenness centrality (edge)...")
    edge_between = nx.edge_betweenness_centrality(G, weight='weight', k=min(500, G.number_of_nodes()))

    print("  Computing closeness centrality...")
    closeness_cent = nx.closeness_centrality(G, distance='weight')

    # Map centrality to segments
    degree_vals = []
    between_vals = []
    closeness_vals = []

    for idx, row in gdf.iterrows():
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        lat_f = round(row['lat_final'], 4)
        lon_f = round(row['lon_final'], 4)
        n_start = (lat_i, lon_i)
        n_end = (lat_f, lon_f)

        d1 = degree_cent.get(n_start, 0)
        d2 = degree_cent.get(n_end, 0)
        degree_vals.append(max(d1, d2))

        edge_key = (n_start, n_end) if (n_start, n_end) in edge_between else (n_end, n_start)
        between_vals.append(edge_between.get(edge_key, 0))

        c1 = closeness_cent.get(n_start, 0)
        c2 = closeness_cent.get(n_end, 0)
        closeness_vals.append(max(c1, c2))

    gdf = gdf.copy()
    gdf['degree_centrality'] = degree_vals
    gdf['betweenness_centrality'] = between_vals
    gdf['closeness_centrality'] = closeness_vals
    gdf['is_intersection'] = [1 if d > 0.005 else 0 for d in degree_vals]

    return gdf


def compute_neighbor_vmd(G, gdf, k=5):
    """For each segment, compute average VMD of K nearest network neighbors that have VMD."""
    sre_to_idx = {row['sre']: idx for idx, row in gdf.iterrows()}

    # Build node-to-SRE mapping
    node_to_sres = defaultdict(list)
    for idx, row in gdf.iterrows():
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        lat_f = round(row['lat_final'], 4)
        lon_f = round(row['lon_final'], 4)
        node_to_sres[(lat_i, lon_i)].append(row['sre'])
        node_to_sres[(lat_f, lon_f)].append(row['sre'])

    observed = gdf[gdf['has_vmd']].copy()
    observed_sres = set(observed['sre'])
    sre_vmd = dict(zip(observed['sre'], observed['vmd']))

    # For each node with observed VMD, store it
    node_vmd = {}
    for _, row in observed.iterrows():
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        lat_f = round(row['lat_final'], 4)
        lon_f = round(row['lon_final'], 4)
        node_vmd[(lat_i, lon_i)] = row['vmd']
        node_vmd[(lat_f, lon_f)] = row['vmd']

    neighbor_mean = []
    dist_to_nearest = []

    for idx, row in gdf.iterrows():
        lat_i = round(row['lat_inicial'], 4)
        lon_i = round(row['lon_inicial'], 4)
        n_start = (lat_i, lon_i)

        if n_start not in G:
            neighbor_mean.append(np.nan)
            dist_to_nearest.append(np.nan)
            continue

        # BFS to find nearest segments with VMD
        try:
            lengths = nx.single_source_dijkstra_path_length(G, n_start, weight='weight', cutoff=200)
        except Exception:
            neighbor_mean.append(np.nan)
            dist_to_nearest.append(np.nan)
            continue

        vmd_dists = []
        for node, dist in lengths.items():
            if node in node_vmd and dist > 0:
                vmd_dists.append((node_vmd[node], dist))

        if not vmd_dists:
            neighbor_mean.append(np.nan)
            dist_to_nearest.append(np.nan)
            continue

        vmd_dists.sort(key=lambda x: x[1])
        top_k = vmd_dists[:k]

        weights = [1.0 / max(d, 0.1) for _, d in top_k]
        values = [v for v, _ in top_k]
        w_sum = sum(weights)
        neighbor_mean.append(sum(v * w for v, w in zip(values, weights)) / w_sum)
        dist_to_nearest.append(top_k[0][1])

    gdf = gdf.copy()
    gdf['neighbor_mean_vmd'] = neighbor_mean
    gdf['distance_to_nearest_count'] = dist_to_nearest

    return gdf


def build_network_features(gdf):
    """Main network analysis pipeline."""
    print("[Network] Building road graph...")
    G = build_road_graph(gdf)

    print("[Network] Computing centrality features...")
    gdf = compute_centrality_features(G, gdf)

    print("[Network] Computing neighbor VMD features...")
    gdf = compute_neighbor_vmd(G, gdf)

    return gdf, G
