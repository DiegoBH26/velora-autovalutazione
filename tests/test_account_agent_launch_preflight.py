"""Regression checks: account-only OTA agents cannot start ghost timers."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class AccountLaunchGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontend=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        cls.server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")

    def test_batch_starts_direct_master_before_booking_without_global_login_gate(self):
        app=self.frontend
        begin=app.index("async function launchAgentBatch(")
        end=app.index("async function loadAgentChat(",begin)
        batch=app[begin:end]
        # Expedia/Vrbo/Holidu authentication must not block Leonardo or Booking.
        # Every account specialist is checked independently by startSpecialistAgent.
        self.assertNotIn("await requireSpecialistAccountProfiles(ids)",batch)
        self.assertLess(
            batch.index('await startSpecialistAgent("official_site"'),
            batch.index('await startSpecialistAgent("booking"')
        )
        self.assertLess(
            batch.index('await startSpecialistAgent("booking"'),
            batch.index("await Promise.all(remaining.map(")
        )
        single=app[app.index("async function startSpecialistAgent("):begin]
        self.assertLess(
            single.index("await requireSpecialistAccountProfiles([agentId])"),
            single.index('const started = await fetch(localAgentUrl("/api/agents/start")')
        )
        self.assertIn("acceptedIds.push(id)",batch)
        self.assertIn("if(acceptedIds.length===1)",batch)
        self.assertIn("if (acceptedIds.length===0)",batch)
        self.assertNotIn("setAgentRunIds(ids);",batch)

    def test_single_agent_waits_for_account_and_sets_launch_error(self):
        app=self.frontend
        section=app[app.index("async function startSpecialistAgent("):app.index("async function launchAgentBatch(")]
        self.assertIn("await requireSpecialistAccountProfiles([agentId])",section)
        self.assertIn("onAccepted?.()",section)
        self.assertIn("if (!accepted)",section)
        self.assertIn('state:"failed",error:message',section)

    def test_account_setup_is_explained_without_public_button(self):
        app=self.frontend
        self.assertIn('▶ Account',app)
        self.assertNotIn('▶ Pubblico',app)
        self.assertIn("Apri accesso",app)
        self.assertIn("Chiudi e conserva",app)
        self.assertIn("Configura credenziali",app)
        self.assertIn("Il timer parte soltanto",app)
        self.assertIn("setPortalSessions(sessions)",app)
        self.assertIn("Avvio non eseguito: account da configurare",app)
        self.assertIn('role="alert">{specialistLaunchErrors[agent.id] || state?.error}',app)
        # A previous login may already exist on the PC: do not block the
        # verification button based on stale UI state. The backend still preflights.
        self.assertNotIn("||!loginState?.profileSaved||loginOpen",app)
        self.assertIn("Rileggi accessi",app)
        self.assertIn("Gestore credenziali Windows",app)

    def test_backend_requires_existing_profile_or_windows_credentials(self):
        server=self.server
        self.assertIn('if agent_id in {"expedia", "vrbo", "holidu"} and session_mode != "account":',server)
        self.assertIn("PORTAL_SESSIONS.has_saved_profile(agent_id)",server)
        self.assertIn("PORTAL_SESSIONS.has_credentials(agent_id)",server)
        self.assertIn('portal_state.get("state")=="ready"',server)
        self.assertIn('"/api/portal-auth/start"',server)
        self.assertIn('state="queued"',server.replace('"state":"queued"','state="queued"'))  # queued before worker starts


if __name__=="__main__":
    unittest.main()
