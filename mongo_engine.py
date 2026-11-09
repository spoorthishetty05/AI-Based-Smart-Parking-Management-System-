"""
MongoDB Engine Root Module Wrapper.
Provides direct root-level access and backward compatibility for core.mongo_engine.
"""
import sys
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(_BASE_DIR, 'core')
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from core.mongo_engine import *

if __name__ == '__main__':
    from core.database import get_mongo_db
    db = get_mongo_db()
    if db is not None:
        print("[MongoDB Connected]")
        print("Total Slots:", db.parking_slots.count_documents({}))
        print("Total Users:", db.users.count_documents({}))
        print("Total Bookings:", db.reservations.count_documents({}))
    else:
        print("[MongoDB Not Connected]")

