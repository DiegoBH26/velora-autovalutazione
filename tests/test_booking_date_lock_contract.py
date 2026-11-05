"""Regression contracts: Booking dates must be authoritative for every OTA."""
import ast
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
FRONT=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class BookingDateLockContracts(unittest.TestCase):
    def test_source_files_are_parseable(self):
        ast.parse(SERVER)
        ast.parse(PILOT)

    def test_batch_waits_for_booking_then_starts_others(self):
        batch=FRONT.split("async function launchAgentBatch(",1)[1].split(
            "async function validateSpecialistNetwork(",1)[0]
        self.assertIn('await startSpecialistAgent("booking"',batch)
        self.assertIn("await Promise.all(remaining.map(",batch)
        self.assertLess(batch.index('await startSpecialistAgent("booking"'),
                        batch.index("await Promise.all(remaining.map("))
        self.assertIn("bookingReferenceStays",batch)
        self.assertIn("locks.some(",batch)
        self.assertIn("shifted_to_available_booking_dates",batch)

    def test_single_ota_uses_same_batch_guard(self):
        self.assertIn("onClick={()=>void launchAgentBatch([agent.id])}",FRONT)
        self.assertNotIn("onClick={()=>void startSpecialistAgent(agent.id)}",FRONT)

    def test_windows_preflight_rejects_missing_or_stale_booking_locks(self):
        handler=SERVER.split('if route=="/api/agents/start":',1)[1].split(
            'if route=="/api/pilot/intervention":',1)[0]
        self.assertIn('data.pop("_specialistBookingLocks",None)',handler)
        self.assertIn('booking_result.get("propertyId")!=property_id',handler)
        self.assertIn('booking_result.get("propertyName")!=data.get("name")',handler)
        self.assertIn("expected_keys",handler)
        self.assertIn("any(key not in by_key for key in expected_keys)",handler)
        self.assertIn('self._json(409,{"error":(',handler)
        self.assertLess(handler.index('if not expected_keys or any('),
                        handler.index('with AGENT_RUN_LOCK:'))

    def test_each_requested_stay_uses_exact_booking_lock(self):
        self.assertIn(
            '(str(row.get("requestedCheckin")),str(row.get("requestedCheckout"))): row',PILOT
        )
        self.assertIn(
            'shared_booking_locks.get((str(planned_stay.get("checkin")),str(planned_stay.get("checkout"))))',
            PILOT,
        )
        self.assertIn("if reference_for_specialist and not use_shared_stay:",PILOT)
        self.assertIn("SINCRONIZZAZIONE DATE:",PILOT)
        self.assertIn('record["status"]="dates_mismatch_booking_reference"',PILOT)

    def test_missing_booking_is_not_a_commercial_vacancy(self):
        # A blocked OTA or a failed Booking reference is NOT evidence of
        # closed inventory; only a same-date, verified comparison can be used.
        self.assertIn('"status":"booking_reference_unavailable"',PILOT)
        self.assertIn('record["quotes"]=[]',PILOT)
        self.assertIn("if(!booking?.units.size)continue;",FRONT)
        self.assertIn('if (observation.status==="no_public_rate")',FRONT)


if __name__=="__main__":
    unittest.main()
