"""
Test Suite: Machine Learning & Simulation Engines (Modules 5 & 6).
Verifies:
1. AI Occupancy prediction with weather & event features.
2. Multi-factor intelligent parking slot recommendation.
3. Exploratory Data Analysis (EDA) and model metrics.
4. Simulation clock advancement and state manipulation.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from datetime import datetime
from tests.conftest import get_test_client, create_authenticated_session, get_future_date_and_time

class TestMLAndSimulationModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()

    def tearDown(self):
        # Reset virtual simulation clock to real host PC time after tests
        try:
            self.client.post('/api/simulate/reset-clock')
        except Exception:
            pass

    def test_01_occupancy_prediction(self):
        """AI occupancy prediction should return realistic occupancy percentage and traffic level."""
        date_str, time_str, _ = get_future_date_and_time(days_ahead=2, start_hour=14)
        res = self.client.post('/api/ai/predict', json={
            'target_date': date_str,
            'target_time': time_str,
            'weather': 'Clear',
            'has_event': False,
            'floor': 'Ground Floor'
        })
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        pred = data.get('prediction', {})
        self.assertIn('predicted_occupancy', pred)
        self.assertIn('traffic_level', pred)
        self.assertIn('model_used', pred)
        self.assertGreaterEqual(pred['predicted_occupancy'], 0)
        self.assertLessEqual(pred['predicted_occupancy'], 100)

    def test_02_slot_recommendation(self):
        """Intelligent recommendation engine should rank slots by suitability score."""
        date_str, time_str, _ = get_future_date_and_time(days_ahead=1)
        res = self.client.post('/api/ai/recommend', json={
            'date': date_str,
            'time': time_str,
            'duration': 2.0,
            'vehicle_type': 'Car',
            'floor': 'All',
            'preferences': ['near_elevator', 'covered'],
            'top_n': 5
        })
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        recommendations = data.get('recommended_slots', [])
        self.assertIsInstance(recommendations, list)
        if len(recommendations) > 0:
            top_rec = recommendations[0]
            self.assertIn('slot_id', top_rec)
            self.assertIn('suitability_score', top_rec)

    def test_03_eda_metrics_and_model_evaluation(self):
        """EDA endpoint should return dataset overview and regression/classification metrics."""
        res = self.client.get('/api/ai/eda-metrics')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        metrics = data.get('data', {})
        self.assertIn('model_metrics', metrics)
        self.assertIn('total_records', metrics)

    def test_04_models_comparison_and_kmeans(self):
        """Comparison and KMeans clustering APIs should return structured evaluation data."""
        res_comp = self.client.get('/api/ai/models-comparison')
        self.assertEqual(res_comp.status_code, 200)

        res_kmeans = self.client.get('/api/ai/kmeans')
        self.assertEqual(res_kmeans.status_code, 200)
        self.assertIn('clusters', res_kmeans.json)

    def test_05_simulation_clock_step(self):
        """Simulation tick endpoint should advance virtual clock by specified minutes."""
        res = self.client.post('/api/simulate/tick', json={'minutes': 30})
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        result = data.get('result', {})
        self.assertIn('current_time', result)
        self.assertIn('formatted_time', result)

if __name__ == '__main__':
    unittest.main()
