# app.py — FastAPI + Firestore + Discord OAuth (atualizado)
import os
import requests
import urllib.parse
import csv
from io import StringIO
from typing import Optional
from fastapi import FastAPI, Form, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import firebase_admin
from firebase_admin import credentials, firestore

# -----------------------------
# CONFIG / VARIÁVEIS DE AMBIENTE
# -----------------------------
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI") or (os.getenv("FRONTEND_URL") + "/callback" if os.getenv("FRONTEND_URL") else None)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")           # usado para buscar info do utilizador via bot token
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")  # webhook para enviar notificações
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ADMINS = [a.strip() for a in os.getenv("ADMINS", "").split(",") if a.strip()]

# Verificações iniciais — logs simples para debug em deploy
required_envs = {
    "DISCORD_CLIENT_ID": DISCORD_CLIENT_ID,
    "DISCORD_CLIENT_SECRET": DISCORD_CLIENT_SECRET,
    "DISCORD_REDIRECT_URI / FRONTEND_URL": DISCORD_REDIRECT_URI,
    "FIRESTORE_PROJECT_ID": os.getenv("FIRESTORE_PROJECT_ID"),
    "FIRESTORE_CLIENT_EMAIL": os.getenv("FIRESTORE_CLIENT_EMAIL"),
    "FIRESTORE_PRIVATE_KEY": os.getenv("FIRESTORE_PRIVATE_KEY") is not None,
    "FIRESTORE_PRIVATE_KEY_ID": os.getenv("FIRESTORE_PRIVATE_KEY_ID"),
    "FIRESTORE_CLIENT_ID": os.getenv("FIRESTORE_CLIENT_ID"),
}
for k, v in required_envs.items():
    if not v:
        print(f"[WARN] Variável de ambiente ausente ou inválida: {k}")

# -----------------------------
# FIRESTORE (constrói o credential a partir de ENV)
# -----------------------------
if os.getenv("FIRESTORE_PRIVATE_KEY"):
    service_account = {
        "type": "service_account",
        "project_id": os.environ.get("FIRESTORE_PROJECT_ID"),
        "private_key_id": os.environ.get("FIRESTORE_PRIVATE_KEY_ID"),
        "private_key": os.environ.get("FIRESTORE_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.environ.get("FIRESTORE_CLIENT_EMAIL"),
        "client_id": os.environ.get("FIRESTORE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.environ.get("FIRESTORE_CLIENT_X509_CERT_URL", "")
    }

    try:
        cred = credentials.Certificate(service_account)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print("[ERRO] Não foi possível inicializar o Firebase:", e)
        db = None
else:
    print("[ERRO] FIRESTORE_PRIVATE_KEY não definida. Firestore desactivado.")
    db = None

# -----------------------------
# FastAPI + templates / static
# -----------------------------
app = FastAPI()
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
templates = Jinja2Templates(directory="templates")

# -----------------------------
# Helper: validar URL
# -----------------------------
def is_valid_url(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

# -----------------------------
# Função para buscar usuário no Discord via Bot
# -----------------------------
def buscar_user_discord(user_id: Optional[str]):
    if not user_id:
        return {"id": None, "username": None, "global_name": None, "tag": None}

    if not DISCORD_BOT_TOKEN:
        return {"id": user_id, "username": None, "global_name": None, "tag": f"{user_id}"}

    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        r = requests.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
        return {
            "id": user_id,
            "username": data.get("username"),
            "global_name": data.get("global_name"),
            "tag": f"{data.get('username')}#{data.get('discriminator')}" if data.get("username") and data.get("discriminator") else f"{user_id}"
        }
    except Exception as e:
        print("[WARN] Falha ao buscar user via bot:", e)
        return {"id": user_id, "username": None, "global_name": None, "tag": f"{user_id}"}

# -----------------------------
# Rotas básicas (home, login, logout, admin)
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login/discord")
async def login_discord():
    if not is_valid_url(DISCORD_REDIRECT_URI):
        return HTMLResponse("<h1>Redirect URI inválido</h1>", status_code=500)
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify"
    }
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}")

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
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers, timeout=10)
    r.raise_for_status()
    access_token = r.json().get("access_token")
    r2 = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"}, timeout=8)
    r2.raise_for_status()
    user_info = r2.json()
    response = RedirectResponse(url="/admin")
    response.set_cookie(key="discord_user", value=user_info.get("id"))
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("discord_user")
    return response

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    user_id = request.cookies.get("discord_user")
    if not user_id:
        return RedirectResponse(url="/")
    if ADMINS and user_id not in ADMINS:
        return HTMLResponse("<h1>Acesso negado</h1>", status_code=403)
    avaliacoes = []
    if db:
        try:
            avaliacoes = [doc.to_dict() for doc in db.collection("avaliacoes").stream()]
        except Exception as e:
            print("[WARN] Erro ao ler avaliações:", e)
    return templates.TemplateResponse("admin.html", {"request": request, "avaliacoes": avaliacoes})

