from flask import Flask, render_template
import requests

app = Flask(__name__)

API_BASE = "https://api.umapyoi.net/api/v1"

@app.route("/")
def index():
    response = requests.get(f"{API_BASE}/character/list")
    characters = response.json()
    return render_template("index.html", characters=characters)


@app.route("/character/<int:char_id>")
def character_detail(char_id):
    response = requests.get(f"{API_BASE}/character/info")
    characters = response.json()

    character = next((c for c in characters if c["id"] == char_id), None)

    if not character:
        return "Personagem não encontrado", 404

    return render_template("character.html", character=character)

if __name__ == "__main__":
    app.run(debug=True)