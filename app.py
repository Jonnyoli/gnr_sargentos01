import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import firebase_admin
from firebase_admin import credentials, firestore

from requests_oauthlib import OAuth2Session

# ---------------------------------------------------
# 🔐 Variáveis de ambiente
# ---------------------------------------------------

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("FRONTEND_URL") + "/callback"
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ADMINS = os.getenv("ADMINS", "").split(",")

# ---------------------------------------------------
# 🔥 Firestore
# ---------------------------------------------------

cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.environ["FIRESTORE_PROJECT_ID"],
    "private_key_id": os.environ["FIRESTORE_PRIVATE_KEY_ID"],
    "private_key": os.environ["FIRESTORE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": os.environ["FIRESTORE_CLIENT_EMAIL"],
    "client_id": os.environ["FIRESTORE_CLIENT_ID"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": ""
})

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---------------------------------------------------
# 🌐 FastAPI
# ---------------------------------------------------

app = FastAPI()

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------
# 🔗 Rota inicial
# ---------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------
# 🔐 Login Discord
# ---------------------------------------------------

def discord_oauth():
    return OAuth2Session(
        DISCORD_CLIENT_ID,
        redirect_uri=DISCORD_REDIRECT_URI,
        scope=["identify"]
    )


@app.get("/login")
async def login():
    oauth = discord_oauth()
    authorization_url, _ = oauth.authorization_url("https://discord.com/api/oauth2/authorize")
    return RedirectResponse(authorization_url)


@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/")

    oauth = discord_oauth()
    token = oauth.fetch_token(
        "https://discord.com/api/oauth2/token",
        code=code,
        client_secret=DISCORD_CLIENT_SECRET
    )

    user = oauth.get("https://discord.com/api/users/@me").json()
    user_id = user["id"]

    # guardar na sessão (em cookie simples)
    response = RedirectResponse("/admin")
    response.set_cookie("user_id", user_id)

    return response


# ---------------------------------------------------
# 👮 Painel Admin
# ---------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):

    user_id = request.cookies.get("user_id")

    if user_id not in ADMINS:
        return HTMLResponse("<h1>Acesso negado</h1>")

    # buscar avaliações no Firestore
    docs = db.collection("avaliacoes").stream()
    avaliacoes = [doc.to_dict() for doc in docs]

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "avaliacoes": avaliacoes
    })


# ---------------------------------------------------
# 📝 API para receber formulários
# ---------------------------------------------------

@app.post("/submit")
async def submit(data: dict):
    db.collection("avaliacoes").add(data)
    return {"status": "success"}
