from flask import Flask, request, session, redirect, url_for #type: ignore
from threading import Thread
import os
import requests

app = Flask("")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me")

@app.route("/", methods=["GET"])
def home():
   return """<!DOCTYPE html>
<html lang=\"es\"> 
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Goonbot • Acceso</title>
  <style>
    :root { --bg:#0f1226; --panel:#151938; --text:#e6e8f0; --muted:#9aa3b2; --accent:#6c8cff; --ok:#22c55e; --err:#ef4444; }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{margin:0;display:grid;place-items:center;background:radial-gradient(60% 80% at 80% 0%, #1b2148, transparent 60%), var(--bg);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Helvetica,Arial;padding:24px}
    .card{width:min(480px,92vw);background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:24px;box-shadow:0 20px 80px rgba(0,0,0,.35)}
    h1{margin:0 0 12px;font-size:clamp(22px,4vw,28px)}
    p{margin:0 0 18px;color:var(--muted)}
    label{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
    input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.06);color:var(--text);outline:none}
    .row{margin-bottom:14px}
    button{width:100%;padding:12px 14px;border-radius:10px;border:1px solid rgba(108,140,255,.5);background:linear-gradient(180deg, rgba(108,140,255,.9), rgba(108,140,255,.6));color:white;font-weight:600;cursor:pointer}
    .err{color:#fecaca;background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.35);padding:10px 12px;border-radius:10px;margin-bottom:14px;display:none}
  </style>
</head>
<body>
  <main class=\"card\"> 
    <h1>Acceso</h1>
    <p>Introduce usuario y contraseña para continuar.</p>
    <div id=\"err\" class=\"err\"></div>
    <form method=\"post\" action=\"/login\" onsubmit=\"return validate(event)\"> 
      <div class=\"row\"> 
        <label for=\"user\">Usuario</label>
        <input id=\"user\" name=\"user\" type=\"text\" placeholder=\"tsmcz\" required />
      </div>
      <div class=\"row\"> 
        <label for=\"password\">Contraseña</label>
        <input id=\"password\" name=\"password\" type=\"password\" required />
      </div>
      <button type=\"submit\">Entrar</button>
    </form>
  </main>
  <script>
    function validate(e){
      const u = document.getElementById('user').value.trim();
      if(u !== 'tsmcz'){ e.preventDefault(); const er = document.getElementById('err'); er.textContent = 'Usuario inválido'; er.style.display='block'; return false; }
      return true;
    }
  </script>
</body>
</html>"""

# --- Auth & Discord helpers ---
WEB_USER = os.getenv("WEB_USER", "tsmcz")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "goontime67")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")


def is_authed():
   return session.get("auth") is True


def discord_send_message(channel_id: str, content: str):
   if not DISCORD_TOKEN:
      return False, "DISCORD_TOKEN no configurado"
   url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
   headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
   resp = requests.post(url, headers=headers, json={"content": content})
   if resp.status_code in (200, 201):
      return True, "Mensaje enviado"
   try:
      data = resp.json()
      err = data.get('message') or data
   except Exception:
      err = resp.text
   return False, f"Error {resp.status_code}: {err}"


@app.route("/login", methods=["POST"])
def login():
   user = request.form.get("user", "").strip()
   pw = request.form.get("password", "")
   if user != WEB_USER or pw != WEB_PASSWORD:
      return redirect(url_for('home'))
   session['auth'] = True
   return redirect(url_for('console'))


@app.route("/console", methods=["GET"])
def console():
   if not is_authed():
      return redirect(url_for('home'))
   return """<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Goonbot • Consola</title>
  <style>
    :root { --bg:#0f1226; --panel:#151938; --text:#e6e8f0; --muted:#9aa3b2; --accent:#6c8cff; }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{margin:0;display:grid;grid-template-rows:auto 1fr; background:radial-gradient(60% 80% at 80% 0%, #1b2148, transparent 60%), var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Helvetica,Arial}
    header{padding:16px 20px;background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.08)}
    .wrap{max-width:940px;margin:0 auto;width:100%;}
    h1{margin:0;font-size:18px;letter-spacing:.3px}
    .panel{margin:16px auto;max-width:940px;width:calc(100% - 24px); background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02)); border:1px solid rgba(255,255,255,.08); border-radius:12px; overflow:hidden}
    .toolbar{display:flex;gap:12px;padding:12px;border-bottom:1px solid rgba(255,255,255,.08)}
    input,textarea{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);color:var(--text);border-radius:10px;padding:10px 12px;outline:none}
    input{min-width:240px}
    textarea{width:100%;min-height:120px;resize:vertical}
    button{padding:10px 14px;border-radius:10px;border:1px solid rgba(108,140,255,.5);background:linear-gradient(180deg, rgba(108,140,255,.9), rgba(108,140,255,.6));color:white;font-weight:600;cursor:pointer}
    .console{padding:12px;max-height:50vh;overflow:auto;font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; background:rgba(0,0,0,.25)}
    .line{padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.06)}
    .ok{color:#86efac}
    .err{color:#fca5a5}
  </style>
</head>
<body>
  <header>
    <div class=\"wrap\"> 
      <h1>Goonbot • Consola</h1>
    </div>
  </header>

  <div class=\"panel\"> 
    <div class=\"toolbar\"> 
      <input id=\"channel\" type=\"text\" placeholder=\"Channel ID\" />
      <button onclick=\"sendMsg()\">Enviar</button>
    </div>
    <div style=\"padding:12px\"> 
      <textarea id=\"content\" placeholder=\"Escribe el mensaje...\"></textarea>
    </div>
    <div id=\"console\" class=\"console\"></div>
  </div>

  <script>
    async function sendMsg(){
      const channel = document.getElementById('channel').value.trim();
      const content = document.getElementById('content').value;
      if(!channel || !content){ log('Faltan campos', 'err'); return; }
      try{
        const resp = await fetch('/send', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel_id: channel, content}) });
        const data = await resp.json();
        if(data.ok){ log('Enviado: ' + data.detail, 'ok'); }
        else{ log('Error: ' + data.detail, 'err'); }
      }catch(e){ log('Error de red', 'err'); }
    }
    function log(msg, cls){
      const el = document.getElementById('console');
      const line = document.createElement('div');
      line.className = 'line ' + (cls||'');
      line.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
      el.prepend(line);
    }
  </script>
</body>
</html>"""


@app.route("/send", methods=["POST"])
def send():
   if not is_authed():
      return {"ok": False, "detail": "No autorizado"}, 401
   data = request.get_json(silent=True) or {}
   channel_id = str(data.get("channel_id", "")).strip()
   content = str(data.get("content", ""))
   if not channel_id or not content:
      return {"ok": False, "detail": "Parámetros inválidos"}, 400
   ok, detail = discord_send_message(channel_id, content)
   status = 200 if ok else 400
   return {"ok": ok, "detail": detail}, status


def run():
   app.run(host="0.0.0.0", port=8080)


def keep_alive():
   t = Thread(target=run)
   t.start()

