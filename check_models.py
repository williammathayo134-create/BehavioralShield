# -*- coding: utf-8 -*-
import requests

GROQ_API_KEY = ""
url = "https://api.groq.com/openai/v1/models"
headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

try:
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        models = response.json().get('data', [])
        print("Models zinazopatikana kwenye Groq API yako:")
        for m in models:
            print(f"- {m['id']}")
    else:
        print("Hitilafu:", response.status_code, response.text)
except Exception as e:
    print(f"Hitilafu: {e}")
