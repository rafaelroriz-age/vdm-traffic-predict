"""Calibration - optimizes model parameters against observed traffic counts.
Uses differential_evolution to minimize error between estimated and observed VMD."""
import numpy as np
from scipy.optimize import differential_evolution


def compute_geh(estimated, observed):
    """GEH statistic - standard traffic engineering validation metric.
    GEH < 5 is considered a good match for individual links."""
    e, o = np.array(estimated), np.array(observed)
    denom = np.sqrt((e + o) / 2.0)
    denom = np.where(denom == 0, 1, denom)
    return np.abs(e - o) / denom


def compute_metrics(G):
    """Compute calibration metrics comparing estimated vs observed volumes.

    Returns dict with: rmse, mae, mape, r2, geh_pct, n_observations,
                       scatter_data (for web viz)
    """
    observed = []
    estimated = []
    sre_list = []

    for u, v, k, d in G.edges(keys=True, data=True):
        if not d.get('fixed') or d.get('sre') == 'connection':
            continue
        obs = d.get('observed_vmd', np.nan)
        est = d.get('volume', np.nan)
        if np.isnan(obs) or np.isnan(est) or obs <= 0:
            continue
        observed.append(obs)
        estimated.append(est)
        sre_list.append(d.get('sre', ''))

    if len(observed) < 2:
        return {'error': 'insufficient observations'}

    obs = np.array(observed)
    est = np.array(estimated)

    residuals = est - obs
    rmse = np.sqrt(np.mean(residuals ** 2))
    mae = np.mean(np.abs(residuals))
    mape = np.mean(np.abs(residuals) / np.maximum(obs, 1)) * 100
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    r2 = 1 - ss_res / max(ss_tot, 1)

    geh = compute_geh(est, obs)
    geh_pct = np.mean(geh < 5) * 100

    scatter = [{'sre': s, 'observed': float(o), 'estimated': float(e),
                'geh': float(g), 'residual': float(e - o)}
               for s, o, e, g in zip(sre_list, obs, est, geh)]

    return {
        'rmse': float(rmse),
        'mae': float(mae),
        'mape': float(mape),
        'r2': float(r2),
        'geh_pct_under_5': float(geh_pct),
        'n_observations': len(observed),
        'mean_observed': float(np.mean(obs)),
        'mean_estimated': float(np.mean(est)),
        'scatter_data': scatter,
    }


def _objective(param_vector, param_names, run_pipeline_fn):
    """Objective function for differential_evolution.
    Minimizes weighted combination of RMSE and (100 - GEH%).
    """
    params = dict(zip(param_names, param_vector))
    try:
        metrics = run_pipeline_fn(params)
        if 'error' in metrics:
            return 1e9
        rmse_norm = metrics['rmse'] / max(metrics['mean_observed'], 1)
        geh_penalty = (100 - metrics['geh_pct_under_5']) / 100
        return rmse_norm + geh_penalty
    except Exception as e:
        print(f"    Calibration error: {e}")
        return 1e9


def calibrate(run_pipeline_fn, max_iter=50):
    """Optimize model parameters using differential evolution.

    run_pipeline_fn: function(params_dict) -> metrics_dict
    Must run the full propagation+assignment pipeline and return metrics.

    Returns: best_params dict, best_metrics dict
    """
    param_defs = [
        ('gravity_gamma',       0.5,  3.0,  1.5),
        ('bpr_alpha',           0.05, 0.50, 0.15),
        ('bpr_beta',            2.0,  6.0,  4.0),
        ('urban_trip_factor',   1.0,  4.0,  2.0),
        ('federal_trip_factor', 1.0,  3.0,  1.5),
        ('trip_base_rate',      0.1,  0.6,  0.3),
        ('urban_cap_mult',      1.0,  2.5,  1.5),
        ('principal_cap_mult',  1.0,  2.0,  1.3),
    ]

    param_names = [p[0] for p in param_defs]
    bounds = [(p[1], p[2]) for p in param_defs]
    defaults = [p[3] for p in param_defs]

    print(f"  Calibrating {len(param_names)} parameters (max {max_iter} iterations)...")

    # First evaluate defaults
    default_params = dict(zip(param_names, defaults))
    default_metrics = run_pipeline_fn(default_params)
    print(f"  Default: R²={default_metrics.get('r2', 0):.3f}, "
          f"GEH<5={default_metrics.get('geh_pct_under_5', 0):.1f}%, "
          f"RMSE={default_metrics.get('rmse', 0):.0f}")

    result = differential_evolution(
        _objective,
        bounds,
        args=(param_names, run_pipeline_fn),
        maxiter=max_iter,
        seed=42,
        tol=0.01,
        popsize=10,
        mutation=(0.5, 1.0),
        recombination=0.7,
        disp=False,
    )

    best_params = dict(zip(param_names, result.x))
    best_metrics = run_pipeline_fn(best_params)

    print(f"  Calibrated: R²={best_metrics.get('r2', 0):.3f}, "
          f"GEH<5={best_metrics.get('geh_pct_under_5', 0):.1f}%, "
          f"RMSE={best_metrics.get('rmse', 0):.0f}")
    print(f"  Best params: {best_params}")

    return best_params, best_metrics
