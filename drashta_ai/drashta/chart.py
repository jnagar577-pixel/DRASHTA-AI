"""Deterministic D1 (Rashi/Lagna) chart engine. No language model involved.

EPHEMERIS: built-in low-precision analytic model (Schlyter-style orbital elements +
main Moon/Jupiter/Saturn perturbations). Typical error: Sun ~0.01-0.02 deg, planets
~0.02-0.1 deg, Moon ~0.1-0.3 deg (geocentric, no topocentric parallax). Good for
sign/house; nakshatra/pada and degree borders can be wrong near boundaries.
Install pyswisseph for higher accuracy (see README) - not used by default here.
"""
import math, datetime as dt
from zoneinfo import ZoneInfo

SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
LORDS = ["Mars","Venus","Mercury","Moon","Sun","Mercury","Venus","Mars","Jupiter","Saturn","Saturn","Jupiter"]
NAKS = ["Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra","Punarvasu","Pushya","Ashlesha","Magha",
 "Purva Phalguni","Uttara Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha","Mula",
 "Purva Ashadha","Uttara Ashadha","Shravana","Dhanishta","Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati"]
PLANETS = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]
EXALT = {"Sun":0,"Moon":1,"Mars":9,"Mercury":5,"Jupiter":3,"Venus":11,"Saturn":6}
OWN = {"Sun":[4],"Moon":[3],"Mars":[0,7],"Mercury":[2,5],"Jupiter":[8,11],"Venus":[1,6],"Saturn":[9,10]}
ASPECTS = {"Sun":[7],"Moon":[7],"Mars":[4,7,8],"Mercury":[7],"Jupiter":[5,7,9],"Venus":[7],"Saturn":[3,7,10],"Rahu":[7],"Ketu":[7]}
DEFAULT_SETTINGS = {"ayanamsha":"lahiri","node":"mean","house_system":"whole_sign",
 "combustion_orbs":{"Moon":12,"Mars":17,"Mercury":14,"Jupiter":11,"Venus":10,"Saturn":15},
 "combustion_orbs_retro":{"Mercury":12,"Venus":8}}

class ChartError(ValueError): pass
class AmbiguousTime(ChartError): pass

def _r(x): return math.radians(x)
def jd_from_utc(d):
    d = d.astimezone(dt.timezone.utc); y, m = d.year, d.month
    D = d.day + (d.hour + (d.minute + d.second/60)/60)/24
    if m <= 2: y -= 1; m += 12
    A = y//100; B = 2 - A + A//4
    return int(365.25*(y+4716)) + int(30.6001*(m+1)) + D + B - 1524.5

def _kepler(M, e):
    M = _r(M % 360); E = M + e*math.sin(M)*(1+e*math.cos(M))
    for _ in range(30):
        dE = (E - e*math.sin(E) - M)/(1 - e*math.cos(E)); E -= dE
        if abs(dE) < 1e-12: break
    return E

def _sun(d):
    w = 282.9404 + 4.70935e-5*d; e = 0.016709 - 1.151e-9*d; M = 356.0470 + 0.9856002585*d
    E = _kepler(M, e); xv = math.cos(E)-e; yv = math.sqrt(1-e*e)*math.sin(E)
    lon = math.degrees(math.atan2(yv, xv)) + w; r = math.hypot(xv, yv)
    return r*math.cos(_r(lon)), r*math.sin(_r(lon)), lon % 360, M, w