# -----------------------------
# Submit form atualizado para gravar Avaliador corretamente
# -----------------------------
@app.post("/submit")
async def submit_form(
    request: Request,
    user_id: str = Form(default=None),
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
        # Pega o ID do cookie se não veio via form
        if not user_id:
            user_id = request.cookies.get("discord_user")
        if not user_id:
            return JSONResponse(status_code=400, content={"error": "user_id ausente"})

        # Obtém info do usuário (OAuth confiável)
        avaliador_info = buscar_user_discord(user_id)
        if not avaliador_info.get("username"):
            # fallback: pega só o ID
            avaliador_info["username"] = None
            avaliador_info["global_name"] = None
            avaliador_info["tag"] = user_id

        from datetime import datetime
        data = {
            "avaliador": avaliador_info,
            "nome": nome,
            "tema": tema,
            "avaliacoes_feitas": int(avaliacoes_feitas),
            "assaltos": int(assaltos),
            "abordagens": int(abordagens),
            "perseg": int(perseg),
            "detencoes_count": int(detencoes_count),
            "radio": int(radio),
            "radio_desc": radio_desc,
            "conduta": int(conduta),
            "conduta_desc": conduta_desc,
            "nota_detencao": int(nota_detencao),
            "det1_leu_direitos": det1_leu_direitos,
            "det1_identificou": det1_identificou,
            "det1_apreendeu": det1_apreendeu,
            "conduta_desc2": conduta_desc2,
            "nota_detencao2": int(nota_detencao2),
            "det2_leu_direitos": det2_leu_direitos,
            "det2_identificou": det2_identificou,
            "det2_apreendeu": det2_apreendeu,
            "nota_incidente": int(nota_incidente),
            "crimes_yesno": crimes_yesno,
            "foto_yesno": foto_yesno,
            "layout_yesno": layout_yesno,
            "descricao_yesno": descricao_yesno,
            "incidente_erros": incidente_erros,
            "incidente_obs": incidente_obs,
            "data_submissao": datetime.utcnow()
        }

        if db:
            db.collection("avaliacoes").add(data)

        # webhook
        if DISCORD_WEBHOOK_URL:
            embed = {
                "title": "📋 Nova Avaliação de Guarda",
                "description": f"Avaliação enviada por <@{user_id}>",
                "color": 0x00FF00,
                "fields": [
                    {"name": "👤 Nome do Avaliado", "value": nome, "inline": False},
                    {"name": "📌 Tema", "value": tema, "inline": False},
                    {"name": "📊 Geral", "value": f"• Avaliações anteriores: **{avaliacoes_feitas}**\n• Assaltos: **{assaltos}**\n• Abordagens: **{abordagens}**", "inline": False},
                    {"name": "🚓 Ações", "value": f"• Perseguições: **{perseg}**\n• Detenções: **{detencoes_count}**", "inline": False},
                    {"name": "📡 Rádio", "value": f"Nota: **{radio}/10**\nDescrição: {radio_desc}", "inline": False},
                    {"name": "🧍 Conduta", "value": f"Nota: **{conduta}/10**\nDescrição: {conduta_desc}", "inline": False},
                    {"name": "🔒 Detenção 1", "value": f"• Nota: **{nota_detencao}/10**\n• Leu direitos: **{det1_leu_direitos}**\n• Identificou: **{det1_identificou}**\n• Apreendeu objetos: **{det1_apreendeu}**", "inline": False},
                    {"name": "🔒 Detenção 2", "value": f"• Nota: **{nota_detencao2}/10**\n• Leu direitos: **{det2_leu_direitos}**\n• Identificou: **{det2_identificou}**\n• Apreendeu objetos: **{det2_apreendeu}**", "inline": False},
                    {"name": "⚠️ Incidente", "value": f"• Nota: **{nota_incidente}/10**\n• Crimes corretos: **{crimes_yesno}**\n• Foto: **{foto_yesno}**\n• Layout: **{layout_yesno}**\n• Descrição: **{descricao_yesno}**", "inline": False},
                    {"name": "❗ Erros no Incidente", "value": incidente_erros if incidente_erros else "Nenhum informado.", "inline": False},
                    {"name": "📝 Observação Final", "value": incidente_obs, "inline": False},
                    {"name": "👮 Avaliador", "value": avaliador_info.get("tag", "Desconhecido"), "inline": False},
                ]
            }
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=8)

        return {"success": True, "message": "Avaliação enviada!"}

    except Exception as e:
        print("[ERRO] submit_form:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

# -----------------------------
# Export CSV
# -----------------------------
@app.get("/export_csv")
async def export_csv(discord_user: str = Cookie(None)):
    if not discord_user or (ADMINS and discord_user not in ADMINS):
        return RedirectResponse(url="/")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Nome", "Tema", "Avaliador", "Nota Conduta", "Nota Detenção", "Nota Incidente"])

    if db:
        try:
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
        except Exception as e:
            print("[WARN] export_csv error:", e)

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=avaliacoes.csv"})
