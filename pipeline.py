"""Main pipeline - orchestrates the full VMD estimation workflow."""
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))

from src.data_prep import prepare_data
from src.network import build_network_features
from src.features import build_features
from src.models import run_models
from src.export import export_geojson, export_metrics


def main():
    print("=" * 60)
    print("VMD Traffic Estimation Pipeline")
    print("=" * 60)

    # Phase 1: Data preparation
    print("\n--- Phase 1: Data Preparation ---")
    gdf = prepare_data()

    # Phase 2: Network analysis
    print("\n--- Phase 2: Network Analysis ---")
    gdf, G = build_network_features(gdf)

    # Phase 3: Feature engineering
    print("\n--- Phase 3: Feature Engineering ---")
    gdf, feature_cols = build_features(gdf)

    # Phase 4: ML modeling
    print("\n--- Phase 4: ML Modeling ---")
    gdf, results = run_models(gdf, feature_cols)

    # Phase 5: Export
    print("\n--- Phase 5: Export ---")
    export_dir = BASE_DIR / "data" / "export"
    export_geojson(gdf, export_dir)
    export_metrics(results, export_dir)

    # Copy to docs/data for GitHub Pages
    docs_data = BASE_DIR / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    for f in export_dir.glob("*"):
        shutil.copy2(f, docs_data / f.name)
    print(f"  Copied exports to {docs_data}")

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)

    # Print summary
    print(f"\nSegments: {len(gdf)}")
    print(f"Observed VMD: {gdf['has_vmd'].sum()}")
    print(f"Predicted VMD: {(~gdf['has_vmd']).sum()}")
    print(f"\nModel comparison:")
    for model_name, metrics in results.items():
        if model_name == 'feature_importance':
            continue
        if 'r2' in metrics and 'mean' in metrics['r2']:
            print(f"  {model_name}: R²={metrics['r2']['mean']:.3f}, RMSE={metrics.get('rmse', {}).get('mean', 0):.0f}")


if __name__ == "__main__":
    main()
