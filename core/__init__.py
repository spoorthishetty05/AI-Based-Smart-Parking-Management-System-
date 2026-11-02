"""
Core Domain Package for AI-Based Smart Parking System.
Exposes database drivers, MongoDB operational engines, ML predictive models,
recommendations, overstay monitoring, time simulation, and visualization services.
"""

import os
import sys

# Ensure core directory is on sys.path for internal relative/absolute imports
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from .database import (
    get_mongo_client, get_mongo_db, get_next_sequence, init_db,
    ensure_permanent_admin, create_notification, clear_and_init_mongodb,
    get_db_connection
)

from .mongo_engine import (
    mongo_save_user, mongo_get_user_by_email, mongo_get_user_by_id,
    mongo_update_user, mongo_delete_user, mongo_save_vehicle, mongo_delete_vehicle,
    mongo_record_login, mongo_save_reservation, mongo_update_reservation,
    mongo_update_slot, mongo_log_activity, mongo_save_overstay, mongo_update_overstay,
    mongo_search_available_slots, mongo_check_slot_available, mongo_create_booking,
    mongo_get_user_bookings, mongo_get_booking_by_id, mongo_cancel_booking,
    mongo_get_checkout_preview, mongo_exit_booking, mongo_start_parking,
    validate_booking_datetime, calculate_end_time_string, check_time_intervals_overlap
)

from .overstay_engine import (
    normalize_vehicle_type, get_vehicle_penalty_amount, calculate_overstay,
    check_and_update_overstays, get_active_overstays, get_overstay_management_data,
    get_overstay_dashboard_data, complete_parking_session, resolve_overstay,
    mark_overstay_paid, get_user_active_overstay, get_current_sim_time
)

from .ml_engine import (
    predict_occupancy, get_eda_metrics, train_occupancy_models,
    get_loaded_model, get_raw_dataset_preview, get_preprocessing_info,
    train_kmeans_clusters, get_kmeans_clusters, predict_cluster_regime
)

from .recommendation_engine import recommend_slots
from .simulation_engine import step_simulation_time, set_simulation_time, trigger_random_arrival, trigger_random_departure
from .visualization_engine import get_all_matplotlib_visualizations
from .parking_places_config import get_categories, get_all_places, get_place_by_id, sync_places_to_mongodb

