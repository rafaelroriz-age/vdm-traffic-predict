"""Main pipeline - VMD Traffic Estimation via Network Flow Approach.

3-Phase estimation:
  Phase A: Flow Propagation (conservation of flow at nodes)
  Phase B: Gravity Model + Traffic Assignment (Frank-Wolfe)
  Phase C: Calibration (differential_evolution vs observed counts)
"""
import sys
import shutil
import copy
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.data_prep import prepare_data
from src.capacity import compute_capacities
from src.network_build import build_network, assign_observed_vmd
from src.flow_propagation import propagate_flows, smooth_volumes
from src.gravity_od import build_od_matrix
from src.assignment import frank_wolfe_assignment, merge_assigned_volumes
from src.calibration import calibrate, compute_metrics
from src.export import export_all


def run_estimation(gdf, df_dir, params=None):
    """Run full estimation pipeline with given parameters.
    Returns: G, centroids, frames, zones, od_dict, metrics
    """
    params = params or {}

    # Capacity estimation
    gdf_cap = compute_capacities(gdf, params)

    # Build network
    G, centroids = build_network(gdf_cap, eps_meters=params.get('dbscan_eps', 500))
    G = assign_observed_vmd(G, df_dir)

    # Phase A: Flow Propagation
    G, frames = propagate_flows(G, max_iter=params.get('prop_max_iter', 100))
    G = smooth_volumes(G, weight=params.get('smooth_weight', 0.7))

    # Phase B: Gravity + Assignment
    zones, trips, od_dict = build_od_matrix(G, params)
    G = frank_wolfe_assignment(G, od_dict, params)
    G = merge_assigned_volumes(G)

    # Compute metrics
    metrics = compute_metrics(G)

    return G, centroids, frames, zones, od_dict, metrics, gdf_cap


def main():
    t0 = time.time()
    print("=" * 60)
    print("VMD Traffic Estimation - Network Flow Approach")
    print("=" * 60)

    # ── Data Preparation ──
    print("\n--- Data Preparation ---")
    gdf, df_dir, df_total = prepare_data()

    # ── Phase C: Calibration ──
    # We wrap the estimation in a function that calibrate() can call repeatedly
    print("\n--- Phase C: Calibration (optimizing parameters) ---")

    def run_with_params(params):
        """Run phases A+B and return metrics (used by calibrator)."""
        G, centroids, frames, zones, od_dict, metrics, _ = run_estimation(gdf, df_dir, params)
        return metrics

    # Run calibration (or skip if --no-calibrate flag)
    skip_calibrate = '--no-calibrate' in sys.argv
    if skip_calibrate:
        print("  Skipping calibration (--no-calibrate)")
        best_params = {}
    else:
        best_params, best_metrics = calibrate(run_with_params, max_iter=30)

    # ── Final Run with Best Parameters ──
    print("\n--- Final Estimation (best parameters) ---")
    G, centroids, frames, zones, od_dict, metrics, gdf_final = run_estimation(gdf, df_dir, best_params)

    # ── Coverage Summary ──
    n_total = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('sre') != 'connection')
    n_obs = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('vmd_source') == 'observed')
    n_prop = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('vmd_source') == 'propagated')
    n_assign = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('vmd_source') == 'assigned')
    n_est = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get('vmd_source') == 'estimated')

    print(f"\n  Coverage breakdown ({n_total} directed edges):")
    print(f"    Observed:   {n_obs:5d} ({100*n_obs/max(n_total,1):.1f}%)")
    print(f"    Propagated: {n_prop:5d} ({100*n_prop/max(n_total,1):.1f}%)")
    print(f"    Assigned:   {n_assign:5d} ({100*n_assign/max(n_total,1):.1f}%)")
    print(f"    Estimated:  {n_est:5d} ({100*n_est/max(n_total,1):.1f}%)")

    # ── Export ──
    print("\n--- Export ---")
    export_dir = BASE_DIR / "data" / "export"
    export_all(gdf_final, G, centroids, frames, zones, od_dict, metrics, best_params, export_dir)

    # Copy web-relevant exports to docs/data for GitHub Pages
    docs_data = BASE_DIR / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    web_files = ['segments.geojson', 'count_points.geojson', 'network_graph.json',
                 'propagation_frames.json', 'gravity_model.json', 'calibration_report.json']
    for fname in web_files:
        src = export_dir / fname
        if src.exists():
            shutil.copy2(src, docs_data / fname)
    print(f"  Copied exports to {docs_data}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"Pipeline complete! ({elapsed:.1f}s)")
    print(f"{'='*60}")

    # Final metrics
    if 'error' not in metrics:
        print(f"\n  R² = {metrics['r2']:.3f}")
        print(f"  RMSE = {metrics['rmse']:.0f}")
        print(f"  MAE = {metrics['mae']:.0f}")
        print(f"  MAPE = {metrics['mape']:.1f}%")
        print(f"  GEH < 5: {metrics['geh_pct_under_5']:.1f}%")
        print(f"  Observations: {metrics['n_observations']}")


if __name__ == "__main__":
    main()
