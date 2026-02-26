from flask import Flask, render_template
import requests
from datetime import datetime
import random

app = Flask(__name__)

API_BASE = "https://api.umapyoi.net/api/v1"

# 🔥 Cache global
birthday_cache = []


def load_birthdays():
    """
    Carrega todos os aniversários da API uma única vez
    e salva em memória.
    """
    global birthday_cache

    print("Carregando aniversários...")

    response = requests.get(f"{API_BASE}/character/list")
    if response.status_code != 200:
        print("Erro ao buscar lista de personagens")
        return

    characters = response.json()

    for char in characters:
        char_id = char["id"]

        detail_response = requests.get(f"{API_BASE}/character/{char_id}")
        if detail_response.status_code == 200:
            detail = detail_response.json()

            # Só adiciona se tiver data válida
            if detail.get("birth_day") and detail.get("birth_month"):
                birthday_cache.append({
                    "name": detail.get("name_en"),
                    "day": detail.get("birth_day"),
                    "month": detail.get("birth_month")
                })


# 🔥 Executa UMA VEZ quando o servidor inicia
load_birthdays()


@app.route("/")
def index():
    response = requests.get(f"{API_BASE}/character/list")

    if response.status_code != 200:
        return "Erro ao buscar personagens", 500

    characters = response.json()

    current_month = datetime.now().month

    birthday_list = [
        b for b in birthday_cache
        if int(b["month"]) == current_month
    ]

    # 🎲 Personagem aleatória
    random_character = random.choice(characters)

    return render_template(
        "index.html",
        characters=characters,
        birthdays=birthday_list,
        random_character=random_character
    )


@app.route("/character/<int:char_id>")
def character_detail(char_id):

    char_response = requests.get(f"{API_BASE}/character/{char_id}")
    if char_response.status_code != 200:
        return "Personagem não encontrado", 404

    character = char_response.json()
    game_id = character.get("game_id")

    image_groups = []

    if game_id:
        image_response = requests.get(f"{API_BASE}/character/images/{game_id}")
        if image_response.status_code == 200:
            image_groups = image_response.json()

    return render_template(
        "character.html",
        character=character,
        image_groups=image_groups
    )


if __name__ == "__main__":
    app.run(debug=True)