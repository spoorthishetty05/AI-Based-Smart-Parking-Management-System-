import os
import sys
import json
import io
import csv
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response, session, redirect, url_for, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError

from core.database import (
    get_db_connection, init_db, ensure_permanent_admin, 
    PERMANENT_ADMINS, create_notification, ensure_notifications_table,
    ensure_users_columns, get_mongo_db, get_next_sequence, clear_and_init_mongodb
)
from core.mongo_engine import (
    get_mongo_client, get_mongo_db, get_mongo_status, sync_sqlite_to_mongodb, init_mongodb_data,
    mongo_save_user, mongo_get_user_by_email, mongo_get_user_by_id,
    mongo_update_user, mongo_delete_user, mongo_save_vehicle, mongo_delete_vehicle,
    mongo_record_login, mongo_save_reservation, mongo_update_reservation,
    mongo_update_slot, mongo_log_activity, mongo_save_overstay, mongo_update_overstay,
    mongo_search_available_slots, mongo_check_slot_available, mongo_create_booking,
    mongo_get_user_bookings, mongo_get_booking_by_id, mongo_cancel_booking,
    mongo_get_checkout_preview, mongo_exit_booking, mongo_start_parking,
    validate_booking_datetime, calculate_end_time_string, check_time_intervals_overlap
)
from routes.middleware import login_required, admin_required, verify_password_hash, get_authenticated_user_id

try:
    from core.ml_engine import (
        predict_occupancy, get_eda_metrics, train_occupancy_models, 
        get_loaded_model, get_raw_dataset_preview, get_preprocessing_info,
        train_kmeans_clusters, get_kmeans_clusters, predict_cluster_regime
    )
except ImportError:
    predict_occupancy = get_eda_metrics = train_occupancy_models = None
    get_loaded_model = get_raw_dataset_preview = get_preprocessing_info = None
    train_kmeans_clusters = get_kmeans_clusters = predict_cluster_regime = None

try:
    from core.visualization_engine import (
        get_all_matplotlib_visualizations, generate_kmeans_cluster_plot,
        generate_feature_importance_plot, generate_actual_vs_predicted_plot,
        generate_occupancy_distribution_plot
    )
except ImportError:
    get_all_matplotlib_visualizations = generate_kmeans_cluster_plot = None
    generate_feature_importance_plot = generate_actual_vs_predicted_plot = None
    generate_occupancy_distribution_plot = None

from core.recommendation_engine import recommend_slots

ai_bp = Blueprint('ai', __name__)


# AI / ML MODULE APIs
# ==========================================

