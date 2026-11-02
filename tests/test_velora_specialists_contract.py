"""Offline contract checks for Velora's twelve specialist agents.

These checks inspect source code without launching Chrome or changing OTA adapters.
They do NOT claim live OTA availability or authenticated scraping.
"""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = (
    "booking", "agoda", "airbnb", "vrbo", "expedia", "holidu",
    "hotels", "travelocity", "trip", "priceline",
    "official_site", "reviews",
)

def source(name):
    return (ROOT / name).read_text(encoding="utf-8")

def registry():
    module = ast.parse(source("velora_agent_network.py"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AGENTS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("AGENTS registry missing")

class VeloraSpecialistContracts(unittest.TestCase):
    def test_exactly_twelve_ready_agents_and_independent_ids(self):
        agents = registry()
        self.assertEqual(set(agents), set(IDS))
        self.assertEqual(len(agents), 12)
        self.assertTrue(all(info["ready"] for info in agents.values()))
        self.assertEqual({agents[a]["channel"] for a in IDS[:10]},
                         set(IDS[:10]))

    def test_browser_source_reuses_existing_ota_adapters(self):
        network = source("velora_agent_network.py")
        self.assertIn("raw = await pilot.run(args)", network)
        self.assertIn("channels=agent", network)
        self.assertIn("pricing_only=True", network)
        for name in IDS:
            self.assertIn('"' + name + '"', network)

    def test_reviewer_is_separate_and_manual(self):
        network = source("velora_agent_network.py")
        server = source("local_audit_server.py")
        self.assertIn('REVIEWER_NAME = "Giove"', network)
        self.assertIn('if route=="/api/agents/validate":', server)
        self.assertIn("agent_network.evaluate(property_id,outputs)", server)
        self.assertIn("agent_validation_output(property_id)", server)

    def test_isolated_outputs_and_two_browser_slots(self):
        server = source("local_audit_server.py")
        self.assertIn("AGENT_WORK_SLOTS=threading.BoundedSemaphore(2)", server)
        self.assertIn("def agent_workspace(property_id,agent_id)", server)
        self.assertIn('return AGENT_RESULTS / property_id / agent_id', server)
        self.assertIn("run_specialist_job", server)
        self.assertIn('"state":"queued"', server)

    def test_frontend_matches_backend_and_reports_accepted_starts(self):
        app = source("src/App.tsx")
        for agent in IDS:
            self.assertIn('id:"' + agent + '"', app)
        self.assertIn("async function launchAgentBatch", app)
        self.assertIn("startSpecialistAgent(id,false)", app)
        self.assertIn('const readiness = await fetch(localAgentUrl("/api/agents/config")', app)
        self.assertIn("accepted = true;", app)
        self.assertIn("if (trackProgress) {", app)
        self.assertIn("setAgentRunStartedAt(startedAt)", app)
        self.assertIn("role=\"progressbar\"", app)

    def test_windows_import_diagnostics_and_updater_preflight(self):
        server = source("local_audit_server.py")
        updater = source("AGGIORNA_VELORA_COMPLETO.bat")
        self.assertIn("AGENT_IMPORT_ERROR=", server)
        self.assertIn("specialist_unavailable_message()", server)
        self.assertIn("Versione agente: velora-local-agent-v125", server)
        self.assertIn("assert len(n.AGENTS)==12", updater)
        self.assertIn("n.REVIEWER_NAME=='Giove'", updater)
        self.assertIn("if errorlevel 1 goto :errore_import", updater)

    def test_progress_uses_saved_milestones_not_elapsed_seconds(self):
        import json
        import tempfile
        tree = ast.parse(source("local_audit_server.py"))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "specialist_progress")
        namespace = {"json": json}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "progress-test", "exec"), namespace)
        progress = namespace["specialist_progress"]
        with tempfile.TemporaryDirectory() as temp:
            result_file = Path(temp) / "result.json"
            running = {"state": "running", "propertyId": "sample"}
            self.assertEqual(progress("expedia", running, result_file)["progress"], 2)
            partial = {
                "propertyId": "sample",
                "identityResolution": {"status": "resolved"},
                "plan": [{"month": "2026-11"}],
                "selectedChannels": ["expedia"],
                "discoveryProgress": {"stage": "targeted", "completed": 0, "total": 1},
                "browserPhases": [],
                "bookingReferenceStays": [],
                "observations": [],
            }
            result_file.write_text(json.dumps(partial), encoding="utf-8")
            self.assertGreaterEqual(progress("expedia", running, result_file)["progress"], 12)
            partial["discoveryProgress"]["completed"] = 1
            partial["browserPhases"] = [{"phase": "discovery", "status": "completed"}, {"phase": "pricing", "status": "running"}]
            result_file.write_text(json.dumps(partial), encoding="utf-8")
            mid = progress("expedia", running, result_file)
            self.assertGreaterEqual(mid["progress"], 54)
            self.assertLess(mid["progress"], 100)
            partial["bookingReferenceStays"] = [{"month": "2026-11"}]
            partial["observations"] = [{"otaId": "expedia", "status": "no_public_rate"}]
            result_file.write_text(json.dumps(partial), encoding="utf-8")
            observed = progress("expedia", running, result_file)
            self.assertGreaterEqual(observed["progress"], 90)
            self.assertLess(observed["progress"], 100)
            self.assertIn("1/1", observed["progressDetail"])
            self.assertEqual(progress("expedia", {"state": "completed"}, result_file)["progress"], 100)

    def test_frontend_displays_live_phase_and_freezes_finished_timer(self):
        app = source("src/App.tsx")
        self.assertIn("item?.progress", app)
        self.assertIn("active?.state?.phase", app)
        self.assertIn("active?.state?.progressDetail", app)
        self.assertIn("agentRunFinishedAt", app)
        self.assertIn("setAgentRunFinishedAt(finishedAt)", app)

    def test_specialist_rejects_wrong_booking_property_by_distinctive_name(self):
        pilot_source = source("browser_audit_pilot.py")
        tree = ast.parse(pilot_source)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "specialist_booking_name_matches")
        import re
        import unicodedata
        def normalize(value):
            text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
            return " ".join(re.findall(r"[a-z0-9]+", text))
        namespace = {"_norm_name": normalize}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "booking-identity-test", "exec"), namespace)
        is_same = namespace["specialist_booking_name_matches"]
        self.assertFalse(is_same("Tenuta Speculizzi", "Tenuta Palmira", "Salve"))
        self.assertFalse(is_same("Tenuta Speculizzi", "Tenuta Palmira - Salve", "Salve"))
        self.assertTrue(is_same("Tenuta Speculizzi", "Tenuta Speculizzi - Salve", "Salve"))
        self.assertTrue(is_same("Masseria Giovanni", "Agriresort Masseria Giovanni", "Martano"))
        self.assertFalse(is_same("Masseria Giovanni", "Masseria Giulia", "Martano"))

    def test_specialists_do_not_use_booking_searchresults_for_date_lock(self):
        pilot = source("browser_audit_pilot.py")
        self.assertIn("reference_for_specialist=bool(specialist_id and specialist_id != \"booking\")", pilot)
        self.assertIn("verify_booking_candidate_page(", pilot)
        self.assertIn("IDENTITY MISMATCH", pilot)
        self.assertIn("if not booking_reference_source and not reference_for_specialist:", pilot)
        self.assertIn("if reference_for_specialist:\n                            # A single Expedia", pilot)
        self.assertIn("booking_probe_direct_dated_detail(", pilot)
        self.assertIn("max_shifts=2 if reference_for_specialist else None", pilot)
        self.assertIn("if not reference_for_specialist and initial_booking.get(\"status\") not in {", pilot)
        self.assertIn("def booking_dated_search_observation(", pilot)
        self.assertIn("def specialist_booking_name_matches(", pilot)

    def test_manual_login_remains_separate_from_automated_scraping(self):
        sessions = source("velora_portal_sessions.py")
        self.assertIn("launch_persistent_context", sessions)
        for portal in ("expedia", "vrbo", "holidu"):
            self.assertIn('"' + portal + '": {', sessions)
        self.assertIn('"scraping": "disabled_until_authorized"', sessions)

if __name__ == "__main__":
    unittest.main()
