"""Flow propagation - iterative flow conservation at network nodes.
At each intersection: flow_in ≈ flow_out. Observed VMDs are fixed constraints.
Unknown volumes are distributed proportional to capacity.

Uses multi-pass strategy:
  Pass 1: Strict conservation (all known on one side)
  Pass 2: Relaxed (majority known on one side)
  Pass 3: Neighbor averaging for remaining unknowns
"""
import numpy as np
import networkx as nx


def propagate_flows(G, max_iter=50, tol=1.0):
    """Iteratively propagate known volumes through the network."""
    frames = []
    n_edges = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('sre') != 'connection')

    def count_known():
        return sum(1 for _, _, _, d in G.edges(keys=True, data=True)
                   if not np.isnan(d.get('volume', np.nan)) and d.get('sre') != 'connection')

    n_known_start = count_known()
    frames.append({
        'iteration': 0,
        'coverage': n_known_start / max(n_edges, 1),
        'edges_known': n_known_start,
        'new_edges': {}
    })

    # Pass 1 & 2: Iterative propagation with decreasing strictness
    for min_known_ratio in [1.0, 0.5, 0.3]:
        for iteration in range(1, max_iter + 1):
            changed = False
            new_edges_this_iter = {}

            for node in G.nodes():
                in_edges = [(u, v, k, d) for u, v, k, d in G.in_edges(node, keys=True, data=True)
                            if d.get('sre') != 'connection']
                out_edges = [(u, v, k, d) for u, v, k, d in G.out_edges(node, keys=True, data=True)
                             if d.get('sre') != 'connection']

                known_in = [(u, v, k, d) for u, v, k, d in in_edges
                            if not np.isnan(d.get('volume', np.nan))]
                unknown_in = [(u, v, k, d) for u, v, k, d in in_edges
                              if np.isnan(d.get('volume', np.nan))]
                known_out = [(u, v, k, d) for u, v, k, d in out_edges
                             if not np.isnan(d.get('volume', np.nan))]
                unknown_out = [(u, v, k, d) for u, v, k, d in out_edges
                               if np.isnan(d.get('volume', np.nan))]

                n_in = len(in_edges)
                n_out = len(out_edges)
                sum_in = sum(d['volume'] for _, _, _, d in known_in)
                sum_out = sum(d['volume'] for _, _, _, d in known_out)

                # Check if enough edges are known on inbound side
                ratio_in = len(known_in) / max(n_in, 1)
                ratio_out = len(known_out) / max(n_out, 1)

                # Case A: Sufficient inbound known → estimate outbound
                if ratio_in >= min_known_ratio and len(unknown_out) > 0 and len(known_in) > 0:
                    # Extrapolate total inbound based on known fraction
                    est_total_in = sum_in / max(ratio_in, 0.1)
                    remaining = max(est_total_in - sum_out, est_total_in * 0.1)
                    cap_sum = sum(d.get('capacity', 3000) for _, _, _, d in unknown_out)
                    if cap_sum > 0:
                        for u, v, k, d in unknown_out:
                            if not d.get('fixed'):
                                new_vol = remaining * d.get('capacity', 3000) / cap_sum
                                new_vol = max(new_vol, 1)
                                if np.isnan(d.get('volume', np.nan)) or abs(new_vol - d.get('volume', 0)) > tol:
                                    G[u][v][k]['volume'] = new_vol
                                    new_edges_this_iter[d.get('edge_key', k)] = round(new_vol, 1)
                                    changed = True

                # Case B: Sufficient outbound known → estimate inbound
                if ratio_out >= min_known_ratio and len(unknown_in) > 0 and len(known_out) > 0:
                    est_total_out = sum_out / max(ratio_out, 0.1)
                    remaining = max(est_total_out - sum_in, est_total_out * 0.1)
                    cap_sum = sum(d.get('capacity', 3000) for _, _, _, d in unknown_in)
                    if cap_sum > 0:
                        for u, v, k, d in unknown_in:
                            if not d.get('fixed'):
                                new_vol = remaining * d.get('capacity', 3000) / cap_sum
                                new_vol = max(new_vol, 1)
                                if np.isnan(d.get('volume', np.nan)) or abs(new_vol - d.get('volume', 0)) > tol:
                                    G[u][v][k]['volume'] = new_vol
                                    new_edges_this_iter[d.get('edge_key', k)] = round(new_vol, 1)
                                    changed = True

                # Case C: Single unknown on either side
                if len(unknown_out) == 1 and len(known_in) > 0:
                    u, v, k, d = unknown_out[0]
                    if not d.get('fixed'):
                        new_vol = max(sum_in - sum_out, sum_in * 0.2, 1)
                        if np.isnan(d.get('volume', np.nan)):
                            G[u][v][k]['volume'] = new_vol
                            new_edges_this_iter[d.get('edge_key', k)] = round(new_vol, 1)
                            changed = True

                if len(unknown_in) == 1 and len(known_out) > 0:
                    u, v, k, d = unknown_in[0]
                    if not d.get('fixed'):
                        new_vol = max(sum_out - sum_in, sum_out * 0.2, 1)
                        if np.isnan(d.get('volume', np.nan)):
                            G[u][v][k]['volume'] = new_vol
                            new_edges_this_iter[d.get('edge_key', k)] = round(new_vol, 1)
                            changed = True

            n_known = count_known()
            coverage = n_known / max(n_edges, 1)

            if new_edges_this_iter:
                frames.append({
                    'iteration': len(frames),
                    'coverage': round(coverage, 4),
                    'edges_known': n_known,
                    'new_edges': new_edges_this_iter
                })

            if not changed:
                break

        n_now = count_known()
        print(f"  Pass (ratio>={min_known_ratio}): {n_now}/{n_edges} edges ({100 * n_now / max(n_edges, 1):.1f}%)")

    # Pass 3: Neighbor averaging for remaining unknowns
    _neighbor_fill(G)

    n_final = count_known()
    print(f"  Propagation final: {n_final}/{n_edges} edges ({100 * n_final / max(n_edges, 1):.1f}%)")

    return G, frames