@ai_bp.route('/api/ai/predict', methods=['POST'])
def api_predict_occupancy():
    """Live Occupancy Prediction using Scikit-Learn model."""
    data = request.get_json() or {}
    target_date = data.get('target_date') or data.get('date') or datetime.now().strftime('%Y-%m-%d')
    target_time = data.get('target_time') or data.get('time') or '17:00'
    weather = data.get('weather', 'Clear')
    has_event = bool(data.get('has_event', False))
    floor = data.get('floor', 'Ground Floor')

    result = predict_occupancy(target_date, target_time, weather=weather, has_event=has_event, floor=floor)
    
    # Store prediction log in db
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO predictions (target_date, target_time, floor, predicted_occupancy, traffic_level, confidence_score, model_name)
        VALUES (?, ?, ?, ?, ?, 0.94, ?)
    """, (target_date, target_time, floor, result['predicted_occupancy'], result['traffic_level'], result['model_used']))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'prediction': result})

@ai_bp.route('/api/ai/recommend', methods=['POST'])
def api_recommend_slots():
    """Intelligent Slot Recommendation ranking based on multi-factor suitability."""
    data = request.get_json() or {}
    target_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_time = data.get('time', '10:00')
    duration_hours = float(data.get('duration', 2.0))
    vehicle_type = data.get('vehicle_type', 'Car')
    floor = data.get('floor', 'All')
    lot_id = data.get('lot_id', 'all')
    preferences = data.get('preferences', [])
    top_n = int(data.get('top_n', 6))

    result = recommend_slots(
        target_date, start_time,
        duration_hours=duration_hours,
        vehicle_type=vehicle_type,
        floor=floor,
        lot_id=lot_id,
        preferences=preferences,
        top_n=top_n
    )
    return jsonify(result)

@ai_bp.route('/api/ai/eda-metrics', methods=['GET'])
def api_eda_metrics():
    """Returns exploratory data analysis metrics, model evaluation scores, and feature importances."""
    metrics = get_eda_metrics()
    return jsonify({'status': 'success', 'data': metrics})

@ai_bp.route('/api/ai/retrain', methods=['POST'])
def api_retrain_model():
    """Triggers ML model re-training and re-evaluates metrics."""
    package = train_occupancy_models()
    return jsonify({
        'status': 'success',
        'message': f"Model '{package['model_name']}' successfully retrained and deployed.",
        'metrics': package['metrics'],
        'feature_importances': package['feature_importances'],
        'trained_at': package['trained_at']
    })

# ==========================================

# ADDITIONAL AI/ML DATASET & PREPROCESSING APIs
# ==========================================

@ai_bp.route('/api/ai/dataset-preview', methods=['GET'])
def api_dataset_preview():
    """Returns top raw historical dataset records and summary stats."""
    limit = int(request.args.get('limit', 25))
    preview = get_raw_dataset_preview(limit=limit)
    return jsonify(preview)

@ai_bp.route('/api/ai/preprocessing-info', methods=['GET'])
def api_preprocessing_info():
    """Returns documentation and feature pipeline information."""
    info = get_preprocessing_info()
    return jsonify(info)

@ai_bp.route('/api/ai/models-comparison', methods=['GET'])
def api_models_comparison():
    """Returns comparative metrics of all trained regressors."""
    pkg = get_loaded_model()
    return jsonify({
        'status': 'success',
        'best_model': pkg.get('model_name', 'RandomForestRegressor'),
        'trained_at': pkg.get('trained_at', ''),
        'metrics': pkg.get('metrics', {}),
        'feature_importances': pkg.get('feature_importances', {})
    })

# ==========================================
# K-MEANS CLUSTERING & REGIME APIs
# ==========================================

@ai_bp.route('/api/ai/kmeans', methods=['GET'])
def api_kmeans_clusters():
    """Returns K-Means clustering model results, centroids, and traffic demand profiles."""
    pkg = get_kmeans_clusters()
    return jsonify({
        'status': 'success',
        'n_clusters': pkg['n_clusters'],
        'inertia': pkg['inertia'],
        'silhouette_score': pkg['silhouette_score'],
        'clusters': pkg['clusters'],
        'trained_at': pkg['trained_at']
    })

@ai_bp.route('/api/ai/kmeans/predict', methods=['POST'])
def api_kmeans_predict():
    """Classifies an operating point (hour, occupancy) into a K-Means traffic regime."""
    data = request.get_json() or {}
    hour = float(data.get('hour', 9.5))
    occupancy = float(data.get('occupancy_percentage', 50.0))
    day_of_week = int(data.get('day_of_week', 2))
    
    result = predict_cluster_regime(hour, occupancy, day_of_week=day_of_week)
    return jsonify({'status': 'success', 'result': result})

@ai_bp.route('/api/ai/kmeans/retrain', methods=['POST'])
def api_kmeans_retrain():
    """Retrains K-Means clusters with specified cluster count (default 3)."""
    data = request.get_json() or {}
    k = int(data.get('n_clusters', 3))
    pkg = train_kmeans_clusters(n_clusters=k)
    return jsonify({
        'status': 'success',
        'message': f"K-Means successfully retrained with {k} clusters.",
        'n_clusters': pkg['n_clusters'],
        'inertia': pkg['inertia'],
        'silhouette_score': pkg['silhouette_score'],
        'clusters': pkg['clusters'],
        'trained_at': pkg['trained_at']
    })

# ==========================================
# MATPLOTLIB ANALYTICS & VISUALIZATION APIs
# ==========================================

@ai_bp.route('/api/ai/matplotlib-visualizations', methods=['GET'])
def api_matplotlib_visualizations():
    """Returns all 4 high-resolution Matplotlib visualizations encoded in Base64."""
    data = get_all_matplotlib_visualizations()
    return jsonify(data)

@ai_bp.route('/api/ai/matplotlib-visualizations/<plot_type>', methods=['GET'])
def api_single_matplotlib_plot(plot_type):
    """Returns a specific Matplotlib figure by name (kmeans, features, diurnal, density)."""
    if plot_type in ('kmeans', 'kmeans_clusters'):
        img = generate_kmeans_cluster_plot()
        title = 'K-Means Traffic & Demand Regimes'
    elif plot_type in ('features', 'feature_importance'):
        img = generate_feature_importance_plot()
        title = 'Feature Importances (Random Forest)'
    elif plot_type in ('diurnal', 'actual_vs_predicted'):
        img = generate_actual_vs_predicted_plot()
        title = 'Actual vs Predicted Diurnal Curve'
    elif plot_type in ('density', 'distribution', 'occupancy_distribution'):
        img = generate_occupancy_distribution_plot()
        title = 'Occupancy Density & Distribution'
    else:
        return jsonify({'status': 'error', 'message': f"Plot '{plot_type}' not found"}), 404

    return jsonify({
        'status': 'success',
        'plot_type': plot_type,
        'title': title,
        'image': img
    })

# ==========================================
