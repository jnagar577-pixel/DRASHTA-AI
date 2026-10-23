"""Conversation state machine + rule evaluation. Chart facts come only from chart.py."""
import re, json, datetime as dt
from . import chart as C, places, kb, llm

TOPICS = {"1": "career", "2": "marriage", "3": "finance", "4": "spiritual"}
LABEL = {"career": "Career", "marriage": "Marriage", "finance": "Finance", "spiritual": "Spiritual Talk: Osho philosophy"}
# topic -> verified record ids the evaluator below actually applies
TOPIC_RECORDS = {"career": ["DRASHTA-BNN-004", "DRASHTA-BNN-005", "DRASHTA-BNN-006", "DRASHTA-BNN-001"],
                 "marriage": ["DRASHTA-BNN-004", "DRASHTA-BNN-006"], "finance": [], "spiritual": []}
KARAKA = {"career": "Saturn", "marriage": "Venus"}  # per DRASHTA-BNN-004 (R. G. Rao intro, p. iii)

def new_state(): return {"step": "name", "data": {}, "chart": None, "topic": None, "history": []}

def parse_date(s):
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            d = dt.datetime.strptime(s.strip(), f).date()
            if dt.date(1900, 1, 1) <= d <= dt.date.today(): return d
            return None
        except ValueError: pass
    return None

def parse_time(s):
    m = re.match(r"^\s*(\d{1,2})\s*[:.\s]\s*(\d{2})\s*(am|pm|a\.m\.|p\.m\.)\s*$", s.strip(), re.I)
    if not m: return None
    return int(m.group(1)), int(m.group(2)), m.group(3)[0].upper() + "M"

def _fmt_chart(ch):
    L = ch["lagna"]; lines = ["D1 (Lagna) chart - Lagna: %s %s, lord %s in house %d, %s pada %d" % (L["sign"], L["dms"], L["lord"], L["lord_house"], L["nakshatra"], L["pada"])]
    for p, v in ch["planets"].items():
        flags = [x for x in ("retrograde" if v["retrograde"] else "", "combust" if v.get("combust") else "") if x]
        lines.append("%s: %s %s | house %d | %s pada %d | %s%s" % (p, v["sign"], v["dms"], v["house"], v["nakshatra"], v["pada"], v["dignity"], (" | " + ", ".join(flags)) if flags else ""))
    lines.append("Houses: " + "; ".join("H%d %s(%s)%s" % (h["house"], h["sign"], h["lord"], ("[" + ",".join(h["planets"]) + "]") if h["planets"] else "") for h in ch["houses"]))
    s = ch["settings"]; lines.append("Settings: %s ayanamsha (%.4f deg), %s, %s, %s. Ephemeris: %s." % (s["ayanamsha"], s["ayanamsha_value_deg"], s["node"], s["house_system"], "D1 only", s["ephemeris"]))
    return "\n".join(lines)

def planet_facts(ch, p):
    pl = ch["planets"][p]; si = C.SIGNS.index(pl["sign"]); lord = C.LORDS[si]
    on = lambda sign: [q for q, x in ch["planets"].items() if x["sign"] == sign and q != p]
    s7, s12 = C.SIGNS[(si + 6) % 12], C.SIGNS[(si + 11) % 12]
    exch = lord != p and C.LORDS[C.SIGNS.index(ch["planets"][lord]["sign"])] == p
    return {"planet": p, "sign": pl["sign"], "house": pl["house"], "dignity": pl["dignity"], "retrograde": pl["retrograde"],
        "combust": pl.get("combust", False), "sign_lord": lord, "sign_lord_house": ch["planets"][lord]["house"],
        "same_sign": on(pl["sign"]), "seventh_sign": s7, "in_seventh": on(s7), "twelfth_sign": s12, "in_twelfth": on(s12), "sign_exchange": exch,
        "aspected_by": [q for q, a in ch["aspects"].items() if q != p and pl["house"] in a["aspect_houses"]]}

