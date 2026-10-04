# -*- coding: utf-8 -*-
import sqlite3
import os
import requests

CLOUD_DB_URL = "https://helazjnnxyknclaltgro.supabase.co/rest/v1/behavior_logs"
API_KEY = "sb_publishable_dZyW6Y9stfSuRFO0CdFRqA_60esizOL"

def sync_data():
    try:
        local_db = "/data/data/com.termux/files/home/BehavioralShield/local_data.db"
        if not os.path.exists(local_db):
            return

        conn = sqlite3.connect(local_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM logs WHERE synced = 0 LIMIT 10")
        rows = cursor.fetchall()

        for row in rows:
            record_id, timestamp, event_data = row[0], row[1], row[2]
            payload = {"id": record_id, "timestamp": timestamp, "event_data": event_data}
            headers = {
                "apikey": API_KEY,
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            response = requests.post(CLOUD_DB_URL, json=payload, headers=headers)
            if response.status_code in [200, 201]:
                cursor.execute("UPDATE logs SET synced = 1 WHERE id = ?", (record_id,))
                conn.commit()
                print(f"Record #{record_id} imetumwa online kwenye Supabase!")
                
        conn.close()
    except Exception as e:
        print(f"Hitilafu ya Sync: {e}")

if __name__ == "__main__":
    sync_data()
