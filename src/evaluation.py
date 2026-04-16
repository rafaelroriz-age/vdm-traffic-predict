"""Evaluation module - Spatial K-Fold CV and metrics."""
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score


def spatial_kfold_cv(model_fn, X, y, groups, n_splits=5):
    """Perform spatial K-Fold cross-validation grouped by regional.

    Args:
        model_fn: callable that returns a fitted model given (X_train, y_train)
        X: feature matrix
        y: target (log-VMD)
        groups: group labels (regional)
        n_splits: number of folds

    Returns:
        dict with metrics arrays across folds
    """
    gkf = GroupKFold(n_splits=n_splits)

    metrics = {'rmse': [], 'mae': [], 'mape': [], 'r2': []}
    oof_preds = np.zeros(len(y))

    for fold, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model = model_fn(X_train, y_train)
        preds = model.predict(X_val)
        oof_preds[val_idx] = preds

        # Metrics in original scale (exp of log-VMD)
        y_val_orig = np.exp(y_val)
        preds_orig = np.exp(preds)

        rmse = np.sqrt(mean_squared_error(y_val_orig, preds_orig))
        mae = mean_absolute_error(y_val_orig, preds_orig)
        mape = np.mean(np.abs((y_val_orig - preds_orig) / np.maximum(y_val_orig, 1))) * 100
        r2 = r2_score(y_val_orig, preds_orig)

        metrics['rmse'].append(rmse)
        metrics['mae'].append(mae)
        metrics['mape'].append(mape)
        metrics['r2'].append(r2)

    # Summary
    summary = {}
    for key, vals in metrics.items():
        summary[key] = {
            'mean': float(np.mean(vals)),
            'std': float(np.std(vals)),
            'folds': [float(v) for v in vals]
        }

    return summary, oof_preds