def topic_report(topic, ch, db):
    out = []; cites = []
    if topic in KARAKA:
        p = KARAKA[topic]; f = planet_facts(ch, p)
        out.append("CALCULATED FACTS (D1): %s is in %s, house %d; dignity: %s; %s%s. Sign lord %s sits in house %d. Same sign: %s. In the 7th sign (%s): %s. In the 12th sign (%s): %s. Sign exchange: %s. Aspected by (graha drishti): %s." % (
            p, f["sign"], f["house"], f["dignity"], "retrograde" if f["retrograde"] else "direct", ", combust" if f["combust"] else "",
            f["sign_lord"], f["sign_lord_house"], ", ".join(f["same_sign"]) or "none", f["seventh_sign"], ", ".join(f["in_seventh"]) or "none",
            f["twelfth_sign"], ", ".join(f["in_twelfth"]) or "none", "yes" if f["sign_exchange"] else "no", ", ".join(f["aspected_by"]) or "none"))
        for rid in TOPIC_RECORDS[topic]:
            r = kb.get_record(db, rid)
            if r: cites.append("[%s | %s, p. %s | %s] %s" % (r["id"], r["source_title"], r["printed_page"], r["verification_status"], r["source_supported_summary"]))
        out.append("SOURCE-BACKED RULES APPLIED:\n" + "\n".join(cites))
        if topic == "career":
            out.append("SOURCE NOTE: the same source says Saturn is neutral and results depend on his position, and that Jupiter's transit modifies results. Transits are NOT computed in this version, so that factor is unassessed.")
        out.append("INFERENCE (not a source rule): the verified records identify %s as the significator for %s and list what to examine around it; they contain no verified statement mapping this specific placement to an outcome. So no outcome is predicted. Use the facts above as the factors a Nadi reader would weigh." % (p, topic))
    elif topic == "finance":
        l2, l11 = ch["houses"][1], ch["houses"][10]
        out.append("CALCULATED FACTS (D1): 2nd house %s (lord %s in house %d); 11th house %s (lord %s in house %d)." % (l2["sign"], l2["lord"], ch["planets"][l2["lord"]]["house"], l11["sign"], l11["lord"], ch["planets"][l11["lord"]]["house"]))
        out.append("NO VERIFIED SOURCE RULE: the knowledge base has no verified finance rule yet (the BPHS scan is not transcribed and the supplied Nadi sources have no finance rule recorded). Nothing about money outcomes is predicted.")
    else:
        out.append("NO VERIFIED OSHO RECORDS YET: the supplied Osho PDFs have corrupted Hindi text layers and the astrology book was not supplied, so I cannot attribute specific views to Osho. I can hold a general reflective conversation, clearly labelled DRASHTA-REFLECTION and not Osho's words. For example: what would change in how you act today if you watched your pattern as a witness instead of as a verdict?")
    out.append("This is an interpretive reading of a calculated chart, not a scientific prediction or guarantee.")
    return "\n\n".join(out)

def _menu(cfg):
    en = cfg["topics_enabled"]
    return "What would you like to explore?\n" + "\n".join("%s. %s" % (k, LABEL[v]) for k, v in TOPICS.items() if v in en)

