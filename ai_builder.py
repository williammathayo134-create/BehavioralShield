# -*- coding: utf-8 -*-
import os
import json
import urllib.request
import time

GROQ_API_KEY = ""
url = "https://api.groq.com/openai/v1/chat/completions"
model_name = "openai/gpt-oss-120b"

project_files = {"main.py": "Andika code ya main.py inayounganisha local storage na weekly cloud sync."}
    "local_storage.py": "Andika code kamili ya Python ya SQLite inayotunza sensor_logs na security_events.",
    "sensor_monitor.py": "Andika code kamili ya Python ya kusoma Accelerometer na Gyroscope.",
    "ml_model.py": "Andika code kamili ya Python ya Machine Learning ya kuchunguza tabia ya mtumiaji.",
    "security_actions.py": "Andika code kamili ya Python inayofunga simu na kupiga picha ya siri.",
    "cloud_sync.py": "Andika code inayotuma data kwenye cloud kila wiki moja na kuhifadhi SQLite offline kwanza.",
    "main.py": "Andika faili kuu lenye muundo wa Settings la kuwasha na kuzima mfumo mzima."
}

os.makedirs("/data/data/com.termux/files/home/BehavioralShield", exist_ok=True)

print("AI anaanza kuandika code kwa kutumia modeli ya openai/gpt-oss-120b...")

for filename, task_desc in project_files.items():
    file_path = f"/data/data/com.termux/files/home/BehavioralShield/{filename}"
    print(f"Inaandika: {filename}...")
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Wewe ni mtaalamu wa Python. Andika code safi na kamili pekee."},
            {"role": "user", "content": task_desc}
        ],
        "temperature": 0.1
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Termux-Python-Client"
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            gen_code = res_data["choices"][0]["message"]["content"]
            
            if "```python" in gen_code:
                gen_code = gen_code.split("```python")[1].split("```")[0]
            elif "```" in gen_code:
                gen_code = gen_code.split("```")[1].split("```")[0]

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(gen_code.strip())
            print(f"Imefanikiwa: {filename}")
    except Exception as e:
        print(f"Kosa kwenye {filename}: {e}")
    
    time.sleep(1)

print("Kazi imekamilika! Mafaili yote yameandikwa kikamilifu.")
