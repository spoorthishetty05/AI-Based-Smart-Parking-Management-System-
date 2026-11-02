import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import sqlite3
import datetime

def clean_and_setup_city_parking():
    conn = sqlite3.connect('smart_parking.db')
    cursor = conn.cursor()

    # Get City Parking lot_id
    cursor.execute("SELECT lot_id FROM parking_lots WHERE lot_name = 'City Parking'")
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT INTO parking_lots (lot_name, location, total_floors, total_slots, hourly_rate, overstay_penalty_rate, operating_hours)
            VALUES ('City Parking', 'Hampankatta, Mangaluru', 2, 100, 40.0, 100.0, '24/7 (Open Daily)')
        """)
        city_lot_id = cursor.lastrowid
    else:
        city_lot_id = row[0]
        cursor.execute("UPDATE parking_lots SET location = 'Hampankatta, Mangaluru', total_slots = 100, operating_hours = '24/7 (Open Daily)' WHERE lot_id = ?", (city_lot_id,))

    # Remove any existing slots and reservations for City Parking to recreate cleanly
    cursor.execute("SELECT slot_id FROM parking_slots WHERE lot_id = ?", (city_lot_id,))
    existing_sids = [r[0] for r in cursor.fetchall()]
    if existing_sids:
        placeholders = ','.join('?' * len(existing_sids))
        cursor.execute(f"DELETE FROM overstay_records WHERE slot_id IN ({placeholders})", existing_sids)
        cursor.execute(f"DELETE FROM reservations WHERE slot_id IN ({placeholders})", existing_sids)
        cursor.execute(f"DELETE FROM parking_slots WHERE lot_id = ?", (city_lot_id,))

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    slots = []

    # Ground Floor: 50 slots (A1-A12, B1-B12, C1-C13, D1-D13)
    # Row A: A1 (Regular, available), A2 (VIP, reserved), A3 (Accessible, occupied), A4 (EV, overstayed)
    slots.append(('A1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None, None, None))
    slots.append(('A2', 'Ground Floor', 'City Central Wing', 'VIP', 'reserved', 'KA 19 AB 1234', '16:00', '19:00'))
    slots.append(('A3', 'Ground Floor', 'City Central Wing', 'Accessible', 'occupied', 'KA 19 XY 9876', '12:00', '18:00'))
    slots.append(('A4', 'Ground Floor', 'City Central Wing', 'EV', 'overstayed', 'KA 19 CD 5678', '08:00', '10:00'))

    for i in range(5, 13):
        st = 'EV' if i % 4 == 0 else ('VIP' if i % 3 == 0 else 'Regular')
        slots.append((f'A{i}', 'Ground Floor', 'City Central Wing', st, 'available', None, None, None))

    # Row B: B1-B12
    slots.append(('B1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None, None, None))
    slots.append(('B2', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None, None, None))
    slots.append(('B3', 'Ground Floor', 'City Central Wing', 'Accessible', 'available', None, None, None))
    slots.append(('B4', 'Ground Floor', 'City Central Wing', 'VIP', 'available', None, None, None))
    for i in range(5, 13):
        st = 'Accessible' if i % 4 == 0 else ('VIP' if i % 3 == 0 else 'Regular')
        slots.append((f'B{i}', 'Ground Floor', 'City Central Wing', st, 'available', None, None, None))

    # Row C: C1-C13
    slots.append(('C1', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None, None, None))
    slots.append(('C2', 'Ground Floor', 'City Central Wing', 'EV', 'available', None, None, None))
    slots.append(('C3', 'Ground Floor', 'City Central Wing', 'Regular', 'available', None, None, None))
    slots.append(('C4', 'Ground Floor', 'City Central Wing', 'Accessible', 'available', None, None, None))
    for i in range(5, 14):
        st = 'EV' if i % 3 == 0 else 'Regular'
        slots.append((f'C{i}', 'Ground Floor', 'City Central Wing', st, 'available', None, None, None))

    # Row D: D1-D13
    for i in range(1, 14):
        st = 'VIP' if i in (1, 7) else ('Accessible' if i in (2, 8) else 'Regular')
        slots.append((f'D{i}', 'Ground Floor', 'City Central Wing', st, 'available', None, None, None))

    # Upper Floor: 50 slots (E1-E12, F1-F12, G1-G13, H1-H13)
    for i in range(1, 13):
        slots.append((f'E{i}', 'Upper Floor', 'Elevated Parking Deck', 'Regular', 'available', None, None, None))
        slots.append((f'F{i}', 'Upper Floor', 'Elevated Parking Deck', 'EV' if i % 2 == 0 else 'Regular', 'available', None, None, None))

    for i in range(1, 14):
        slots.append((f'G{i}', 'Upper Floor', 'Elevated Parking Deck', 'Accessible' if i % 3 == 0 else 'Regular', 'available', None, None, None))
        slots.append((f'H{i}', 'Upper Floor', 'Elevated Parking Deck', 'VIP' if i % 4 == 0 else 'Regular', 'available', None, None, None))

    assert len(slots) == 100, f"Expected 100 slots, got {len(slots)}"

    # Insert slots
    for slot_num, floor, zone, stype, status, plate, start_time, end_time in slots:
        cursor.execute("""
            INSERT INTO parking_slots (lot_id, slot_number, floor, zone, slot_type, distance_to_entry_m, distance_to_elevator_m, status, current_plate)
            VALUES (?, ?, ?, ?, ?, 15, 20, ?, ?)
        """, (city_lot_id, slot_num, floor, zone, stype, status, plate))
        s_id = cursor.lastrowid

        if status == 'reserved':
            cursor.execute("""
                INSERT INTO reservations (user_id, slot_id, vehicle_plate, date, start_time, end_time, status, total_amount, notes)
                VALUES (2, ?, ?, ?, ?, ?, 'confirmed', 80.0, 'VIP Reserved Booking')
            """, (s_id, plate, today_str, start_time, end_time))
            r_id = cursor.lastrowid
            cursor.execute("UPDATE parking_slots SET current_reservation_id = ? WHERE slot_id = ?", (r_id, s_id))

        elif status == 'occupied':
            cursor.execute("""
                INSERT INTO reservations (user_id, slot_id, vehicle_plate, date, start_time, end_time, actual_entry_time, status, total_amount, notes)
                VALUES (3, ?, ?, ?, ?, ?, ?, 'checked_in', 120.0, 'Accessible Active Parking')
            """, (s_id, plate, today_str, start_time, end_time, f"{today_str} 11:05:00"))
            r_id = cursor.lastrowid
            cursor.execute("UPDATE parking_slots SET current_reservation_id = ? WHERE slot_id = ?", (r_id, s_id))

        elif status == 'overstayed':
            cursor.execute("""
                INSERT INTO reservations (user_id, slot_id, vehicle_plate, date, start_time, end_time, actual_entry_time, status, total_amount, notes)
                VALUES (4, ?, ?, ?, ?, ?, ?, 'overstayed', 80.0, 'EV Overstayed Session')
            """, (s_id, plate, today_str, start_time, end_time, f"{today_str} 08:02:00"))
            r_id = cursor.lastrowid
            cursor.execute("UPDATE parking_slots SET current_reservation_id = ? WHERE slot_id = ?", (r_id, s_id))
            cursor.execute("""
                INSERT INTO overstay_records (reservation_id, slot_id, vehicle_plate, expected_exit, detected_at, extra_duration_minutes, penalty_amount, status)
                VALUES (?, ?, ?, ?, ?, 45, 100.0, 'active')
            """, (r_id, s_id, plate, f"{today_str} 10:00:00", f"{today_str} 10:15:00"))

    conn.commit()

    # Verification summary
    cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE lot_id = ?", (city_lot_id,))
    total_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT status, COUNT(*) FROM parking_slots WHERE lot_id = ? GROUP BY status", (city_lot_id,))
    status_summary = dict(cursor.fetchall())
    cursor.execute("SELECT DISTINCT slot_type FROM parking_slots WHERE lot_id = ?", (city_lot_id,))
    types_list = [r[0] for r in cursor.fetchall()]

    print("=" * 65)
    print("CITY PARKING – MANGALURU – 100 SLOTS SETUP SUCCESSFUL")
    print("=" * 65)
    print(f"Total Slots: {total_cnt}")
    print(f"Slot Types: {types_list}")
    print(f"Status Breakdown: {status_summary}")
    print("Row A Preview:")
    cursor.execute("SELECT slot_number, slot_type, status, current_plate FROM parking_slots WHERE lot_id = ? AND slot_number IN ('A1','A2','A3','A4')", (city_lot_id,))
    for r in cursor.fetchall():
        print(f"  {r[0]}: Type={r[1]}, Status={r[2]}, Plate={r[3]}")
    conn.close()

if __name__ == '__main__':
    clean_and_setup_city_parking()
