import requests
import json

API_BASE = "https://api.umapyoi.net/api/v1"

print("Gerando birthdays.json...")

response = requests.get(f"{API_BASE}/character/list")

if response.status_code != 200:
    print("Erro ao buscar lista")
    exit()

characters = response.json()

birthday_list = []

for char in characters:
    char_id = char["id"]

    detail_response = requests.get(f"{API_BASE}/character/{char_id}")
    if detail_response.status_code == 200:
        detail = detail_response.json()

        if detail.get("birth_day") and detail.get("birth_month"):
            birthday_list.append({
                "name": detail.get("name_en"),
                "day": detail.get("birth_day"),
                "month": detail.get("birth_month")
            })

# Salva em arquivo
with open("birthdays.json", "w", encoding="utf-8") as f:
    json.dump(birthday_list, f, ensure_ascii=False, indent=4)

print("Arquivo birthdays.json criado com sucesso!")