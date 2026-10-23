import os, sys, json, tempfile, unittest, datetime as dt
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("ANTHROPIC_API_KEY", None)
from drashta import chart as C, places, kb, consult, llm
from drashta.app import create_app

UTC = dt.timezone.utc
def lon_diff(a, b): return abs((a - b + 180) % 360 - 180)

class TimeTests(unittest.TestCase):
    def test_julian_day_j2000(self): self.assertEqual(C.jd_from_utc(dt.datetime(2000, 1, 1, 12, tzinfo=UTC)), 2451545.0)
    def test_ampm_midnight_noon(self):
        self.assertEqual(C.local_to_utc(1990, 1, 1, 12, 0, "AM", "UTC")[0].hour, 0)
        self.assertEqual(C.local_to_utc(1990, 1, 1, 12, 30, "PM", "UTC")[0].hour, 12)
        self.assertEqual(C.local_to_utc(1990, 1, 1, 10, 30, "PM", "UTC")[0].hour, 22)
    def test_ist_1947(self): self.assertEqual(C.local_to_utc(1947, 8, 15, 12, 0, "AM", "Asia/Kolkata")[0], dt.datetime(1947, 8, 14, 18, 30, tzinfo=UTC))
    def test_dst_ambiguous_and_missing(self):
        with self.assertRaises(C.AmbiguousTime): C.local_to_utc(2023, 11, 5, 1, 30, "AM", "America/New_York")
        with self.assertRaises(C.AmbiguousTime): C.local_to_utc(2023, 3, 12, 2, 30, "AM", "America/New_York")
    def test_invalid_inputs(self):
        for args in [(1990,1,1,13,0,"AM","UTC"), (1990,1,1,5,60,"AM","UTC"), (1990,1,1,5,0,"XM","UTC"), (1990,2,30,5,0,"AM","UTC"), (1990,1,1,5,0,"AM","Nowhere/City")]:
            with self.assertRaises(C.ChartError): C.local_to_utc(*args)
    def test_parsers(self):
        self.assertEqual(consult.parse_time("10:30 PM"), (10, 30, "PM")); self.assertIsNone(consult.parse_time("10:30"))
        self.assertIsNotNone(consult.parse_date("15-08-1947")); self.assertIsNone(consult.parse_date("31-02-1990")); self.assertIsNone(consult.parse_date("01-01-2999"))

class PlaceTests(unittest.TestCase):
    def test_city(self): self.assertEqual(places.resolve("Bhopal")["tz"], "Asia/Kolkata")
    def test_custom(self): self.assertEqual(places.resolve("26.85, 80.95, Asia/Kolkata")["lat"], 26.85)
    def test_unknown(self): self.assertIsNone(places.resolve("Atlantis")); self.assertIsNone(places.resolve("1,2,Bad/Zone"))

class EphemerisTests(unittest.TestCase):
    # Published Meeus examples (Astronomical Algorithms): tolerance reflects this low-precision engine
    def test_moon_meeus_1992(self): self.assertLess(lon_diff(C.tropical_longitudes(2448724.5)["Moon"], 133.167), 0.15)
    def test_venus_meeus_1992(self): self.assertLess(lon_diff(C.tropical_longitudes(2448976.5)["Venus"], 313.081), 0.05)
    def test_sun_moon_j2000(self):
        t = C.tropical_longitudes(2451545.0); self.assertLess(lon_diff(t["Sun"], 280.37), 0.05); self.assertLess(lon_diff(t["Moon"], 223.32), 0.1)
    def test_nodes_opposite(self):
        t = C.tropical_longitudes(2451545.0); self.assertAlmostEqual(lon_diff(t["Rahu"], t["Ketu"]), 180, places=6)
    def test_regression_fixture_1947(self):
        # Regression values produced by this engine; Lagna cross-checked against the widely cited Taurus ~7.7 deg.
        u, _ = C.local_to_utc(1947, 8, 15, 12, 0, "AM", "Asia/Kolkata"); ch = C.compute_chart(u, 28.6139, 77.2090)
        self.assertEqual(ch["lagna"]["sign"], "Taurus"); self.assertAlmostEqual(ch["lagna"]["degree"], 7.74, delta=0.3)
        self.assertEqual((ch["planets"]["Sun"]["sign"], ch["planets"]["Moon"]["sign"], ch["planets"]["Jupiter"]["sign"], ch["planets"]["Rahu"]["sign"]), ("Cancer", "Cancer", "Libra", "Taurus"))
        self.assertTrue(ch["planets"]["Rahu"]["retrograde"]); self.assertEqual(ch["planets"]["Moon"]["nakshatra"], "Pushya")
    def test_retrograde_detected(self):
        # Mercury was retrograde on 2020-07-01 (published station dates 2020-06-18 to 2020-07-12)
        ch = C.compute_chart(dt.datetime(2020, 7, 1, 6, tzinfo=UTC), 28.6, 77.2); self.assertTrue(ch["planets"]["Mercury"]["retrograde"]); self.assertFalse(ch["planets"]["Sun"]["retrograde"])

