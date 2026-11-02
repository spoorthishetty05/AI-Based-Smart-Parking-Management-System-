import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
"""
Migration script for Parking Lot Management (Module 2).
Adds operating_hours column and seeds City Parking – Mangaluru – 100 Slots with layout A1..A4, B1..B4, C1..C4.
"""

import sqlite3
import datetime

def migrate():
    conn = sqlite3.connect('smart_parking.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Add operating_hours column if missing
    cursor.execute("PRAGMA table_info(parking_lots)")
    cols = [r['name'] for r in cursor.fetchall()]
    if 'operating_hours' not in cols:
        print("Adding operating_hours column to parking_lots...")
        cursor.execute("ALTER TABLE parking_lots ADD COLUMN operating_hours TEXT DEFAULT '24/7 (Open Daily)'")
        conn.commit()

    # 2. Update existing lots operating hours
    cursor.execute("UPDATE parking_lots SET operating_hours = '06:00 AM - 11:00 PM' WHERE lot_name = 'Institutions'")
    cursor.execute("UPDATE parking_lots SET operating_hours = '09:00 AM - 11:30 PM' WHERE lot_name = 'Mall'")
    cursor.execute("UPDATE parking_lots SET operating_hours = '24/7 (Open Daily)' WHERE lot_name = 'Public places'")
    conn.commit()

    # 3. Check if City Parking exists, if not create it
    cursor.execute("SELECT lot_id FROM parking_lots WHERE lot_name = 'City Parking'")
    city_lot = cursor.fetchone()
    if not city_lot:
        print("Seeding City Parking – Mangaluru – 100 Slots...")
        cursor.execute("""
            INSERT INTO parking_lots (lot_name, location, total_floors, total_slots, hourly_rate, overstay_penalty_rate, operating_hours)
            VALUES ('City Parking', 'Hampankatta, Mangaluru', 2, 100, 40.0, 100.0, '24/7 (Open Daily)')
        """)
        city_lot_id = cursor.lastrowid
        conn.commit()
    else:
        city_lot_id = city_lot['lot_id']
        cursor.execute("UPDATE parking_lots SET operating_hours = '24/7 (Open Daily)', location = 'Hampankatta, Mangaluru', total_slots = 100 WHERE lot_id = ?", (city_lot_id,))
        conn.commit()

    # 4. Ensure Slots A1..A4, B1..B4, C1..C4 exist in City Parking
    sample_grid_slots = [
        # Slot Number, Floor, Zone, Slot Type, Status, Plate
        ('A1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None),
        ('A2', 'Ground Floor', 'City Central Wing', 'VIP', 'reserved', 'KA 19 AB 1234'),
        ('A3', 'Ground Floor', 'City Central Wing', 'Accessible', 'occupied', 'KA 19 XY 9876'),
        ('A4', 'Ground Floor', 'City Central Wing', 'EV', 'overstayed', 'KA 19 CD 5678'),
        
        ('B1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None),
        ('B2', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None),
        ('B3', 'Ground Floor', 'City Central Wing', 'Accessible', 'available', None),
        ('B4', 'Ground Floor', 'City Central Wing', 'VIP', 'available', None),
        
        ('C1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None),
        ('C2', 'Ground Floor', 'City Central Wing', 'EV', 'available', None),
        ('C3', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None),
        ('C4', 'Ground Floor', 'City Central Wing', 'Accessible', 'available', None),
    ]

    # Additional slots to reach 100 slots in City Parking
    # Rows A-D on Ground Floor (50 slots total: A1-A12, B1-B12, C1-C13, D1-D13)
    # Rows E-H on Upper Floor (50 slots total: E1-E12, F1-F12, G1-G13, H1-H13)
    for i in range(5, 13):
        sample_grid_slots.append((f'A{i}', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None))
        sample_grid_slots.append((f'B{i}', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None))
        sample_grid_slots.append((f'C{i}', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None))
        sample_grid_slots.append((f'D{i}', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None))
    sample_grid_slots.append(('C13', 'Ground Floor', 'City Central Wing', 'EV', 'available', None))
    sample_grid_slots.append(('D13', 'Ground Floor', 'City Central Wing', 'VIP', 'available', None))

    for i in range(1, 13):
        sample_grid_slots.append((f'E{i}', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None))
        sample_grid_slots.append((f'F{i}', 'Upper Floor', 'Elevated Parking Deck', 'EV', 'available', None))
        sample_grid_slots.append((f'G{i}', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None))
        sample_grid_slots.append((f'H{i}', 'Upper Floor', 'Elevated Parking Deck', 'Accessible', 'available', None))
    sample_grid_slots.append(('G13', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None))
    sample_grid_slots.append(('H13', 'Upper Floor', 'Elevated Parking Deck', 'VIP', 'available', None))
    sample_grid_slots.append(('E13', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None))
    sample_grid_slots.append(('F13', 'Upper Floor', 'Elevated Parking Deck', 'EV', 'available', None))
    sample_grid_slots.append(('G14', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None))
    sample_grid_slots.append(('H14', 'Upper Floor', 'Elevated Parking Deck', 'VIP', 'available', None))

    now_str = datetime.datetime.now().strftime('%Y-%m-%d')
    for slot_num, floor, zone, stype, status, plate in sample_grid_slots:
        cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_number = ?", (slot_num,))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute("""
                INSERT INTO parking_slots (lot_id, slot_number, floor, zone, slot_type, distance_to_entry_m, distance_to_elevator_m, status, current_plate)
                VALUES (?, ?, ?, ?, ?, 15, 20, ?, ?)
            """, (city_lot_id, slot_num, floor, zone, stype, status, plate))
            s_id = cursor.lastrowid
            
            # If reserved or overstayed, create corresponding reservation & overstay records
            if status == 'reserved':
                cursor.execute("""
                    INSERT INTO reservations (user_id, slot_id, vehicle_plate, date, start_time, end_time, status, total_amount, notes)
                    VALUES (2, ?, ?, ?, '10:00', '13:00', 'confirmed', 120.0, 'City Parking Reservation')
                """, (s_id, plate, now_str))
                r_id = cursor.lastrowid
                cursor.execute("UPDATE parking_slots SET current_reservation_id = ? WHERE slot_id = ?", (r_id, s_id))
            elif status == 'overstayed':
                cursor.execute("""
                    INSERT INTO reservations (user_id, slot_id, vehicle_plate, date, start_time, end_time, actual_entry_time, status, total_amount, notes)
                    VALUES (3, ?, ?, ?, '08:00', '10:00', ?, 'overstayed', 80.0, 'Overstay Demo Vehicle')
                """, (s_id, plate, now_str, f"{now_str} 08:05:00"))
                r_id = cursor.lastrowid
                cursor.execute("UPDATE parking_slots SET current_reservation_id = ? WHERE slot_id = ?", (r_id, s_id))
                cursor.execute("""
                    INSERT INTO overstay_records (reservation_id, slot_id, vehicle_plate, expected_exit, detected_at, extra_duration_minutes, penalty_amount, status)
                    VALUES (?, ?, ?, ?, ?, 45, 100.0, 'active')
                """, (r_id, s_id, plate, f"{now_str} 10:00:00", f"{now_str} 10:15:00"))

    conn.commit()
    print("Migration complete! City Parking – Mangaluru – 100 Slots verified.")
    conn.close()

if __name__ == '__main__':
    migrate()
