# -*- coding: utf-8 -*-
import sqlite3
import requests
import json
import os

GROQ_API_KEY = ""

def fetch_local_logs():
    try:
        local_db = "/data/data/com.termux/files/home/BehavioralShield/local_data.db"
        if not os.path.exists(local_db):
            print("Hakuna hifadhidata ya ndani iliyopatikana.")
            return
            
        conn = sqlite3.connect(local_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            logs.append({"id": row[0], "timestamp": row[1], "event_data": row[2]})
            
        print(f"Imefanikiwa kusoma kumbukumbu {len(logs)} kutoka kwenye hifadhidata ya ndani.")
        analyze_with_groq(logs)
    except Exception as e:
        print(f"Hitilafu wakati wa kusoma data za ndani: {e}")

def analyze_with_groq(logs):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"Hili ni kundi la kumbukumbu za tabia za simu ya mtumiaji: {json.dumps(logs)}. Chambua na utoe mapendekezo mawili ya kuboresha uokoaji wa chaji na utendaji wa mfumo."
        
        data = {
            "model": "qwen/qwen3.8-27b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }
        
        res = requests.post(url, headers=headers, json=data)
        if res.status_code == 200:
            result = res.json()
            advice = result['choices'][0]['message']['content']
            
            summary_path = "/data/data/com.termux/files/home/BehavioralShield/weekly_insight.txt"
            with open(summary_path, "w") as f:
                f.write(advice)
            print("Uchambuzi wa Groq AI umehifadhiwa kwenye weekly_insight.txt kwa mafanikio!")
        else:
            print("Hitilafu kutoka Groq API:", res.status_code, res.text)
    except Exception as e:
        print(f"Hitilafu ya uchambuzi wa AI: {e}")

if __name__ == "__main__":
    fetch_local_logs()