class HouseAspectTests(unittest.TestCase):
    def setUp(self):
        sid = {p: 0.0 for p in C.PLANETS}
        sid.update({"Sun": 15, "Moon": 100, "Mars": 10, "Mercury": 20, "Jupiter": 130, "Venus": 250, "Saturn": 300, "Rahu": 40, "Ketu": 220})
        self.ch = C.analyze(sid, 5.0)  # Aries lagna
    def test_lagna_lord_and_houses(self):
        self.assertEqual(self.ch["lagna"]["lord"], "Mars"); self.assertEqual(self.ch["lagna"]["lord_house"], 1)
        self.assertEqual([h["sign"] for h in self.ch["houses"]][:3], ["Aries", "Taurus", "Gemini"]); self.assertEqual(self.ch["houses"][3]["lord"], "Moon")
    def test_house_of_planet(self): self.assertEqual(self.ch["planets"]["Moon"]["house"], 4); self.assertEqual(self.ch["planets"]["Saturn"]["house"], 11)
    def test_aspects(self):
        self.assertEqual(self.ch["aspects"]["Mars"]["aspect_houses"], [4, 7, 8])      # Mars in H1: 4,7,8
        self.assertEqual(self.ch["aspects"]["Jupiter"]["aspect_houses"], [9, 11, 1])  # Jupiter in H5: 5th->9, 7th->11, 9th->1
        self.assertEqual(self.ch["aspects"]["Saturn"]["aspect_houses"], [1, 5, 8])    # Saturn H11: 3->1, 7->5, 10->8
        self.assertIn("Moon", self.ch["aspects"]["Mars"]["aspected_planets"]); self.assertIn("Sun", self.ch["aspects"]["Saturn"]["aspected_planets"])
    def test_dignity_combustion(self):
        self.assertEqual(self.ch["planets"]["Sun"]["dignity"], "exalted"); self.assertEqual(self.ch["planets"]["Moon"]["dignity"], "own sign")
        self.assertTrue(self.ch["planets"]["Mercury"]["combust"]); self.assertFalse(self.ch["planets"]["Venus"]["combust"])
    def test_nakshatra_pada(self):
        sid = {p: 0.0 for p in C.PLANETS}; sid["Moon"] = 13.34; ch = C.analyze(sid, 0)
        self.assertEqual((ch["planets"]["Moon"]["nakshatra"], ch["planets"]["Moon"]["pada"]), ("Bharani", 1))

class D1OnlyTests(unittest.TestCase):
    def test_other_charts_rejected(self):
        for c in ("D9", "Chandra", "Arudha"):
            with self.assertRaises(C.ChartError): C.compute_chart(dt.datetime(2000, 1, 1, tzinfo=UTC), 20, 77, chart=c)
    def test_output_is_d1(self):
        ch = C.compute_chart(dt.datetime(2000, 1, 1, tzinfo=UTC), 20, 77); self.assertEqual(ch["chart"], "D1"); self.assertNotIn("D9", json.dumps(ch))
    def test_bad_ayanamsha_and_polar(self):
        with self.assertRaises(C.ChartError): C.compute_chart(dt.datetime(2000, 1, 1, tzinfo=UTC), 20, 77, {"ayanamsha": "xyz"})
        with self.assertRaises(C.ChartError): C.compute_chart(dt.datetime(2000, 1, 1, tzinfo=UTC), 80, 20)

class AppBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DB_PATH": os.path.join(self.tmp.name, "t.db"), "ADMIN_PASSWORD": "pw-test", "SECRET_KEY": "k"}); self.c = self.app.test_client()
    def tearDown(self): self.tmp.cleanup()
    def say(self, sid, m): return self.c.post("/api/chat", json={"session_id": sid, "message": m}).get_json()
    def run_to_menu(self):
        j = self.c.post("/api/session").get_json(); sid = j["session_id"]
        for m in ["Asha", "15-08-1947", "New Delhi", "12:00 AM", "exact", "yes"]: r = self.say(sid, m)
        return sid, r

class KnowledgeTests(AppBase):
    def test_records_have_source_and_page(self):
        con = kb.connect(os.path.join(self.tmp.name, "t.db")); rows = con.execute("SELECT * FROM records").fetchall()
        self.assertGreaterEqual(len(rows), 15)
        for r in rows: self.assertTrue(r["source_id"] and r["page"] and r["verification"], r["id"])
    def test_retrieval_and_citation(self):
        con = kb.connect(os.path.join(self.tmp.name, "t.db")); hits = kb.search(con, "Saturn profession karaka")
        self.assertTrue(any(h["id"] == "DRASHTA-BNN-004" for h in hits)); self.assertEqual(kb.get_record(con, "DRASHTA-BNN-004")["printed_page"], "iii")
    def test_topic_report_cites_only_existing_records(self):
        sid, r = self.run_to_menu(); out = self.say(sid, "1")["reply"]
        self.assertIn("DRASHTA-BNN-004", out); self.assertIn("p. iii", out); self.assertIn("INFERENCE", out)
    def test_disabled_record_not_retrieved(self):
        con = kb.connect(os.path.join(self.tmp.name, "t.db")); con.execute("UPDATE records SET enabled=0 WHERE id='DRASHTA-BNN-004'"); con.commit()
        self.assertIsNone(kb.get_record(con, "DRASHTA-BNN-004"))
    def test_finance_and_spiritual_do_not_fabricate(self):
        sid, _ = self.run_to_menu(); self.assertIn("NO VERIFIED SOURCE RULE", self.say(sid, "3")["reply"]); self.assertIn("NO VERIFIED OSHO RECORDS", self.say(sid, "4")["reply"])

class ProviderTests(AppBase):
    def test_demo_mode_labelled(self):
        self.assertEqual(self.c.get("/api/config").get_json()["mode"], "demo")
        sid, _ = self.run_to_menu(); self.say(sid, "1"); r = self.say(sid, "tell me more"); self.assertEqual(r["mode"], "demo"); self.assertIn("Demo mode", r["reply"])
    def test_provider_failure_safe(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret"}), mock.patch("requests.post", side_effect=RuntimeError("boom sk-secret")):
            sid, _ = self.run_to_menu(); out = self.say(sid, "1")["reply"]
        self.assertIn("Live model unavailable", out); self.assertNotIn("sk-secret", out); self.assertIn("DRASHTA-BNN-004", out)
    def test_live_response_is_labelled_ai(self):
        fake = mock.Mock(); fake.json.return_value = {"content": [{"type": "text", "text": "hello"}]}; fake.raise_for_status = lambda: None
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}), mock.patch("requests.post", return_value=fake):
            sid, _ = self.run_to_menu(); self.assertIn("AI-generated", self.say(sid, "2")["reply"])

