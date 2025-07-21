# panel_admin.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse
import json, os
from config import ADMIN_PASSWORD
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="fluxionadminsecret")

templates = Jinja2Templates(directory="templates")

def load_json(filename):
    return json.load(open(filename, "r")) if os.path.exists(filename) else {}

def save_json(filename, data):
    json.dump(data, open(filename, "w"))

@app.get("/admin", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/admin", response_class=HTMLResponse)
def login_post(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session['admin'] = True
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Password salah!"})

@app.get("/admin/dashboard")
def dashboard(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/admin", status_code=302)

    poin = load_json("data_poin.json")
    penarikan = load_json("penarikan.json")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "poin": poin,
        "penarikan": penarikan
    })

@app.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/approve")
def approve(request: Request, user_id: str = Form(...)):
    penarikan = load_json("penarikan.json")
    for trx in penarikan.get(user_id, []):
        if "status" not in trx:
            trx["status"] = "✅ Disetujui"
            trx["approved_time"] = datetime.now().isoformat()
            break
    save_json("penarikan.json", penarikan)
    return RedirectResponse("/admin/dashboard", status_code=302)

@app.post("/admin/tolak")
def tolak(request: Request, user_id: str = Form(...)):
    penarikan = load_json("penarikan.json")
    for trx in penarikan.get(user_id, []):
        if "status" not in trx:
            trx["status"] = "❌ Ditolak"
            trx["rejected_time"] = datetime.now().isoformat()
            break
    save_json("penarikan.json", penarikan)
    return RedirectResponse("/admin/dashboard", status_code=302)