def handle(state, msg, cfg, db):
    msg = (msg or "").strip(); d = state["data"]; step = state["step"]
    if msg.lower() in ("restart", "reset"):
        state.clear(); state.update(new_state()); return cfg["welcome"]
    if step == "name":
        if not re.match(r"^[^\W\d_][\w .'\-]{0,59}$", msg, re.U): return "Kripya apna naam likhein (letters only, up to 60 characters)."
        d["name"] = msg; state["step"] = "dob"
        return "Dhanyavaad, %s. Aapki date of birth batayein (DD-MM-YYYY, day first)." % msg
    if step == "dob":
        dd = parse_date(msg)
        if not dd: return "Date samajh nahi aayi. Format: DD-MM-YYYY (e.g. 15-08-1947), between 1900 and today."
        d["dob"] = dd.isoformat(); state["step"] = "place"; return "Birthplace batayein (city name, or 'lat,lon,Timezone' e.g. 23.26,77.41,Asia/Kolkata)."
    if step == "place":
        pl = places.resolve(msg)
        if not pl: return "Yeh place mere offline table mein nahi mila. Please 'latitude,longitude,Timezone' likhein (e.g. 26.85,80.95,Asia/Kolkata) ya kisi paas ke bade shehar ka naam."
        d["place"] = pl; state["step"] = "time"; return "Birth time batayein: hour, minute aur AM/PM (e.g. 10:30 PM)."
    if step == "time":
        t = parse_time(msg)
        if not t: return "Time samajh nahi aaya. Format: 10:30 PM (hour, minute, AM/PM zaroori hai)."
        try: dd = dt.date.fromisoformat(d["dob"]); C.local_to_utc(dd.year, dd.month, dd.day, t[0], t[1], t[2], d["place"]["tz"])
        except C.ChartError as ex: return str(ex)
        d["time"] = list(t); state["step"] = "exact"; return "Kya yeh birth time exact hai ya approximate? (exact / approximate)"
    if step == "exact":
        low = msg.lower()
        if low.startswith(("exact", "e")): d["exact"] = True
        elif low.startswith(("appr", "a")): d["exact"] = False
        else: return "Please reply 'exact' ya 'approximate'."
        state["step"] = "confirm"; t = d["time"]; pl = d["place"]
        return "Please confirm:\nName: %s\nDate of birth: %s\nBirthplace: %s (lat %.4f, lon %.4f, tz %s)\nBirth time: %02d:%02d %s (%s)\nSahi hai? (yes / no)" % (
            d["name"], d["dob"], pl["name"], pl["lat"], pl["lon"], pl["tz"], t[0], t[1], t[2], "exact" if d["exact"] else "approximate")
    if step == "confirm":
        if msg.lower() in ("no", "n", "nahi", "nahin"): state["step"] = "dob"; return "Theek hai, date of birth dobara batayein (DD-MM-YYYY)."
        if msg.lower() not in ("yes", "y", "haan", "han", "ha", "sahi"): return "Please reply 'yes' ya 'no'."
        dd = dt.date.fromisoformat(d["dob"]); t = d["time"]; pl = d["place"]
        try:
            utc, _ = C.local_to_utc(dd.year, dd.month, dd.day, t[0], t[1], t[2], pl["tz"])
            st = {"ayanamsha": cfg["ayanamsha"]}; ch = C.compute_chart(utc, pl["lat"], pl["lon"], st)
            extra = ""
            if not d["exact"]:
                ts = C.time_sensitivity(utc, pl["lat"], pl["lon"], 30, st)
                extra = "\n\nApproximate time: within +/-30 minutes the Lagna %s and the Moon's nakshatra %s. Treat Lagna-based details as provisional." % (
                    "COULD CHANGE" if ts["lagna_may_change"] else "would not change", "could change" if ts["moon_nakshatra_may_change"] else "would not change")
        except C.ChartError as ex: state["step"] = "time"; return "Chart nahi ban saka: %s. Birth time dobara batayein." % ex
        state["chart"] = ch; state["step"] = "menu"
        return _fmt_chart(ch) + extra + "\n\n" + _menu(cfg)
    # menu / follow-up
    low = msg.lower(); chosen = TOPICS.get(msg.strip().rstrip("."))
    if not chosen:
        for k, v in LABEL.items():
            if k in low or (k == "spiritual" and "osho" in low): chosen = k; break
    if chosen:
        if chosen not in cfg["topics_enabled"]: return "That topic is currently disabled.\n" + _menu(cfg)
        state["topic"] = chosen; state["step"] = "followup"; state["history"].append(chosen)
        rep = topic_report(chosen, state["chart"], db); ai = _ai_layer(state, cfg, db, "Give a concise, careful reading of the %s facts for %s." % (chosen, d["name"]), rep)
        return rep + ("\n\n" + ai if ai else "") + "\n\nAap follow-up pooch sakte hain, ya doosra topic chunein (1-4)."
    if step == "menu": return "Please choose a topic.\n" + _menu(cfg)
    ai = _ai_layer(state, cfg, db, msg, topic_report(state["topic"], state["chart"], db))
    if ai: return ai
    return "[Demo mode - no AI model] I can only answer chart-fact questions by topic right now. Choose a topic (1-4) or type 'restart'. Last topic: %s." % LABEL[state["topic"]]

def _ai_layer(state, cfg, db, prompt, report):
    if not llm.is_live(cfg): return None
    recs = [r["id"] for r in kb.search(db, prompt)] + TOPIC_RECORDS.get(state["topic"], [])
    sysmsg = cfg["instructions"] + "\nUser name: %s. Chart JSON (authoritative, do not alter): %s\nRetrieved record ids you may cite: %s\nRule-evaluation report: %s\nCite only those ids. Label inference as INFERENCE. No outcome guarantees." % (
        state["data"]["name"], json.dumps(state["chart"]["planets"]), sorted(set(recs)), report)
    state["history"] = state["history"][-12:]
    try: txt = llm.generate(cfg, sysmsg, [{"role": "user", "content": prompt}])
    except llm.LLMError as ex:
        kb.log_event(db, "error", "LLM provider failure: %s" % ex); return "[Live model unavailable right now - showing rule-based output only.]"
    return "[AI-generated by %s - treat as interpretation]\n%s" % (cfg["model"], txt)
