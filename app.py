from fastapi import FastAPI, Form, Request, Cookie
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import urllib.parse
import csv
from io import StringIO
import os

app = FastAPI()

# -----------------------------
# FIREBASE (via variáveis de ambiente)
# -----------------------------
firebase_config = {
    "type": "service_account",
    "project_id": os.environ.get("FIRESTORE_PROJECT_ID"),
    "private_key_id": os.environ.get("FIRESTORE_PRIVATE_KEY_ID"),
    "private_key": os.environ.get("FIRESTORE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIRESTORE_CLIENT_EMAIL"),
    "client_id": os.environ.get("FIRESTORE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": ""
}

cred = credentials.Certificate(firebase_config)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# DISCORD CONFIG (via env)
# -----------------------------
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI")  # EX: "https://teusite.onrender.com/callback"

ADMINS = os.environ.get("ADMINS", "").split(",")  # lista separada por vírgulas

# -----------------------------
# TEMPLATES
# -----------------------------
templates = Jinja2Templates(directory="templates")


def buscar_user_discord(user_id: str):
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    r = requests.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers)
    if r.status_code == 200:
        data = r.json()
        return {
            "id": user_id,
            "username": data.get("username"),
            "global_name": data.get("global_name"),
            "tag": f"{data.get('username')}#{data.get('discriminator')}"
        }
    return {"id": user_id, "username": None, "global_name": None, "tag": None}


# -----------------------------
# FORMULÁRIO DE AVALIAÇÃO
# -----------------------------
@app.post("/submit")
async def submit_form(
    user_id: str = Form(...),
    nome: str = Form(...),
    tema: str = Form(...),
    avaliacoes_feitas: int = Form(...),
    assaltos: int = Form(...),
    abordagens: int = Form(...),
    perseg: int = Form(...),
    detencoes_count: int = Form(...),
    radio: int = Form(...),
    radio_desc: str = Form(...),
    conduta: int = Form(...),
    conduta_desc: str = Form(...),
    nota_detencao: int = Form(...),
    det1_leu_direitos: str = Form(...),
    det1_identificou: str = Form(...),
    det1_apreendeu: str = Form(...),
    conduta_desc2: str = Form(...),
    nota_detencao2: int = Form(...),
    det2_leu_direitos: str = Form(...),
    det2_identificou: str = Form(...),
    det2_apreendeu: str = Form(...),
    nota_incidente: int = Form(...),
    crimes_yesno: str = Form(...),
    foto_yesno: str = Form(...),
    layout_yesno: str = Form(...),
    descricao_yesno: str = Form(...),
    incidente_erros: str = Form(""),
    incidente_obs: str = Form(...)
):

    try:
        avaliador_info = buscar_user_discord(user_id)

        embed = {
            "title": "📋 Nova Avaliação de Guarda",
            "description": f"Avaliação enviada por <@{user_id}>",
            "color": 0x00FF00,
            "fields": [
                {"name": "👤 Nome do Avaliado", "value": nome, "inline": False},
                {"name": "📌 Tema", "value": tema, "inline": False},
                {"name": "📊 Geral",
                 "value": f"• Avaliações anteriores: **{avaliacoes_feitas}**\n"
                          f"• Assaltos: **{assaltos}**\n"
                          f"• Abordagens: **{abordagens}**",
                 "inline": False},
                {"name": "🚓 Ações",
                 "value": f"• Perseguições: **{perseg}**\n• Detenções: **{detencoes_count}**",
                 "inline": False},
                {"name": "📡 Rádio",
                 "value": f"Nota: **{radio}/10**\nDescrição: {radio_desc}",
                 "inline": False},
                {"name": "🧍 Conduta",
                 "value": f"Nota: **{conduta}/10**\nDescrição: {conduta_desc}",
                 "inline": False},
                {"name": "🔒 Detenção 1",
                 "value": f"• Nota: **{nota_detencao}/10**\n• Leu direitos: **{det1_leu_direitos}**\n"
                          f"• Identificou: **{det1_identificou}**\n• Apreendeu objetos: **{det1_apreendeu}**",
                 "inline": False},
                {"name": "🔒 Detenção 2",
                 "value": f"• Nota: **{nota_detencao2}/10**\n• Leu direitos: **{det2_leu_direitos}**\n"
                          f"• Identificou: **{det2_identificou}**\n• Apreendeu objetos: **{det2_apreendeu}**",
                 "inline": False},
                {"name": "⚠️ Incidente",
                 "value": f"• Nota: **{nota_incidente}/10**\n• Crimes corretos: **{crimes_yesno}**\n"
                          f"• Foto: **{foto_yesno}**\n• Layout: **{layout_yesno}**\n"
                          f"• Descrição: **{descricao_yesno}**",
                 "inline": False},
                {"name": "❗ Erros no Incidente",
                 "value": incidente_erros if incidente_erros else "Nenhum informado.", "inline": False},
                {"name": "📝 Observação Final", "value": incidente_obs, "inline": False},
                {"name": "👮 Avaliador", "value": avaliador_info.get("tag", "Desconhecido"), "inline": False}
            ]
        }

        # Enviar webhook
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})

        # Salvar banco
        db.collection("avaliacoes").add({
            "avaliador": avaliador_info,
            "nome": nome,
            "tema": tema,
            "avaliacoes_feitas": avaliacoes_feitas,
            "assaltos": assaltos,
            "abordagens": abordagens,
            "perseg": perseg,
            "detencoes_count": detencoes_count,
            "radio": radio,
            "radio_desc": radio_desc,
            "conduta": conduta,
            "conduta_desc": conduta_desc,
            "nota_detencao": nota_detencao,
            "det1_leu_direitos": det1_leu_direitos,
            "det1_identificou": det1_identificou,
            "det1_apreendeu": det1_apreendeu,
            "conduta_desc2": conduta_desc2,
            "nota_detencao2": nota_detencao2,
            "det2_leu_direitos": det2_leu_direitos,
            "det2_identificou": det2_identificou,
            "det2_apreendeu": det2_apreendeu,
            "nota_incidente": nota_incidente,
            "crimes_yesno": crimes_yesno,
            "foto_yesno": foto_yesno,
            "layout_yesno": layout_yesno,
            "descricao_yesno": descricao_yesno,
            "incidente_erros": incidente_erros,
            "incidente_obs": incidente_obs
        })

        return {"success": True, "message": "Avaliação enviada com sucesso!"}

    except Exception as e:
        print("ERRO:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


# -----------------------------
# LOGIN COM DISCORD
# -----------------------------
@app.get("/login/discord")
async def login_discord():
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify"
    }
    url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


