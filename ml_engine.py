"""
ML Engine Root Module Wrapper.
Provides direct root-level access and compatibility for core.ml_engine.
"""
import sys
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(_BASE_DIR, 'core')
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from core.ml_engine import *

if __name__ == '__main__':
    from core.ml_engine import (
        train_occupancy_models,
        train_kmeans_clusters,
        predict_occupancy,
        predict_cluster_regime
    )
    pkg = train_occupancy_models()
    kmeans_pkg = train_kmeans_clusters()
    res = predict_occupancy('2026-05-24', '09:30', 'Clear', False, 'Ground Floor')
    print("Sample Prediction Result:", res)
    print("Sample K-Means Result:", predict_cluster_regime(9.5, 52.0))