def _moon(d, Ms, ws):
    N = 125.1228 - 0.0529538083*d; i = 5.1454; w = 318.0634 + 0.1643573223*d
    a = 60.2666; e = 0.0549; M = 115.3654 + 13.0649929509*d
    E = _kepler(M, e); xv = a*(math.cos(E)-e); yv = a*math.sqrt(1-e*e)*math.sin(E)
    v = math.degrees(math.atan2(yv, xv)); u = _r(v + w)
    x = math.cos(_r(N))*math.cos(u) - math.sin(_r(N))*math.sin(u)*math.cos(_r(i))
    y = math.sin(_r(N))*math.cos(u) + math.cos(_r(N))*math.sin(u)*math.cos(_r(i))
    lon = math.degrees(math.atan2(y, x))
    Lm = N + w + M; Ls = ws + Ms; D = Lm - Ls; F = M + w; s = lambda a_: math.sin(_r(a_))
    lon += (-1.274*s(M-2*D) + 0.658*s(2*D) - 0.186*s(Ms) - 0.059*s(2*M-2*D) - 0.057*s(M-2*D+Ms)
            + 0.053*s(M+2*D) + 0.046*s(2*D-Ms) + 0.041*s(M-Ms) - 0.035*s(D) - 0.031*s(M+Ms)
            - 0.015*s(2*F-2*D) + 0.011*s(M-4*D))
    return lon % 360

_EL = {  # N0,N1, i0,i1, w0,w1, a, e0,e1, M0,M1
 "Mercury":(48.3313,3.24587e-5,7.0047,5.00e-8,29.1241,1.01444e-5,0.387098,0.205635,5.59e-10,168.6562,4.0923344368),
 "Venus":(76.6799,2.46590e-5,3.3946,2.75e-8,54.8910,1.38374e-5,0.723330,0.006773,-1.302e-9,48.0052,1.6021302244),
 "Mars":(49.5574,2.11081e-5,1.8497,-1.78e-8,286.5016,2.92961e-5,1.523688,0.093405,2.516e-9,18.6021,0.5240207766),
 "Jupiter":(100.4542,2.76854e-5,1.3030,-1.557e-7,273.8777,1.64505e-5,5.20256,0.048498,4.469e-9,19.8950,0.0830853001),
 "Saturn":(113.6634,2.38980e-5,2.4886,-1.081e-7,339.3939,2.97661e-5,9.55475,0.055546,-9.499e-9,316.9670,0.0334442282)}

def _planet(name, d, xs, ys):
    N0,N1,i0,i1,w0,w1,a,e0,e1,M0,M1 = _EL[name]
    N = N0+N1*d; i = i0+i1*d; w = w0+w1*d; e = e0+e1*d; M = M0+M1*d
    E = _kepler(M, e); xv = a*(math.cos(E)-e); yv = a*math.sqrt(1-e*e)*math.sin(E)
    v = math.degrees(math.atan2(yv, xv)); r = math.hypot(xv, yv); u = _r(v+w)
    xh = r*(math.cos(_r(N))*math.cos(u) - math.sin(_r(N))*math.sin(u)*math.cos(_r(i)))
    yh = r*(math.sin(_r(N))*math.cos(u) + math.cos(_r(N))*math.sin(u)*math.cos(_r(i)))
    zh = r*math.sin(u)*math.sin(_r(i))
    if name in ("Jupiter","Saturn"):
        Mj = 19.8950+0.0830853001*d; Ms = 316.9670+0.0334442282*d; s = lambda a_: math.sin(_r(a_)); c = lambda a_: math.cos(_r(a_))
        lon = math.degrees(math.atan2(yh, xh)); lat = math.atan2(zh, math.hypot(xh, yh))
        if name == "Jupiter":
            lon += (-0.332*s(2*Mj-5*Ms-67.6) - 0.056*s(2*Mj-2*Ms+21) + 0.042*s(3*Mj-5*Ms+21)
                    - 0.036*s(Mj-2*Ms) + 0.022*c(Mj-Ms) + 0.023*s(2*Mj-3*Ms+52) - 0.016*s(Mj-5*Ms-69))
        else:
            lon += (0.812*s(2*Mj-5*Ms-67.6) - 0.229*c(2*Mj-4*Ms-2) + 0.119*s(Mj-2*Ms-3)
                    + 0.046*s(2*Mj-6*Ms-69) + 0.014*s(Mj-3*Ms+32))
        rr = math.hypot(math.hypot(xh, yh), zh)
        xh = rr*math.cos(lat)*math.cos(_r(lon)); yh = rr*math.cos(lat)*math.sin(_r(lon))
    return math.degrees(math.atan2(yh+ys, xh+xs)) % 360