@app.get("/callback")
async def discord_callback(code: str):
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    token_res.raise_for_status()

    access_token = token_res.json()["access_token"]

    user_res = requests.get("https://discord.com/api/v10/users/@me", headers={
        "Authorization": f"Bearer {access_token}"
    })
    user_res.raise_for_status()

    user_info = user_res.json()

    response = RedirectResponse(url="/admin")
    response.set_cookie(key="discord_user", value=user_info["id"])
    return response


# -----------------------------
# LOGOUT
# -----------------------------
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("discord_user")
    return response


# -----------------------------
# ADMIN
# -----------------------------
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, discord_user: str = Cookie(None)):
    if not discord_user or discord_user not in ADMINS:
        return RedirectResponse(url="/")

    avaliacoes = [doc.to_dict() for doc in db.collection("avaliacoes").stream()]

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "avaliacoes": avaliacoes
    })


# -----------------------------
# EXPORTAR CSV
# -----------------------------
@app.get("/export_csv")
async def export_csv(discord_user: str = Cookie(None)):
    if not discord_user or discord_user not in ADMINS:
        return RedirectResponse(url="/")

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Nome", "Tema", "Avaliador", "Nota Conduta", "Nota Detenção", "Nota Incidente"])

    for doc in db.collection("avaliacoes").stream():
        d = doc.to_dict()
        writer.writerow([
            d.get("nome"),
            d.get("tema"),
            d.get("avaliador", {}).get("tag"),
            d.get("conduta"),
            d.get("nota_detencao"),
            d.get("nota_incidente")
        ])

    output.seek(0)

    return StreamingResponse(output, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=avaliacoes.csv"})


# -----------------------------
# FRONTEND
# -----------------------------
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