def _neighbor_fill(G):
    """Fill remaining unknown edges using average of neighbor volumes."""
    filled = True
    passes = 0
    while filled and passes < 10:
        filled = False
        passes += 1
        for u, v, k, d in G.edges(keys=True, data=True):
            if d.get('sre') == 'connection' or not np.isnan(d.get('volume', np.nan)):
                continue

            # Collect neighbor volumes
            neighbors = []
            for _, _, _, nd in list(G.out_edges(v, keys=True, data=True)) + list(G.in_edges(u, keys=True, data=True)):
                nv = nd.get('volume', np.nan)
                if not np.isnan(nv) and nd.get('sre') != 'connection':
                    neighbors.append(nv)

            if neighbors:
                cap = d.get('capacity', 3000)
                avg_neighbor = np.mean(neighbors)
                # Scale by capacity ratio
                neighbor_caps = []
                for _, _, _, nd in list(G.out_edges(v, keys=True, data=True)) + list(G.in_edges(u, keys=True, data=True)):
                    if not np.isnan(nd.get('volume', np.nan)) and nd.get('sre') != 'connection':
                        neighbor_caps.append(nd.get('capacity', 3000))
                avg_cap = np.mean(neighbor_caps) if neighbor_caps else 3000
                scale = cap / max(avg_cap, 1)
                G[u][v][k]['volume'] = max(avg_neighbor * min(scale, 2.0), 1)
                filled = True


def smooth_volumes(G, weight=0.7):
    """Smooth propagated volumes using neighbor averaging."""
    for u, v, k, data in G.edges(keys=True, data=True):
        if data.get('fixed') or data.get('sre') == 'connection':
            continue
        vol = data.get('volume', np.nan)
        if np.isnan(vol):
            continue

        neighbors = []
        for _, _, _, nd in G.out_edges(v, keys=True, data=True):
            nv = nd.get('volume', np.nan)
            if not np.isnan(nv) and nd.get('sre') != 'connection':
                neighbors.append(nv)
        for _, _, _, nd in G.in_edges(u, keys=True, data=True):
            nv = nd.get('volume', np.nan)
            if not np.isnan(nv) and nd.get('sre') != 'connection':
                neighbors.append(nv)

        if neighbors:
            mean_neighbor = np.mean(neighbors)
            G[u][v][k]['volume'] = weight * vol + (1 - weight) * mean_neighbor

    return G
