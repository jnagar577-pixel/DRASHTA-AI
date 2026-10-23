"""Offline place table (no geocoding service available). Add cities here or enter 'lat,lon,Timezone'."""
CITIES = {"bhopal":(23.2599,77.4126,"Asia/Kolkata"),"delhi":(28.6139,77.2090,"Asia/Kolkata"),"new delhi":(28.6139,77.2090,"Asia/Kolkata"),
 "mumbai":(19.0760,72.8777,"Asia/Kolkata"),"kolkata":(22.5726,88.3639,"Asia/Kolkata"),"chennai":(13.0827,80.2707,"Asia/Kolkata"),
 "bengaluru":(12.9716,77.5946,"Asia/Kolkata"),"hyderabad":(17.3850,78.4867,"Asia/Kolkata"),"pune":(18.5204,73.8567,"Asia/Kolkata"),
 "ahmedabad":(23.0225,72.5714,"Asia/Kolkata"),"jaipur":(26.9124,75.7873,"Asia/Kolkata"),"lucknow":(26.8467,80.9462,"Asia/Kolkata"),
 "indore":(22.7196,75.8577,"Asia/Kolkata"),"patna":(25.5941,85.1376,"Asia/Kolkata"),"nagpur":(21.1458,79.0882,"Asia/Kolkata"),
 "varanasi":(25.3176,82.9739,"Asia/Kolkata"),"gwalior":(26.2183,78.1828,"Asia/Kolkata"),"jabalpur":(23.1815,79.9864,"Asia/Kolkata"),
 "ujjain":(23.1765,75.7885,"Asia/Kolkata"),"kathmandu":(27.7172,85.3240,"Asia/Kathmandu"),"london":(51.5072,-0.1276,"Europe/London"),
 "new york":(40.7128,-74.0060,"America/New_York"),"dubai":(25.2048,55.2708,"Asia/Dubai"),"singapore":(1.3521,103.8198,"Asia/Singapore")}

def resolve(text):
    parts = [p.strip() for p in text.split(",")]
    if len(parts) == 3:
        try:
            lat, lon = float(parts[0]), float(parts[1])
            from zoneinfo import ZoneInfo; ZoneInfo(parts[2])
            return {"name": "custom coordinates", "lat": lat, "lon": lon, "tz": parts[2]}
        except Exception: return None
    key = " ".join(parts[0].lower().split())
    if key in CITIES:
        lat, lon, tz = CITIES[key]; return {"name": key.title(), "lat": lat, "lon": lon, "tz": tz}
    return None
