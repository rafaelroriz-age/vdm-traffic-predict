"""ML models module - RF, XGBoost, SOM, IDW, Ensemble."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import json
import warnings
warnings.filterwarnings('ignore')

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    from minisom import MiniSom
    HAS_SOM = True
except ImportError:
    HAS_SOM = False

from .evaluation import spatial_kfold_cv
from .spatial import idw_predict


def train_random_forest(X_train, y_train):
    """Train Random Forest pipeline."""
    pipe = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('model', RandomForestRegressor(
            n_estimators=300, max_depth=20, min_samples_leaf=5,
            max_features=0.5, random_state=42, n_jobs=-1
        ))
    ])
    pipe.fit(X_train, y_train)
    return pipe


def train_xgboost(X_train, y_train):
    """Train XGBoost pipeline."""
    pipe = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('model', XGBRegressor(
            n_estimators=500, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=42, n_jobs=-1, verbosity=0
        ))
    ])
    pipe.fit(X_train, y_train)
    return pipe


def train_gradient_boosting(X_train, y_train):
    """Fallback if XGBoost not available."""
    pipe = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('model', GradientBoostingRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, random_state=42
        ))
    ])
    pipe.fit(X_train, y_train)
    return pipe


def train_som_model(X_all, y_observed, observed_mask, som_size=10):
    """Train SOM and compute cluster-mean VMD.

    Returns: som, cluster_vmd_map, scaler, imputer
    """
    imputer = SimpleImputer(strategy='median')
    X_imp = imputer.fit_transform(X_all)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_imp)

    som = MiniSom(som_size, som_size, X_scaled.shape[1],
                  sigma=2.0, learning_rate=0.5, random_seed=42)
    som.random_weights_init(X_scaled)
    som.train_random(X_scaled, 5000)

    # Compute cluster-mean VMD from observed data
    cluster_vmd = {}
    cluster_counts = {}
    X_obs = X_scaled[observed_mask]

    for i, x in enumerate(X_obs):
        bmu = som.winner(x)
        key = bmu
        if key not in cluster_vmd:
            cluster_vmd[key] = []
        cluster_vmd[key].append(y_observed[i])

    cluster_mean = {}
    for key, vals in cluster_vmd.items():
        cluster_mean[key] = float(np.mean(vals))

    # Global mean as fallback
    global_mean = float(np.mean(y_observed))

    return som, cluster_mean, global_mean, scaler, imputer


class SOMPredictor:
    """Wrapper to make SOM usable in the evaluation framework."""
    def __init__(self, som, cluster_mean, global_mean, scaler, imputer):
        self.som = som
        self.cluster_mean = cluster_mean
        self.global_mean = global_mean
        self.scaler = scaler
        self.imputer = imputer

    def predict(self, X):
        X_imp = self.imputer.transform(X)
        X_scaled = self.scaler.transform(X_imp)
        preds = []
        for x in X_scaled:
            bmu = self.som.winner(x)
            preds.append(self.cluster_mean.get(bmu, self.global_mean))
        return np.array(preds)


def run_models(gdf, feature_cols):
    """Train all models, evaluate, and generate predictions."""
    print("\n[Models] Preparing training data...")

    observed = gdf[gdf['has_vmd']].copy()
    to_predict = gdf[~gdf['has_vmd']].copy()

    X_obs = observed[feature_cols].values.astype(float)
    y_obs = np.log(observed['vmd'].values.clip(min=1))

    # Groups for spatial CV
    if 'regional' in observed.columns:
        groups = observed['regional'].fillna(0).astype(int).values
    else:
        groups = np.zeros(len(observed), dtype=int)

    # Ensure enough groups for CV
    unique_groups = np.unique(groups)
    n_splits = min(5, len(unique_groups))
    if n_splits < 2:
        n_splits = 2
        # Create artificial groups
        groups = np.arange(len(observed)) % n_splits

    results = {}

    # Model 1: Random Forest
    print("\n[Models] Training Random Forest...")
    rf_metrics, rf_oof = spatial_kfold_cv(train_random_forest, X_obs, y_obs, groups, n_splits)
    results['Random Forest'] = rf_metrics
    print(f"  R²={rf_metrics['r2']['mean']:.3f} ± {rf_metrics['r2']['std']:.3f}")
    print(f"  RMSE={rf_metrics['rmse']['mean']:.0f} ± {rf_metrics['rmse']['std']:.0f}")

    # Model 2: XGBoost or GradientBoosting
    if HAS_XGBOOST:
        print("\n[Models] Training XGBoost...")
        xgb_metrics, xgb_oof = spatial_kfold_cv(train_xgboost, X_obs, y_obs, groups, n_splits)
        results['XGBoost'] = xgb_metrics
        model2_name = 'XGBoost'
    else:
        print("\n[Models] Training Gradient Boosting (XGBoost not available)...")
        xgb_metrics, xgb_oof = spatial_kfold_cv(train_gradient_boosting, X_obs, y_obs, groups, n_splits)
        results['Gradient Boosting'] = xgb_metrics
        model2_name = 'Gradient Boosting'
    print(f"  R²={xgb_metrics['r2']['mean']:.3f} ± {xgb_metrics['r2']['std']:.3f}")
    print(f"  RMSE={xgb_metrics['rmse']['mean']:.0f} ± {xgb_metrics['rmse']['std']:.0f}")

    # Model 3: IDW
    print("\n[Models] Training IDW...")
    train_coords = observed[['lat_centroid', 'lon_centroid']].values
    train_vmd = observed['vmd'].values

    def idw_model_fn(X_train, y_train):
        class IDWModel:
            def __init__(self, coords, values):
                self.coords = coords
                self.values = np.exp(values)  # back to original for IDW
            def predict(self, X):
                pred_coords = X[:, :2]  # assume lat/lon are first features
                # Use lat_centroid, lon_centroid indices
                preds = idw_predict(self.coords, self.values, pred_coords, power=2, k=8)
                return np.log(np.maximum(preds, 1))

        # Find lat/lon column indices
        return IDWModel(X_train[:, feature_cols.index('lat_centroid'):feature_cols.index('lon_centroid')+1]
                        if 'lat_centroid' in feature_cols else X_train[:, :2],
                        y_train)

    # Simple IDW evaluation
    lat_idx = feature_cols.index('lat_centroid') if 'lat_centroid' in feature_cols else 0
    lon_idx = feature_cols.index('lon_centroid') if 'lon_centroid' in feature_cols else 1

    class IDWModelCV:
        def __init__(self):
            self.coords = None
            self.values = None
        def fit(self, X, y):
            self.coords = X[:, [lat_idx, lon_idx]]
            self.values = np.exp(y)
            return self
        def predict(self, X):
            pred_coords = X[:, [lat_idx, lon_idx]]
            preds = idw_predict(self.coords, self.values, pred_coords, power=2, k=8)
            return np.log(np.maximum(preds, 1))

    def idw_factory(X_train, y_train):
        m = IDWModelCV()
        m.fit(X_train, y_train)
        return m

    idw_metrics, idw_oof = spatial_kfold_cv(idw_factory, X_obs, y_obs, groups, n_splits)
    results['IDW'] = idw_metrics
    print(f"  R²={idw_metrics['r2']['mean']:.3f} ± {idw_metrics['r2']['std']:.3f}")
    print(f"  RMSE={idw_metrics['rmse']['mean']:.0f} ± {idw_metrics['rmse']['std']:.0f}")

    # Model 4: SOM
    som_predictor = None
    if HAS_SOM:
        print("\n[Models] Training SOM...")
        X_all = gdf[feature_cols].values.astype(float)
        observed_mask = gdf['has_vmd'].values

        som, cluster_mean, global_mean, scaler, imputer = train_som_model(
            X_all, y_obs, observed_mask, som_size=10
        )
        som_predictor = SOMPredictor(som, cluster_mean, global_mean, scaler, imputer)

        def som_factory(X_train, y_train):
            # SOM CV: train on X_train only, use its own mask
            mask = np.ones(len(X_train), dtype=bool)
            s, cm, gm, sc, imp = train_som_model(X_train, y_train, mask, som_size=10)
            return SOMPredictor(s, cm, gm, sc, imp)

        som_metrics, som_oof = spatial_kfold_cv(som_factory, X_obs, y_obs, groups, n_splits)
        results['SOM'] = som_metrics
        print(f"  R²={som_metrics['r2']['mean']:.3f} ± {som_metrics['r2']['std']:.3f}")
        print(f"  RMSE={som_metrics['rmse']['mean']:.0f} ± {som_metrics['rmse']['std']:.0f}")

    # Select best model and train final on all data
    print("\n[Models] Selecting best model...")
    best_name = max(results.keys(), key=lambda k: results[k]['r2']['mean'])
    print(f"  Best model: {best_name} (R²={results[best_name]['r2']['mean']:.3f})")

    # Train final models on all observed data
    print("\n[Models] Training final models on all data...")
    rf_final = train_random_forest(X_obs, y_obs)
    if HAS_XGBOOST:
        xgb_final = train_xgboost(X_obs, y_obs)
    else:
        xgb_final = train_gradient_boosting(X_obs, y_obs)

    # Generate predictions for all segments
    X_all = gdf[feature_cols].values.astype(float)

    rf_preds = np.exp(rf_final.predict(X_all))
    xgb_preds = np.exp(xgb_final.predict(X_all))

    idw_all_coords = gdf[['lat_centroid', 'lon_centroid']].values
    idw_preds = idw_predict(
        observed[['lat_centroid', 'lon_centroid']].values,
        observed['vmd'].values,
        idw_all_coords, power=2, k=8
    )

    som_preds = None
    if som_predictor:
        som_preds = np.exp(som_predictor.predict(X_all))

    # Ensemble: weighted average based on CV R²
    weights = {}
    for name, m in results.items():
        r2 = max(m['r2']['mean'], 0.01)
        weights[name] = r2

    w_total = sum(weights.values())
    weights = {k: v / w_total for k, v in weights.items()}

    ensemble_preds = (
        weights.get('Random Forest', 0) * rf_preds +
        weights.get(model2_name if HAS_XGBOOST else 'Gradient Boosting', 0) * xgb_preds +
        weights.get('IDW', 0) * idw_preds
    )
    if som_preds is not None and 'SOM' in weights:
        ensemble_preds += weights['SOM'] * som_preds

    results['Ensemble'] = {
        'weights': {k: round(v, 3) for k, v in weights.items()},
        'r2': {'mean': 0, 'std': 0},  # placeholder
    }

    # Assign predictions to GeoDataFrame
    gdf = gdf.copy()
    gdf['vmd_rf'] = rf_preds
    gdf['vmd_xgb'] = xgb_preds
    gdf['vmd_idw'] = idw_preds
    if som_preds is not None:
        gdf['vmd_som'] = som_preds
    gdf['vmd_ensemble'] = ensemble_preds

    # For segments without observed VMD, use ensemble; for observed, keep original
    gdf['vmd_final'] = np.where(gdf['has_vmd'], gdf['vmd'], gdf['vmd_ensemble'])
    gdf['vmd_source'] = np.where(gdf['has_vmd'], 'observed', 'predicted')
    gdf['best_model'] = best_name

    # Confidence based on distance to nearest count and model agreement
    if som_preds is not None:
        model_std = np.std([rf_preds, xgb_preds, idw_preds, som_preds], axis=0)
    else:
        model_std = np.std([rf_preds, xgb_preds, idw_preds], axis=0)
    model_cv = model_std / np.maximum(ensemble_preds, 1)
    gdf['prediction_confidence'] = pd.cut(
        model_cv,
        bins=[-np.inf, 0.3, 0.6, np.inf],
        labels=['high', 'medium', 'low']
    ).astype(str)
    gdf.loc[gdf['has_vmd'], 'prediction_confidence'] = 'observed'

    # Feature importance from RF
    imputer = rf_final.named_steps['imputer']
    rf_model = rf_final.named_steps['model']
    importance = dict(zip(feature_cols, rf_model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15]
    results['feature_importance'] = {k: round(float(v), 4) for k, v in top_features}

    print("\n[Models] Feature importance (top 10):")
    for name, imp in top_features[:10]:
        print(f"  {name}: {imp:.4f}")

    return gdf, results
