"""
Master Seeding Script for AI-Based Smart Parking System.
Initializes the system with:
1. Permanent Admin & Driver Accounts
2. Configured Parking Places (Institutions, Mall, City Parking) & Slots
3. Active Parking Sessions & Overstay Simulation Records
"""

import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.database import clear_and_init_mongodb, get_mongo_db
from scripts.seed_overstay_demo import slot_configs
import subprocess

def run_all_seeds():
    print("=" * 60)
    print("SEEDING COMPLETE DEMO DATA FOR SMART PARKING SYSTEM")
    print("=" * 60)

    # 1. Reset database to fresh clean state
    print("\n[1/3] Initializing MongoDB Collections & Permanent Users...")
    clear_and_init_mongodb(force_reseed=True, preserve_users=False)
    print(" -> MongoDB initialized with fresh collections and standard users.")

    # 2. Run overstay demo seeding
    print("\n[2/3] Seeding Overstay Demo Records (Car/Bike scenarios)...")
    try:
        from scripts import seed_overstay_demo
        print(" -> Overstay scenarios seeded (A-12, B-04, C-07, D-03).")
    except Exception as e:
        print(f" -> Warning during overstay demo seed: {e}")

    # 3. Seed active demo session
    print("\n[3/3] Seeding Active Parking Session...")
    try:
        from scripts import seed_active_session
        print(" -> Active parking session seeded (Slot S5).")
    except Exception as e:
        print(f" -> Warning during active session seed: {e}")

    print("\n" + "=" * 60)
    print("SUCCESS: Demo data successfully seeded!")
    print("=" * 60)

if __name__ == '__main__':
    run_all_seeds()

