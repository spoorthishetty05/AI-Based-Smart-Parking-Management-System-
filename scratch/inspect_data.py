"""
Data Inspection Utility Script.
Inspects active MongoDB collections, slots, occupancy, and machine learning dataset.
"""
import sys
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from core.database import get_mongo_db
from core.ml_engine import get_raw_dataset_preview, get_eda_metrics

if __name__ == '__main__':
    print("=" * 60)
    print("  SMART PARKING - DATA & MONGODB INSPECTOR")
    print("=" * 60)
    db = get_mongo_db()
    if db is not None:
        print(f"MongoDB Database: {db.name}")
        for coll in db.list_collection_names():
            print(f" - Collection '{coll}': {db[coll].count_documents({})} documents")
    else:
        print("MongoDB is not connected.")

    print("\nDataset & ML Metrics:")
    try:
        preview = get_raw_dataset_preview(limit=5)
        stats = preview.get('stats', {})
        print(f" - Total Samples: {stats.get('total_rows')}")
        print(f" - Average Occupancy: {stats.get('mean_occupancy')}%")
        print(f" - Max Occupancy: {stats.get('max_occupancy')}%")
        print(f" - Date Range: {stats.get('date_range')}")
        eda = get_eda_metrics()
        print(f" - Best Trained Model: {eda.get('best_model')}")
        print(f" - Weather Impact: {list(eda.get('weather_impact', {}).keys())}")
    except Exception as e:
        print(f"Error reading ML metrics: {e}")