def tropical_longitudes(jd):
    d = jd - 2451543.5; xs, ys, ls, Ms, ws = _sun(d)
    out = {"Sun": ls, "Moon": _moon(d, Ms, ws)}
    for n in ("Mercury","Venus","Mars","Jupiter","Saturn"): out[n] = _planet(n, d, xs, ys)
    T = (jd-2451545.0)/36525; om = (125.0445479 - 1934.1362891*T + 0.0020754*T*T) % 360
    out["Rahu"] = om; out["Ketu"] = (om+180) % 360
    return out

def ayanamsha(jd, name="lahiri"):
    if name == "lahiri": return 23.8531 + 1.396971*(jd-2451545.0)/36525  # approx; ~0.01 deg level
    if name.startswith("custom:"): return float(name[7:]) + 1.396971*(jd-2451545.0)/36525  # value at J2000
    raise ChartError("Unsupported ayanamsha: %s (supported: lahiri, custom:<deg at J2000>)" % name)

def ascendant_tropical(jd, lat, lon):
    T = (jd-2451545.0)/36525
    ramc = (280.46061837 + 360.98564736629*(jd-2451545.0) + 0.000387933*T*T + lon) % 360
    eps = _r(23.4392911 - 0.0130042*T)
    return math.degrees(math.atan2(math.cos(_r(ramc)), -(math.sin(_r(ramc))*math.cos(eps) + math.tan(_r(lat))*math.sin(eps)))) % 360

def local_to_utc(year, month, day, hour12, minute, ampm, tzname):
    if not 1 <= hour12 <= 12: raise ChartError("Hour must be 1-12 (with AM/PM).")
    if not 0 <= minute <= 59: raise ChartError("Minute must be 0-59.")
    ampm = ampm.upper()
    if ampm not in ("AM","PM"): raise ChartError("Please specify AM or PM.")
    h = hour12 % 12 + (12 if ampm == "PM" else 0)
    try:
        tz = ZoneInfo(tzname); a = dt.datetime(year, month, day, h, minute, tzinfo=tz, fold=0)
    except Exception as ex: raise ChartError("Invalid date or timezone: %s" % ex)
    b = a.replace(fold=1)
    if a.utcoffset() != b.utcoffset():
        raise AmbiguousTime("That local time is ambiguous or non-existent in %s because of a daylight-saving change. Please give the correct local time or UTC offset." % tzname)
    return a.astimezone(dt.timezone.utc), a

def _dms(x): return "%d\u00b0%02d\u2032" % (int(x), int((x % 1)*60))

