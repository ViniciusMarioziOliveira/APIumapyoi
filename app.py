from flask import Flask, render_template
import requests

app = Flask(__name__)

API_BASE = "https://api.umapyoi.net/api/v1"


@app.route("/")
def index():
    response = requests.get(f"{API_BASE}/character/list")
    
    if response.status_code != 200:
        return "Erro ao buscar personagens", 500

    characters = response.json()
    return render_template("index.html", characters=characters)


@app.route("/character/<int:char_id>")
def character_detail(char_id):

    # Buscar personagem
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