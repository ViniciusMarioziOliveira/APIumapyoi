from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta, timezone
from time import monotonic
from urllib.parse import urlparse
import random
import re

import requests

app = Flask(__name__)

API_BASE = "https://api.umapyoi.net/api/v1"
REQUEST_TIMEOUT = 10          # segundos
LIST_TTL = 60 * 60 * 6        # lista de personagens: 6 horas
DETAIL_TTL = 60 * 60          # detalhes e imagens: 1 hora
RETRY_AFTER_FAILURE = 60      # se a API cair, tenta de novo depois de 1 minuto

# Horário de Brasília (sem horário de verão desde 2019)
BRT = timezone(timedelta(hours=-3))

MONTHS_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

OUTFIT_LABELS_PT = {
    "Uniform": "Uniforme",
    "Racewear": "Traje de Corrida",
    "Concept Art": "Arte Conceitual",
    "Starting Future": "Starting Future",
    "Default": "Padrão",
}

DEFAULT_COLOR = "#f72585"
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")

session = requests.Session()


class ApiError(Exception):
    """A API não respondeu ou respondeu com erro."""


# ==========================
# ACESSO À API (COM CACHE)
# ==========================

def fetch_json(path):
    """GET na API. Retorna None se o recurso não existir (404)."""
    try:
        response = session.get(f"{API_BASE}{path}", timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ApiError(f"HTTP {response.status_code} em {path}")

    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(f"JSON inválido em {path}") from exc


_cache = {}


def cached_fetch(path, ttl=DETAIL_TTL):
    hit = _cache.get(path)
    if hit and monotonic() - hit[0] < ttl:
        return hit[1]

    try:
        data = fetch_json(path)
    except ApiError:
        if hit:                 # API fora do ar: serve a versão antiga
            return hit[1]
        raise

    _cache[path] = (monotonic(), data)
    return data


# ==========================
# CORES
# ==========================

def normalize_color(value, fallback=DEFAULT_COLOR):
    value = (value or "").strip()
    if not HEX_COLOR.match(value):
        return fallback
    if len(value) == 4:  # #abc -> #aabbcc
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value.lower()


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def text_on(hex_color):
    """Cor de texto (branco ou roxo-escuro) mais legível sobre a cor dada."""
    lum = _luminance(_rgb(hex_color))
    dark = _luminance(_rgb("#1e1030"))
    return "#ffffff" if _contrast(lum, 1.0) >= _contrast(lum, dark) else "#1e1030"


def ink(hex_color):
    """Escurece a cor até ela ficar legível como texto sobre fundo branco."""
    r, g, b = _rgb(hex_color)
    for step in range(0, 101, 5):
        k = 1 - step / 100
        rgb = (round(r * k), round(g * k), round(b * k))
        if _contrast(_luminance(rgb), 1.0) >= 4.5:
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#1e1030"


def decorate(char):
    """Adiciona campos de apresentação (cores legíveis e categoria)."""
    main = normalize_color(char.get("color_main"))
    sub = normalize_color(char.get("color_sub"), fallback=main)
    char["color_main"] = main
    char["color_sub"] = sub
    char["color_ink"] = ink(main)
    char["color_on"] = text_on(main)
    is_uma = (char.get("category_label_en") or "").strip().lower() == "umamusume"
    char["category"] = "uma" if is_uma else "related"
    return char


# ==========================
# CACHE DE PERSONAGENS
# ==========================

_characters = {"data": [], "expires": 0.0}


def get_characters():
    """Lista de personagens, recarregada a cada LIST_TTL (ou após falha)."""
    if monotonic() < _characters["expires"]:
        return _characters["data"]

    try:
        data = fetch_json("/character/list") or []
    except ApiError:
        app.logger.warning("Não foi possível carregar a lista de personagens")
        _characters["expires"] = monotonic() + RETRY_AFTER_FAILURE
        return _characters["data"]

    _characters["data"] = [decorate(c) for c in data if c.get("id")]
    _characters["expires"] = monotonic() + LIST_TTL
    return _characters["data"]


def today_brt():
    return datetime.now(BRT).date()


# ==========================
# FILTROS DE TEMPLATE
# ==========================

def _cdn_url(url, params):
    """Acrescenta parâmetros de imagem do CDN do microCMS (imgix)."""
    if not url or urlparse(url).netloc != "images.microcms-assets.io":
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + "&".join(params)


@app.template_filter("img")
def resized_image(url, width=None, height=None):
    """Pede ao CDN uma versão menor (WebP) da imagem."""
    params = ["fm=webp"]
    if width:
        params.append(f"w={width}")
    if height:
        params.append(f"h={height}")
    return _cdn_url(url, params)


@app.template_filter("bust")
def bust_crop(url, size=96):
    """Recorte quadrado com zoom no busto, para as miniaturas de roupa."""
    return _cdn_url(url, [
        "fit=crop", "crop=focalpoint", "fp-x=0.5", "fp-y=0.3", "fp-z=1.6",
        f"w={size}", f"h={size}", "fm=webp",
    ])


@app.template_filter("birthday")
def format_birthday(char):
    day, month = char.get("birth_day"), char.get("birth_month")
    if not day or not month:
        return None
    return f"{day} de {MONTHS_PT[int(month)]}"


# ==========================
# INDEX
# ==========================

@app.route("/")
def index():
    characters = get_characters()
    if not characters:
        return render_error(503)

    today = today_brt()

    birthday_list = sorted(
        (c for c in characters
         if c.get("birth_month") == today.month and c.get("birth_day")),
        key=lambda c: c["birth_day"],
    )

    return render_template(
        "index.html",
        characters=characters,
        umamusume_chars=[c for c in characters if c["category"] == "uma"],
        related_chars=[c for c in characters if c["category"] == "related"],
        birthdays=birthday_list,
        month_name=MONTHS_PT[today.month],
        today=today,
        random_character=random.choice(characters),
    )


# ==========================
# CHARACTER PAGE
# ==========================

def build_profile(character):
    """Linhas da ficha de perfil, só com os campos que a API preencheu."""
    rows = []

    def add(label, value):
        if value not in (None, "", []):
            rows.append({"label": label, "value": value})

    sizes = [character.get(k) for k in ("size_b", "size_w", "size_h")]
    measures = (
        f"B{sizes[0]} · W{sizes[1]} · H{sizes[2]}" if all(sizes) else None
    )

    add("Peso", character.get("weight"))
    add("Medidas", measures)
    add("Calçado", character.get("shoe_size"))
    add("Dormitório", character.get("residence"))
    add("Pontos fortes", character.get("strengths"))
    add("Pontos fracos", character.get("weaknesses"))
    return rows


def build_facts(character):
    facts = [
        ("👂", "Sobre as orelhas", character.get("ears_fact")),
        ("🐎", "Sobre a cauda", character.get("tail_fact")),
        ("🏠", "Sobre a família", character.get("family_fact")),
    ]
    return [{"icon": i, "label": l, "text": t} for i, l, t in facts if t]


def build_outfits(image_groups):
    outfits = []
    for group in image_groups or []:
        images = group.get("images") or []
        if not images or not images[0].get("image"):
            continue
        label_en = group.get("label_en") or "Outfit"
        outfits.append({
            "label": OUTFIT_LABELS_PT.get(label_en, label_en),
            "image": images[0]["image"],
        })
    return outfits


@app.route("/character/<int:char_id>")
def character_detail(char_id):
    try:
        character = cached_fetch(f"/character/{char_id}")
    except ApiError:
        return render_error(503)

    if not character:
        return render_error(404)

    character = decorate(dict(character))

    outfits = []
    game_id = character.get("game_id")
    if game_id:
        try:
            outfits = build_outfits(cached_fetch(f"/character/images/{game_id}"))
        except ApiError:
            app.logger.warning("Falha ao carregar imagens de %s", char_id)

    # Personagem anterior / próxima, na ordem da lista
    characters = get_characters()
    prev_char = next_char = None
    ids = [c["id"] for c in characters]
    if char_id in ids:
        pos = ids.index(char_id)
        prev_char = characters[pos - 1]
        next_char = characters[(pos + 1) % len(characters)]

    return render_template(
        "character.html",
        character=character,
        outfits=outfits,
        profile_rows=build_profile(character),
        facts=build_facts(character),
        prev_char=prev_char,
        next_char=next_char,
    )


# ==========================
# QUIZ PAGE
# ==========================

@app.route("/quiz")
def quiz():
    if len(get_characters()) < 4:
        return render_error(503)
    return render_template("quiz.html")


# ==========================
# PROXIMA PERGUNTA
# ==========================

@app.route("/quiz/next")
def next_question():
    characters = get_characters()
    if len(characters) < 4:
        return jsonify({"error": "Characters not loaded"}), 503

    used_ids = set(request.args.getlist("used[]", type=int))

    # personagens ainda não usados
    available = [c for c in characters if c["id"] not in used_ids]

    # se acabaram os personagens, recomeça com a lista completa
    if len(available) < 4:
        available = characters

    correct = random.choice(available)
    wrong = random.sample([c for c in available if c["id"] != correct["id"]], 3)

    options = wrong + [correct]
    random.shuffle(options)

    return jsonify({
        "correct_id": correct["id"],
        "image": resized_image(correct["thumb_img"], width=480),
        "color": correct["color_main"],
        "options": [{"id": o["id"], "name": o["name_en"]} for o in options],
    })


# ==========================
# ERROS
# ==========================

ERRORS = {
    404: (
        "Essa página não existe...",
        "Parece que você tentou acessar uma rota que não foi encontrada. "
        "Talvez ela tenha sido removida ou nunca existiu.",
    ),
    500: (
        "Tropeçamos na largada!",
        "Algo deu errado aqui do nosso lado. Tente novamente em instantes.",
    ),
    503: (
        "A pista está fechada...",
        "Não conseguimos falar com a API umapyoi.net agora. "
        "Tente de novo daqui a pouco.",
    ),
}


def render_error(code):
    title, message = ERRORS[code]
    return render_template("404.html", code=code, title=title, message=message), code


@app.errorhandler(404)
def page_not_found(e):
    return render_error(404)


@app.errorhandler(500)
def server_error(e):
    return render_error(500)


# ==========================
# RUN
# ==========================

if __name__ == "__main__":
    app.run(debug=True, port=5001)