class SessionTests(AppBase):
    def test_welcome_exact(self): self.assertEqual(self.c.post("/api/session").get_json()["reply"], "Namaskar, main Drashta AI hoon. Aapka name kya hai?")
    def test_flow_and_followup_context(self):
        sid, r = self.run_to_menu(); self.assertIn("D1 (Lagna) chart - Lagna: Taurus", r["reply"]); self.assertIn("1. Career", r["reply"]); self.assertIn("4. Spiritual", r["reply"])
        self.say(sid, "2"); r2 = self.say(sid, "what about it?")["reply"]; self.assertIn("Marriage", r2)  # remembers last topic
        st = json.loads(kb.connect(os.path.join(self.tmp.name, "t.db")).execute("SELECT state FROM sessions WHERE id=?", (sid,)).fetchone()["state"]); self.assertEqual(st["data"]["name"], "Asha")
    def test_validation_messages(self):
        sid = self.c.post("/api/session").get_json()["session_id"]; self.assertIn("naam", self.say(sid, "12345")["reply"]); self.say(sid, "Asha")
        self.assertIn("Date", self.say(sid, "tomorrow")["reply"])
    def test_ambiguous_time_rejected_in_flow(self):
        sid = self.c.post("/api/session").get_json()["session_id"]
        self.say(sid, "Bob"); self.say(sid, "05-11-2023"); self.say(sid, "40.7,-74.0,America/New_York"); self.assertIn("daylight", self.say(sid, "1:30 AM")["reply"])
    def test_approximate_warns(self):
        sid = self.c.post("/api/session").get_json()["session_id"]
        for m in ["Asha", "15-08-1947", "Delhi", "12:00 AM", "approximate"]: self.say(sid, m)
        self.assertIn("Approximate time", self.say(sid, "yes")["reply"])
    def test_topic_disable_and_bad_input(self):
        sid, _ = self.run_to_menu(); con = kb.connect(os.path.join(self.tmp.name, "t.db")); kb.set_setting(con, "topics_enabled", ["career"])
        self.assertIn("disabled", self.say(sid, "3")["reply"])
        self.assertEqual(self.c.post("/api/chat", json={"session_id": "zz", "message": "x"}).status_code, 400)
        self.assertEqual(self.c.post("/api/chat", json={"session_id": sid, "message": "x" * 501}).status_code, 400)
    def test_user_deletes_session(self):
        sid, _ = self.run_to_menu(); self.assertEqual(self.c.delete("/api/session/" + sid).get_json()["deleted"], 1)
        self.assertEqual(self.c.post("/api/chat", json={"session_id": sid, "message": "1"}).status_code, 404)

class AdminTests(AppBase):
    H = {"X-Requested-With": "drashta"}
    def login(self, pw="pw-test"): return self.c.post("/admin/login", json={"password": pw})
    def test_requires_auth(self):
        for path in ("/admin/api/settings", "/admin/api/knowledge", "/admin/api/export", "/admin/api/events"): self.assertEqual(self.c.get(path, headers=self.H).status_code, 401)
        self.assertEqual(self.c.delete("/admin/api/sessions", headers=self.H).status_code, 401)
    def test_wrong_password_and_rate_limit(self):
        self.assertEqual(self.login("bad").status_code, 401)
        for _ in range(6): r = self.login("bad")
        self.assertEqual(r.status_code, 429)
    def test_header_required_after_login(self):
        self.login(); self.assertEqual(self.c.get("/admin/api/settings").status_code, 401); self.assertEqual(self.c.get("/admin/api/settings", headers=self.H).status_code, 200)
    def test_admin_disabled_without_password(self):
        app = create_app({"DB_PATH": os.path.join(self.tmp.name, "n.db"), "ADMIN_PASSWORD": ""}); self.assertEqual(app.test_client().post("/admin/login", json={"password": ""}).status_code, 403)
    def test_settings_toggle_export_import_delete(self):
        self.login(); r = self.c.put("/admin/api/settings", json={"welcome": "Namaste"}, headers=self.H); self.assertEqual(r.get_json()["welcome"], "Namaste")
        self.assertEqual(self.c.post("/api/session").get_json()["reply"], "Namaste")
        self.assertEqual(self.c.put("/admin/api/settings", json={"evil": 1}, headers=self.H).status_code, 400)
        self.c.post("/admin/api/knowledge/DRASHTA-BNN-004/toggle", headers=self.H)
        recs = self.c.get("/admin/api/knowledge", headers=self.H).get_json(); self.assertFalse([x for x in recs["records"] if x["id"] == "DRASHTA-BNN-004"][0]["enabled"])
        self.assertEqual(recs["coverage"]["BPHS-GDP"]["records"], 0); self.assertIn("NOT SUPPLIED", recs["coverage"]["OSHO-ASTRO"]["note"])
        exp = self.c.get("/admin/api/export", headers=self.H).get_json(); self.assertEqual(self.c.post("/admin/api/import", json=exp, headers=self.H).get_json()["imported"], len(exp))
        self.assertEqual(self.c.post("/admin/api/import", json={"a": 1}, headers=self.H).status_code, 400)
        self.c.post("/api/session"); self.assertGreaterEqual(self.c.delete("/admin/api/sessions", headers=self.H).get_json()["deleted"], 1)

if __name__ == "__main__": unittest.main()
