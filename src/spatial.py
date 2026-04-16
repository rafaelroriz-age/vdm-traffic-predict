"""Spatial interpolation methods - IDW."""
import numpy as np


def idw_predict(train_coords, train_values, pred_coords, power=2, k=10):
    """Inverse Distance Weighting interpolation.

    Args:
        train_coords: (N, 2) array of [lat, lon] for training points
        train_values: (N,) array of VMD values
        pred_coords: (M, 2) array of [lat, lon] for prediction points
        power: distance power parameter
        k: number of nearest neighbors to use

    Returns:
        (M,) array of predicted values
    """
    predictions = np.zeros(len(pred_coords))

    for i, coord in enumerate(pred_coords):
        dists = np.sqrt(np.sum((train_coords - coord) ** 2, axis=1))
        dists = np.maximum(dists, 1e-10)  # avoid division by zero

        # Use k nearest
        nearest_idx = np.argsort(dists)[:k]
        nearest_dists = dists[nearest_idx]
        nearest_vals = train_values[nearest_idx]

        weights = 1.0 / (nearest_dists ** power)
        predictions[i] = np.sum(weights * nearest_vals) / np.sum(weights)

    return predictions