def analyze(sid, lagna_sid, speeds=None, settings=None):
    """Pure function: sidereal longitudes (+Lagna) -> houses, lords, aspects, dignity, combustion."""
    st = dict(DEFAULT_SETTINGS); st.update(settings or {})
    li = int(lagna_sid // 30); planets = {}
    for p in PLANETS:
        L = sid[p] % 360; si = int(L // 30); nk = int(L // (40/3)); pada = int((L % (40/3)) // (10/3)) + 1
        planets[p] = {"longitude": round(L, 4), "sign": SIGNS[si], "degree": round(L % 30, 4), "dms": _dms(L % 30),
            "house": (si - li) % 12 + 1, "nakshatra": NAKS[nk], "pada": pada, "lord_of_sign": LORDS[si]}
        retro = p in ("Rahu","Ketu") or (speeds is not None and p not in ("Sun","Moon") and speeds[p] < 0)
        planets[p]["retrograde"] = bool(retro)
        if p in EXALT:
            planets[p]["dignity"] = ("exalted" if si == EXALT[p] else "debilitated" if si == (EXALT[p]+6) % 12
                                     else "own sign" if si in OWN[p] else "neutral (friend/enemy not computed)")
        else: planets[p]["dignity"] = "not assessed"
    sun = sid["Sun"]
    for p, orb in st["combustion_orbs"].items():
        o = st["combustion_orbs_retro"].get(p, orb) if planets[p]["retrograde"] else orb
        diff = abs((sid[p] - sun + 180) % 360 - 180)
        planets[p]["combust"] = diff < o; planets[p]["sun_distance"] = round(diff, 2)
    houses = []
    for h in range(1, 13):
        si = (li + h - 1) % 12
        houses.append({"house": h, "sign": SIGNS[si], "lord": LORDS[si], "planets": [p for p in PLANETS if planets[p]["house"] == h]})
    aspects = {}
    for p in PLANETS:
        hs = [(planets[p]["house"] + n - 2) % 12 + 1 for n in ASPECTS[p]]
        aspects[p] = {"aspect_houses": hs, "aspected_planets": [q for q in PLANETS if q != p and planets[q]["house"] in hs]}
    L = lagna_sid % 360; lord = LORDS[li]
    return {"chart": "D1", "lagna": {"sign": SIGNS[li], "degree": round(L % 30, 4), "dms": _dms(L % 30), "lord": lord,
            "lord_house": planets[lord]["house"], "nakshatra": NAKS[int(L // (40/3))], "pada": int((L % (40/3)) // (10/3)) + 1},
            "houses": houses, "planets": planets, "aspects": aspects}

def compute_chart(utc, lat, lon, settings=None, chart="D1"):
    if chart != "D1": raise ChartError("Only the D1 (Lagna) chart is supported.")
    st = dict(DEFAULT_SETTINGS); st.update(settings or {})
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ChartError("Latitude/longitude out of range.")
    if abs(lat) > 66: raise ChartError("Ascendant is unreliable at polar latitudes; chart refused.")
    jd = jd_from_utc(utc); ay = ayanamsha(jd, st["ayanamsha"])
    trop = tropical_longitudes(jd); a2 = tropical_longitudes(jd+0.5); a1 = tropical_longitudes(jd-0.5)
    sid = {p: (v - ay) % 360 for p, v in trop.items()}
    speeds = {p: (a2[p]-a1[p] + 180) % 360 - 180 for p in PLANETS}
    out = analyze(sid, (ascendant_tropical(jd, lat, lon) - ay) % 360, speeds, st)
    out["settings"] = {"ephemeris": "built-in analytic (low precision; see chart.py docstring)", "zodiac": "sidereal",
        "ayanamsha": st["ayanamsha"], "ayanamsha_value_deg": round(ay, 4), "node": "mean Rahu/Ketu (geocentric)",
        "house_system": "whole-sign houses from Lagna sign", "aspects": "Parashari graha drishti convention (7th for all; Mars 4/8, Jupiter 5/9, Saturn 3/10; Rahu/Ketu 7th only) - external convention",
        "combustion_orbs_deg": st["combustion_orbs"], "utc": utc.isoformat(), "julian_day_ut": round(jd, 5), "lat": lat, "lon": lon}
    return out

def time_sensitivity(utc, lat, lon, minutes=30, settings=None):
    base = compute_chart(utc, lat, lon, settings); ch = []
    for m in (-minutes, minutes):
        c = compute_chart(utc + dt.timedelta(minutes=m), lat, lon, settings)
        ch.append((c["lagna"]["sign"], c["planets"]["Moon"]["nakshatra"]))
    return {"window_minutes": minutes, "lagna_may_change": any(x[0] != base["lagna"]["sign"] for x in ch),
            "moon_nakshatra_may_change": any(x[1] != base["planets"]["Moon"]["nakshatra"] for x in ch)}
