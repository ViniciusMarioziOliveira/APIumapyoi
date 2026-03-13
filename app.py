from flask import Flask, render_template, jsonify
import requests
from datetime import datetime
import random
import json

app = Flask(__name__)

API_BASE = "https://api.umapyoi.net/api/v1"

# ==========================
# CACHE DE PERSONAGENS
# ==========================

print("Carregando personagens da API...")

response = requests.get(f"{API_BASE}/character/list")

if response.status_code == 200:
    characters = response.json()
else:
    characters = []

print(f"{len(characters)} personagens carregados!")

# ==========================
# CACHE DE ANIVERSÁRIOS
# ==========================

with open("birthdays.json", "r", encoding="utf-8") as f:
    birthday_cache = json.load(f)

# ==========================
# INDEX
# ==========================

@app.route("/")
def index():

    current_month = datetime.now().month

    birthday_list = [
        b for b in birthday_cache
        if int(b["month"]) == current_month
    ]

    random_character = random.choice(characters) if characters else None

    return render_template(
        "index.html",
        characters=characters,
        birthdays=birthday_list,
        random_character=random_character
    )

# ==========================
# CHARACTER PAGE
# ==========================

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

# ==========================
# QUIZ PAGE
# ==========================

@app.route("/quiz")
def quiz():

    if not characters:
        return "Erro ao carregar personagens", 500

    correct = random.choice(characters)

    wrong = random.sample(
        [c for c in characters if c["id"] != correct["id"]],
        3
    )

    options = wrong + [correct]
    random.shuffle(options)

    return render_template(
        "quiz.html",
        correct=correct,
        options=options
    )

# ==========================
# PROXIMA PERGUNTA
# ==========================

@app.route("/quiz/next")
def next_question():

    if not characters:
        return jsonify({"error": "Characters not loaded"}), 500

    correct = random.choice(characters)

    options = random.sample(characters, 4)

    if correct not in options:
        options[0] = correct

    random.shuffle(options)

    return jsonify({
        "correct_id": correct["id"],
        "image": correct["thumb_img"],
        "options": [
            {"id": o["id"], "name": o["name_en"]}
            for o in options
        ]
    })

# ==========================
# 404
# ==========================

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# ==========================
# RUN
# ==========================

if __name__ == "__main__":
    app.run(debug=True, port=5001)