import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
import os

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "veryhiadv.db")
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        # 1. BSA 공정 테이블
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bsa_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manage_no TEXT UNIQUE NOT NULL,
            reman_no TEXT UNIQUE NOT NULL,
            customer TEXT,
            car_model TEXT,
            part_no TEXT,
            ro_no TEXT,
            warranty_type TEXT,
            status TEXT DEFAULT '입고',
            inbound_date TEXT NOT NULL,
            wash_photo TEXT
        )
        """)
        # 2. 자재 마스터
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parts_master (
            barcode TEXT PRIMARY KEY,
            part_no TEXT NOT NULL,
            part_name TEXT NOT NULL,
            part_type TEXT, 
            origin TEXT,    
            from_bsa TEXT,  
            to_bsa TEXT,    
            location TEXT,
            unit_price INTEGER DEFAULT 0
        )
        """)
        # 3. 자재 재고
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parts_stock (
            barcode TEXT PRIMARY KEY,
            current_qty INTEGER DEFAULT 0,
            last_update TEXT,
            FOREIGN KEY(barcode) REFERENCES parts_master(barcode)
        )
        """)
        # 4. 통합 이력 테이블
        conn.execute("""
        CREATE TABLE IF NOT EXISTS part_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bsa_manage_no TEXT,
            part_type TEXT,
            new_barcode TEXT,
            old_barcode TEXT,
            usage_date TEXT,
            FOREIGN KEY(bsa_manage_no) REFERENCES bsa_units(manage_no)
        )
        """)
        conn.commit()

# --- [신규] 바코드의 현재 재고 수량 조회 ---
def get_part_stock_qty(barcode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_qty FROM parts_stock WHERE barcode = ?", (barcode,))
        row = cursor.fetchone()
        return row[0] if row else 0

def get_bsa_info_by_no(manage_no):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT car_model, customer, part_no FROM bsa_units WHERE manage_no = ?", (manage_no,))
        return cursor.fetchone()

def get_next_reman_no():
    yy = datetime.now().strftime("%y") 
    prefix = f"RS{yy}-HS"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT reman_no FROM bsa_units WHERE reman_no LIKE ? ORDER BY reman_no DESC LIMIT 1", (f"{prefix}%",))
        row = cursor.fetchone()
        if not row: return f"{prefix}0001"
        last_seq = int(row[0].split("-HS")[-1])
        return f"{prefix}{last_seq + 1:04d}"

def insert_bsa(data):
    try:
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO bsa_units (manage_no, reman_no, customer, car_model, part_no, ro_no, warranty_type, inbound_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['manage_no'], data['reman_no'], data['customer'], data['car_model'], 
                  data['part_no'], data['ro_no'], data['warranty_type'], data['inbound_date']))
            conn.commit()
        return True, None
    except sqlite3.IntegrityError: return False, "🚨 이미 등록된 관리번호입니다."
    except Exception as e: return False, f"❌ 등록 실패: {str(e)}"

def get_all_bsa():
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM bsa_units ORDER BY id DESC", conn)

def update_bsa_status(manage_no, new_status, photo_path=None):
    with get_connection() as conn:
        if photo_path:
            conn.execute("UPDATE bsa_units SET status = ?, wash_photo = ? WHERE manage_no = ?", (new_status, photo_path, manage_no))
        else:
            conn.execute("UPDATE bsa_units SET status = ? WHERE manage_no = ?", (new_status, manage_no))
        conn.commit()

def check_barcode_exists(barcode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT barcode FROM parts_master WHERE barcode = ?", (barcode,))
        return cursor.fetchone() is not None

def get_part_info_by_barcode(barcode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT part_name, part_no, part_type, origin, from_bsa, to_bsa FROM parts_master WHERE barcode = ?", (barcode,))
        return cursor.fetchone()

def register_and_inbound(data_list):
    with get_connection() as conn:
        for item in data_list:
            conn.execute("""
                INSERT OR REPLACE INTO parts_master (barcode, part_no, part_name, unit_price, location, part_type, origin, from_bsa) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item['barcode'], item['part_no'], item['part_name'], 0, item['location'], item['part_type'], item['origin'], item.get('from_bsa')))
            conn.execute("""
                INSERT INTO parts_stock (barcode, current_qty, last_update) VALUES (?, ?, ?)
                ON CONFLICT(barcode) DO UPDATE SET current_qty = current_qty + excluded.current_qty, last_update = excluded.last_update
            """, (item['barcode'], item['qty'], datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

def record_multiple_usages(bsa_no, usage_list):
    with get_connection() as conn:
        for item in usage_list:
            p_type, new_b, old_b = item['type'], item['new'], item['old']
            conn.execute("""
                INSERT INTO part_usage (bsa_manage_no, part_type, new_barcode, old_barcode, usage_date)
                VALUES (?, ?, ?, ?, ?)
            """, (bsa_no, p_type, new_b, old_b, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.execute("UPDATE parts_master SET to_bsa = ? WHERE barcode = ?", (bsa_no, new_b))
            conn.execute("UPDATE parts_stock SET current_qty = current_qty - 1 WHERE barcode = ?", (new_b,))
            
            p_info = get_part_info_by_barcode(new_b)
            p_no, p_name = (p_info[1], p_info[0]) if p_info else ("Unknown", f"{p_type} 탈거품")
            conn.execute("""
                INSERT OR REPLACE INTO parts_master (barcode, part_no, part_name, part_type, location, origin, from_bsa)
                VALUES (?, ?, ?, '폐기품', '폐기함', '일반', ?)
            """, (old_b, p_no, p_name, bsa_no))
            conn.execute("INSERT OR REPLACE INTO parts_stock (barcode, current_qty, last_update) VALUES (?, 1, ?)", (old_b, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.execute("UPDATE bsa_units SET status = '분해조립완료' WHERE manage_no = ?", (bsa_no,))
        conn.commit()

def save_photo(manage_no, uploaded_file):
    if uploaded_file:
        ext = uploaded_file.name.split(".")[-1]
        save_path = UPLOAD_DIR / f"{manage_no}_wash.{ext}"
        with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())
        return str(save_path)
    return None