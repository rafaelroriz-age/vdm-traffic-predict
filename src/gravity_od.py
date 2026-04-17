"""Gravity model OD estimation - zones, trip generation, gravity distribution.
Fills gaps left by flow propagation (~30-40% of network)."""
import numpy as np
import networkx as nx
from collections import defaultdict


def identify_zones(G, min_degree=3, max_zones=300):
    """Identify traffic analysis zones from network nodes.

    Zone criteria (scored and ranked):
    - Degree >= min_degree (intersections)
    - Urban nodes (any connected edge is urban)
    - Nodes connected to federal roads
    - Nodes with observed data

    Limits to max_zones by importance score to keep O(n²) tractable.
    Returns: dict of {node_id: zone_info}
    """
    G_simple = G.to_undirected()
    candidates = []

    for node in G.nodes():
        degree = G_simple.degree(node)
        edges = list(G.edges(node, keys=True, data=True))
        if not edges:
            continue

        is_urban = any(d.get('is_urban', False) for _, _, _, d in edges)
        is_federal = any(d.get('is_federal', False) for _, _, _, d in edges)
        total_cap = sum(d.get('capacity', 0) for _, _, _, d in edges)
        has_observed = any(d.get('fixed', False) for _, _, _, d in edges)
        total_vol = sum(d.get('volume', 0) for _, _, _, d in edges
                        if not np.isnan(d.get('volume', np.nan)))

        # Importance score
        score = degree * 10 + total_cap / 1000
        if is_urban:
            score += 50
        if is_federal:
            score += 30
        if has_observed:
            score += 40
        score += total_vol / 1000

        candidates.append((node, score, {
            'degree': degree,
            'is_urban': is_urban,
            'is_federal': is_federal,
            'total_capacity': total_cap,
            'has_observed': has_observed,
            'lat': G.nodes[node].get('lat', 0),
            'lon': G.nodes[node].get('lon', 0),
        }))

    # Sort by score, take top max_zones
    candidates.sort(key=lambda x: x[1], reverse=True)
    zones = {node: info for node, score, info in candidates[:max_zones]}

    print(f"  Identified {len(zones)} zones from {G.number_of_nodes()} nodes (top by importance)")
    return zones


def trip_generation(G, zones, params=None):
    """Estimate trip production/attraction per zone.

    Production ∝ capacity × urbanization factor
    Attraction ∝ capacity × urbanization factor

    Returns: {node_id: {'production': P, 'attraction': A}}
    """
    params = params or {}
    urban_factor = params.get('urban_trip_factor', 2.0)
    federal_factor = params.get('federal_trip_factor', 1.5)
    base_rate = params.get('trip_base_rate', 0.3)

    trips = {}
    for node, info in zones.items():
        cap = info['total_capacity']
        mult = 1.0
        if info['is_urban']:
            mult *= urban_factor
        if info['is_federal']:
            mult *= federal_factor

        # Use observed volumes to anchor generation where available
        obs_vol = 0
        n_obs = 0
        for _, _, _, d in G.edges(node, keys=True, data=True):
            if d.get('fixed') and d.get('sre') != 'connection':
                obs_vol += d.get('volume', 0)
                n_obs += 1

        if n_obs > 0:
            base = obs_vol / max(n_obs, 1)
        else:
            base = cap * base_rate * mult

        trips[node] = {
            'production': base,
            'attraction': base,
        }

    # Balance: total production = total attraction
    total_p = sum(t['production'] for t in trips.values())
    total_a = sum(t['attraction'] for t in trips.values())
    if total_a > 0:
        balance = total_p / total_a
        for t in trips.values():
            t['attraction'] *= balance

    return trips


def _haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def gravity_distribution(zones, trips, params=None):
    """Gravity model: T_ij = P_i × A_j × f(c_ij) / Σ_j(A_j × f(c_ij))

    f(c) = c^(-gamma)  (power cost function)

    Returns: OD matrix as dict {(origin, dest): flow}
    """
    params = params or {}
    gamma = params.get('gravity_gamma', 1.5)
    min_dist = params.get('gravity_min_dist', 1.0)
    max_dist = params.get('gravity_max_dist', 300.0)

    zone_list = list(zones.keys())
    n = len(zone_list)

    # Cost matrix (distance)
    cost = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                cost[i, j] = min_dist
            else:
                zi, zj = zones[zone_list[i]], zones[zone_list[j]]
                d = _haversine_km(zi['lat'], zi['lon'], zj['lat'], zj['lon'])
                cost[i, j] = max(d, min_dist)

    # Impedance function
    impedance = np.power(cost, -gamma)
    impedance[cost > max_dist] = 0
    np.fill_diagonal(impedance, 0)

    # Doubly-constrained gravity
    attractions = np.array([trips[z]['attraction'] for z in zone_list])
    productions = np.array([trips[z]['production'] for z in zone_list])

    od = np.zeros((n, n))
    for i in range(n):
        denom = np.sum(attractions * impedance[i])
        if denom > 0:
            for j in range(n):
                if i != j:
                    od[i, j] = productions[i] * attractions[j] * impedance[i, j] / denom

    # Build OD dict (only significant flows)
    threshold = np.percentile(od[od > 0], 10) if np.any(od > 0) else 0
    od_dict = {}
    for i in range(n):
        for j in range(n):
            if od[i, j] > threshold:
                od_dict[(zone_list[i], zone_list[j])] = od[i, j]

    total_trips = sum(od_dict.values())
    print(f"  Gravity model: {len(od_dict)} OD pairs, {total_trips:.0f} total trips")

    return od_dict


def build_od_matrix(G, params=None):
    """Full OD estimation pipeline: zones → generation → distribution.

    Returns: zones, trips, od_dict
    """
    params = params or {}
    print("  Identifying zones...")
    zones = identify_zones(G, min_degree=params.get('zone_min_degree', 3),
                           max_zones=params.get('max_zones', 100))
    print("  Computing trip generation...")
    trips = trip_generation(G, zones, params)
    print("  Running gravity distribution...")
    od_dict = gravity_distribution(zones, trips, params)
    return zones, trips, od_dict
