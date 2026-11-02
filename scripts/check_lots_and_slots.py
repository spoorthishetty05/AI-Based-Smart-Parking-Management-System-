import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import sqlite3

def check():
    conn = sqlite3.connect('smart_parking.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM parking_lots")
    lots = [dict(r) for r in c.fetchall()]
    print(f"Total Parking Lots: {len(lots)}")
    for l in lots:
        c.execute("SELECT COUNT(*), COUNT(DISTINCT slot_type) FROM parking_slots WHERE lot_id = ?", (l['lot_id'],))
        cnt, types_cnt = c.fetchone()
        print(f" - Lot #{l['lot_id']}: {l['lot_name']} ({l['location']}) - {cnt} slots in DB (Capacity: {l['total_slots']})")

    c.execute("SELECT DISTINCT slot_type FROM parking_slots")
    types = [r[0] for r in c.fetchall()]
    print(f"\nDistinct Slot Types: {types}")

    c.execute("SELECT status, COUNT(*) FROM parking_slots GROUP BY status")
    statuses = dict(c.fetchall())
    print(f"\nSlot Status Breakdown: {statuses}")
    conn.close()

if __name__ == '__main__':
    check()
