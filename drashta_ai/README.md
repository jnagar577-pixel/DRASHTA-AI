# Drashta AI (working prototype)

D1/Lagna-only Vedic chart consultation chatbot: Flask + SQLite, deterministic chart engine, source-cited knowledge records,
owner admin panel, demo mode when no API key. **Read "Known limitations" before relying on any output.**

## Run
```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # edit; then export the variables:  set -a; . ./.env; set +a
python3 -m drashta.app            # chat: http://127.0.0.1:5000   admin: /admin
python3 -m unittest discover -s tests -v    # 43 tests
```
Without `ANTHROPIC_API_KEY` the UI shows **DEMO MODE** (rule-based, no AI model). Keys are read only from server environment variables.
Do not expose this app publicly with the Flask dev server; use a production WSGI server behind HTTPS.

## Architecture
- `drashta/chart.py` - deterministic D1 engine (no LLM): UTC conversion with zoneinfo (DST ambiguity rejected), Lahiri sidereal, whole-sign houses, lords, graha drishti, nakshatra/pada, retrograde, combustion, dignity, +/-30 min sensitivity for approximate times. Other charts raise an error.
- `drashta/places.py` - small OFFLINE city table; otherwise user gives `lat,lon,Timezone`.
- `drashta/kb.py` + `knowledge/*.md` - record store; ingestion parses the YAML-style record blocks. Add sources by dropping a `.md` file in `knowledge/` and restarting (or import JSON in admin).
- `drashta/consult.py` - conversation flow, topic rule evaluation, citations, AI layer (labelled).
- `drashta/llm.py` - provider adapter (Anthropic Messages API). Failures return a safe message and log an event.
- `drashta/app.py` - API, rate limiting, admin (password from env, SameSite cookie, required header), data deletion.

## Calculation settings (disclosed in every chart)
Sidereal, Lahiri ayanamsha (approx. formula), mean Rahu/Ketu, geocentric, whole-sign houses, Parashari graha drishti convention,
combustion orbs Moon 12 / Mars 17 / Mercury 14 (12 retro) / Jupiter 11 / Venus 10 (8 retro) / Saturn 15. Aspect, dignity and orb conventions are
external conventions, not verified against the supplied BPHS scan.

## Known limitations (honest status)
1. **Ephemeris is NOT Swiss Ephemeris.** No Swiss Ephemeris/network in the build environment. The built-in analytic model matched published Meeus
   examples (Moon 0.02 deg, Venus 0.002 deg) but accuracy is ~0.02-0.1 deg for planets and up to ~0.3 deg for the Moon. Nakshatra/pada
   and sign-edge cases can be wrong. Before real use, validate against Swiss Ephemeris/JPL; wiring `pyswisseph` in is not done.
2. **Knowledge base is small.** 15 records: BNN-RGR introduction (9, p. iii-iv, visually verified) and NADI-JK (6; 4 visually verified, 1 partially, 1 text-layer only).
   **No BPHS records** (image-only scan, no Hindi/Sanskrit OCR available) and **no Osho records** (Hindi text layers corrupted; *Astrology* book not supplied).
   Finance and Spiritual topics therefore say plainly that no verified rule exists.
3. Source rules say *which* planet to examine, not outcomes; the app lists chart facts and cites the rules, and predicts no outcomes.
4. Not implemented: transits, dashas, progression (NADI-JK records exist but no engine), gender input, chat-history-aware retrieval, admin knowledge editing/upload UI
   (use `.md` files or JSON import), "test conversation" admin tool, ayanamsha options beyond Lahiri/custom.
5. Anthropic adapter is **untested against the live API** (only mocked). Model id default `claude-sonnet-5-5` is editable in admin.
6. Admin UI is a minimal JSON editor. No CSRF token beyond SameSite + custom header; no HTTPS handling; single-process in-memory rate limiter.
7. Geocoding is offline and limited; historical timezone data comes from the system tz database.
8. Chat stores session state (name, birth details, chart) in SQLite until deleted (user link in UI; admin "delete all"). No IPs are stored.
