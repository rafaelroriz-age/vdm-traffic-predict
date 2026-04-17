"""Static traffic assignment - Frank-Wolfe algorithm with BPR cost function.
Assigns OD trips to shortest paths on the network, updating link volumes.
Uses batch shortest paths (single_source_dijkstra) for performance."""
import numpy as np
import networkx as nx
from collections import defaultdict


def bpr_cost(free_flow_time, volume, capacity, alpha=0.15, beta=4.0):
    """BPR link cost function: t = t0 * (1 + alpha * (V/C)^beta)"""
    if capacity <= 0:
        return free_flow_time * 10
    vc = volume / capacity
    return free_flow_time * (1.0 + alpha * (vc ** beta))


def _update_edge_costs(G, alpha, beta):
    """Recompute travel times on all edges based on current volumes."""
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get('sre') == 'connection':
            d['cost'] = 0.001
            continue
        t0 = d.get('free_flow_time', 1.0)
        vol = d.get('assigned_volume', 0)
        cap = d.get('capacity', 3000)
        d['cost'] = bpr_cost(t0, vol, cap, alpha, beta)


def _build_simple_graph(G):
    """Build a simple DiGraph with minimum costs for Dijkstra.
    For parallel edges between same nodes, keep the one with lowest cost."""
    S = nx.DiGraph()
    for u, v, k, d in G.edges(keys=True, data=True):
        cost = d.get('cost', 1.0)
        if S.has_edge(u, v):
            if cost < S[u][v]['cost']:
                S[u][v]['cost'] = cost
                S[u][v]['key'] = k
        else:
            S.add_edge(u, v, cost=cost, key=k)
    return S


def _all_or_nothing_batch(G, od_dict, weight='cost'):
    """All-or-nothing assignment using batch shortest paths from each origin."""
    link_flows = defaultdict(float)

    # Group OD pairs by origin
    origins = defaultdict(list)
    for (o, d), flow in od_dict.items():
        if flow > 0 and o != d and o in G and d in G:
            origins[o].append((d, flow))

    # Build simple graph for faster Dijkstra
    S = _build_simple_graph(G)

    failed = 0
    for orig, dest_flows in origins.items():
        if orig not in S:
            failed += len(dest_flows)
            continue
        try:
            # Single-source shortest paths from this origin
            paths = nx.single_source_dijkstra_path(S, orig, weight=weight)
            for dest, flow in dest_flows:
                if dest in paths:
                    path = paths[dest]
                    for i in range(len(path) - 1):
                        u, v = path[i], path[i + 1]
                        edge_key = S[u][v].get('key', None)
                        if edge_key:
                            link_flows[(u, v, edge_key)] += flow
                        else:
                            # Fallback: find best key in original graph
                            edges = G[u][v]
                            best_key = min(edges, key=lambda k: edges[k].get('cost', 1e9))
                            link_flows[(u, v, best_key)] += flow
                else:
                    failed += 1
        except Exception:
            failed += len(dest_flows)

    if failed > 0:
        print(f"    {failed} OD pairs had no path")
    return link_flows


def frank_wolfe_assignment(G, od_dict, params=None):
    """Frank-Wolfe (MSA) traffic assignment.

    Returns: G with 'assigned_volume' on each edge
    """
    params = params or {}
    max_iter = params.get('fw_max_iter', 15)
    alpha = params.get('bpr_alpha', 0.15)
    beta = params.get('bpr_beta', 4.0)
    convergence_gap = params.get('fw_convergence', 0.02)

    # Initialize
    for u, v, k, d in G.edges(keys=True, data=True):
        d['assigned_volume'] = 0
        d['cost'] = d.get('free_flow_time', 1.0)

    # Initial AoN
    link_flows = _all_or_nothing_batch(G, od_dict)
    for (u, v, k), flow in link_flows.items():
        G[u][v][k]['assigned_volume'] = flow

    prev_total = sum(link_flows.values())

    for iteration in range(1, max_iter + 1):
        _update_edge_costs(G, alpha, beta)

        aux_flows = _all_or_nothing_batch(G, od_dict)

        lam = 1.0 / (iteration + 1)

        current_total = 0
        for u, v, k, d in G.edges(keys=True, data=True):
            current = d.get('assigned_volume', 0)
            auxiliary = aux_flows.get((u, v, k), 0)
            new_vol = (1 - lam) * current + lam * auxiliary
            d['assigned_volume'] = new_vol
            current_total += new_vol

        if prev_total > 0:
            gap = abs(current_total - prev_total) / prev_total
            if gap < convergence_gap:
                print(f"  Assignment converged at iteration {iteration} (gap={gap:.4f})")
                break
        prev_total = current_total

    _update_edge_costs(G, alpha, beta)

    n_assigned = sum(1 for _, _, _, d in G.edges(keys=True, data=True)
                     if d.get('assigned_volume', 0) > 0 and d.get('sre') != 'connection')
    total_vol = sum(d.get('assigned_volume', 0) for _, _, _, d in G.edges(keys=True, data=True))
    print(f"  Assignment: {n_assigned} links with volume, total={total_vol:.0f}")

    return G


def merge_assigned_volumes(G):
    """Merge assigned volumes into the main volume field for edges still unknown.

    Priority: observed > propagated > assigned > estimated (capacity fallback)
    """
    filled = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get('sre') == 'connection':
            continue

        vol = d.get('volume', np.nan)
        assigned = d.get('assigned_volume', 0)
        cap = d.get('capacity', 3000)

        if np.isnan(vol) and assigned > 0:
            d['volume'] = assigned
            d['vmd_source'] = 'assigned'
            filled += 1
        elif not np.isnan(vol) and d.get('fixed'):
            d['vmd_source'] = 'observed'
        elif not np.isnan(vol):
            d['vmd_source'] = 'propagated'
        else:
            d['volume'] = cap * 0.15
            d['vmd_source'] = 'estimated'
            filled += 1

        final_vol = d.get('volume', 0)
        if not np.isnan(final_vol) and cap > 0:
            d['vc_ratio'] = final_vol / cap
        else:
            d['vc_ratio'] = 0

    print(f"  Merged assignment: filled {filled} additional edges")
    return G
