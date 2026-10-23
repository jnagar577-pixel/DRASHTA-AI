"""SQLite storage: knowledge records, settings, sessions, error events."""
import re, json, sqlite3, time, glob, os

SCHEMA = """CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, pillar TEXT, source_id TEXT, enabled INTEGER DEFAULT 1,
 verification TEXT, page TEXT, body TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created REAL, updated REAL, state TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, level TEXT, msg TEXT);"""

DEFAULTS = {"assistant_name": "Drashta AI",
 "welcome": "Namaskar, main Drashta AI hoon. Aapka name kya hai?",
 "instructions": "Use only the supplied chart data and cited source records. Never invent placements or citations. Do not make deterministic or frightening predictions.",
 "provider": "anthropic", "model": "claude-sonnet-5-5", "ayanamsha": "lahiri",
 "topics_enabled": ["career", "marriage", "finance", "spiritual"]}

# Source families and their honest status (shown in the admin coverage view)
SOURCES = {"BNN-RGR": "supplied; OCR text layer; introduction only extracted so far",
 "NADI-JK": "supplied; Hindi text layer corrupted; 6 records (pp. 5-6, 10-11, 33, 40)",
 "BPHS-GDP": "supplied; image-only scan; NO records yet (needs Hindi/Sanskrit OCR or page-by-page transcription)",
 "OSHO-ASHTA": "supplied; Hindi text layer corrupted; NO records yet",
 "OSHO-JD": "supplied; Hindi text layer corrupted; NO records yet",
 "OSHO-ASTRO": "NOT SUPPLIED"}

def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row; db.executescript(SCHEMA); return db

def parse_md(text):
    recs = []
    for blk in re.findall(r"```yaml\n(.*?)```", text, re.S):
        r = {}
        for line in blk.splitlines():
            m = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if m: r[m.group(1)] = m.group(2).strip()
        if r.get("id"): recs.append(r)
    return recs

def upsert(db, r):
    page = r.get("printed_page", "")
    txt = " ".join(r.get(k, "") for k in ("original_term", "source_supported_summary", "rule_or_concept", "english_explanation")).lower()
    old = db.execute("SELECT enabled FROM records WHERE id=?", (r["id"],)).fetchone()
    db.execute("REPLACE INTO records VALUES(?,?,?,?,?,?,?,?)", (r["id"], r.get("pillar", ""), r.get("source_id", ""),
        old["enabled"] if old else 1, r.get("verification_status", "unverified"), page, json.dumps(r, ensure_ascii=False), txt))
    db.commit()

def ingest_dir(db, folder):
    n = 0
    for f in sorted(glob.glob(os.path.join(folder, "*.md"))):
        with open(f, encoding="utf-8") as fh: recs = parse_md(fh.read())
        for r in recs: upsert(db, r); n += 1
    return n

def get_record(db, rid):
    row = db.execute("SELECT * FROM records WHERE id=? AND enabled=1", (rid,)).fetchone()
    return json.loads(row["body"]) if row else None

def search(db, query, limit=5):
    toks = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
    scored = []
    for row in db.execute("SELECT * FROM records WHERE enabled=1"):
        s = sum(row["text"].count(t) for t in toks)
        if s: scored.append((s, json.loads(row["body"])))
    return [r for _, r in sorted(scored, key=lambda x: -x[0])[:limit]]

def get_settings(db):
    s = dict(DEFAULTS)
    for row in db.execute("SELECT k,v FROM settings"): s[row["k"]] = json.loads(row["v"])
    return s

def set_setting(db, k, v):
    if k not in DEFAULTS: raise KeyError(k)
    db.execute("REPLACE INTO settings VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False))); db.commit()

def log_event(db, level, msg):
    db.execute("INSERT INTO events(ts,level,msg) VALUES(?,?,?)", (time.time(), level, msg[:500])); db.commit()

def coverage(db):
    out = {}
    for sid, note in SOURCES.items():
        rows = db.execute("SELECT verification, enabled FROM records WHERE source_id=?", (sid,)).fetchall()
        out[sid] = {"note": note, "records": len(rows), "enabled": sum(r["enabled"] for r in rows),
                    "verified_visual": sum(1 for r in rows if r["verification"].startswith("source_verified"))}
    return out
