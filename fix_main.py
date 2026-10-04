# -*- coding: utf-8 -*-
import os
import json
import urllib.request

GROQ_API_KEY = ""
url = "https://api.groq.com/openai/v1/chat/completions"
model_name = "openai/gpt-oss-120b"

payload = {
    "model": model_name,
    "messages": [
        {"role": "system", "content": "Wewe ni mtaalamu bingwa wa Python. Andika code kamili na safi ya main.py pekee inayounganisha local storage na weekly cloud sync."},
        {"role": "user", "content": "Andika faili kuu la main.py linalounganisha SQLite local-first na weekly cloud sync."}
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

        file_path = "/data/data/com.termux/files/home/BehavioralShield/main.py"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(gen_code.strip())
        print("Faili la main.py limeandikwa na kukamilika kikamilifu!")
except Exception as e:
    print(f"Kosa: {e}")
