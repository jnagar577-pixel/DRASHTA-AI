import os, re, json, time, secrets, hmac, collections
from flask import Flask, request, jsonify, session, render_template
from . import kb, consult, llm

def create_app(cfg=None):
    cfg = cfg or {}
    app = Flask(__name__)
    app.config["SECRET_KEY"] = cfg.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    dbpath = cfg.get("DB_PATH") or os.environ.get("DRASHTA_DB", "data/drashta.db")
    admin_pw = cfg.get("ADMIN_PASSWORD") if "ADMIN_PASSWORD" in cfg else os.environ.get("ADMIN_PASSWORD", "")
    hits = collections.defaultdict(collections.deque)

    def db():
        con = kb.connect(dbpath); return con
    with db() as con:
        kb.ingest_dir(con, os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge"))

    def limited(key, n, per):
        q = hits[key]; now = time.time()
        while q and q[0] < now - per: q.popleft()
        if len(q) >= n: return True
        q.append(now); return False

    @app.errorhandler(Exception)
    def err(e):
        code = getattr(e, "code", 500)
        if code == 500:
            try: kb.log_event(db(), "error", "%s" % type(e).__name__)
            except Exception: pass
        return jsonify(error="Something went wrong." if code == 500 else getattr(e, "name", "Error")), code

    @app.get("/")
    def index(): return render_template("index.html")

    @app.get("/api/config")
    def config():
        s = kb.get_settings(db()); return jsonify(mode="live" if llm.is_live(s) else "demo", name=s["assistant_name"])

    @app.post("/api/session")
    def new_session():
        if limited("s" + request.remote_addr, 20, 60): return jsonify(error="Too many requests"), 429
        s = kb.get_settings(db()); sid = secrets.token_hex(16); now = time.time()
        con = db(); con.execute("INSERT INTO sessions VALUES(?,?,?,?)", (sid, now, now, json.dumps(consult.new_state()))); con.commit()
        return jsonify(session_id=sid, reply=s["welcome"], mode="live" if llm.is_live(s) else "demo")

    @app.post("/api/chat")
    def chat():
        if limited("c" + request.remote_addr, 40, 60): return jsonify(error="Too many requests"), 429
        body = request.get_json(silent=True) or {}; sid = str(body.get("session_id", "")); msg = str(body.get("message", ""))
        if not re.fullmatch(r"[0-9a-f]{32}", sid) or not 0 < len(msg) <= 500: return jsonify(error="Invalid input"), 400
        con = db(); row = con.execute("SELECT state FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row: return jsonify(error="Session not found or deleted"), 404
        state = json.loads(row["state"]); cfgs = kb.get_settings(con)
        reply = consult.handle(state, msg, cfgs, con)
        con.execute("UPDATE sessions SET state=?, updated=? WHERE id=?", (json.dumps(state), time.time(), sid)); con.commit()
        return jsonify(reply=reply, mode="live" if llm.is_live(cfgs) else "demo")

    @app.delete("/api/session/<sid>")
    def del_session(sid):
        if not re.fullmatch(r"[0-9a-f]{32}", sid): return jsonify(error="Invalid input"), 400
        con = db(); n = con.execute("DELETE FROM sessions WHERE id=?", (sid,)).rowcount; con.commit(); return jsonify(deleted=n)

    # ---- admin ----
    def need_admin():
        if not admin_pw: return jsonify(error="Admin disabled: set ADMIN_PASSWORD"), 403
        if not session.get("admin") or request.headers.get("X-Requested-With") != "drashta": return jsonify(error="Unauthorized"), 401
    @app.get("/admin")
    def admin_page(): return render_template("admin.html")
    @app.post("/admin/login")
    def login():
        if not admin_pw: return jsonify(error="Admin disabled: set ADMIN_PASSWORD"), 403
        if limited("l" + request.remote_addr, 5, 300): return jsonify(error="Too many attempts"), 429
        pw = str((request.get_json(silent=True) or {}).get("password", ""))
        if hmac.compare_digest(pw.encode(), admin_pw.encode()): session["admin"] = True; return jsonify(ok=True)
        return jsonify(error="Wrong password"), 401
    @app.post("/admin/logout")
    def logout(): session.clear(); return jsonify(ok=True)

    @app.route("/admin/api/settings", methods=["GET", "PUT"])
    def a_settings():
        r = need_admin()
        if r: return r
        con = db()
        if request.method == "PUT":
            for k, v in (request.get_json(silent=True) or {}).items():
                try: kb.set_setting(con, k, v)
                except KeyError: return jsonify(error="Unknown setting: %s" % k), 400
        s = kb.get_settings(con); s["api_key_configured"] = llm.is_live(s) or bool(os.environ.get("ANTHROPIC_API_KEY")); return jsonify(s)
    @app.get("/admin/api/knowledge")
    def a_kb():
        r = need_admin()
        if r: return r
        return jsonify(records=[dict(id=x["id"], source=x["source_id"], page=x["page"], verification=x["verification"], enabled=bool(x["enabled"])) for x in db().execute("SELECT * FROM records ORDER BY id")], coverage=kb.coverage(db()))
    @app.post("/admin/api/knowledge/<rid>/toggle")
    def a_toggle(rid):
        r = need_admin()
        if r: return r
        con = db(); con.execute("UPDATE records SET enabled=1-enabled WHERE id=?", (rid,)); con.commit(); return jsonify(ok=True)
    @app.get("/admin/api/export")
    def a_export():
        r = need_admin()
        if r: return r
        return jsonify([json.loads(x["body"]) for x in db().execute("SELECT body FROM records ORDER BY id")])
    @app.post("/admin/api/import")
    def a_import():
        r = need_admin()
        if r: return r
        data = request.get_json(silent=True)
        if not isinstance(data, list): return jsonify(error="Expected a JSON list of records"), 400
        con = db(); n = 0
        for rec in data:
            if isinstance(rec, dict) and re.fullmatch(r"[A-Za-z0-9_\-]{3,60}", str(rec.get("id", ""))): kb.upsert(con, {k: str(v) for k, v in rec.items()}); n += 1
        return jsonify(imported=n)
    @app.get("/admin/api/events")
    def a_events():
        r = need_admin()
        if r: return r
        return jsonify([dict(x) for x in db().execute("SELECT ts,level,msg FROM events ORDER BY id DESC LIMIT 100")])
    @app.delete("/admin/api/sessions")
    def a_del_sessions():
        r = need_admin()
        if r: return r
        con = db(); n = con.execute("DELETE FROM sessions").rowcount; con.commit(); return jsonify(deleted=n)
    return app

if __name__ == "__main__":
    create_app().run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
