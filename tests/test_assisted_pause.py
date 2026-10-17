"""Regression: assisted Vrbo/Expedia must pause on the SAME public page.

This exercises the actual observe() function with a controlled Playwright-like
page, without live requests or CAPTCHA solving.
"""
import ast
import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / "browser_audit_pilot.py"


def load_observe(scope):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    node = next(
        n for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "observe"
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["observe"]


class Page:
    def __init__(self, status):
        self.url = "about:blank"
        self.status = status
        self.navigation_count = 0

    async def goto(self, url, **kwargs):
        self.url = url
        self.navigation_count += 1
        return SimpleNamespace(status=self.status)


class AssistedPauseTest(unittest.IsolatedAsyncioTestCase):
    async def test_vrbo_and_expedia_pause_before_leaving_page(self):
        for channel, url in [
            ("vrbo", "https://www.vrbo.com/11118543ha"),
            ("expedia", "https://www.expedia.com/Example.h12345.Hotel-Information"),
        ]:
            for status in (200, 429):
                with self.subTest(channel=channel, status=status):
                    page = Page(status)
                    signals = []
                    async def google_click(*args, **kwargs):
                        return {"status": "robots_denied"}
                    async def dismiss(*args, **kwargs):
                        return None
                    async def challenge(*args, **kwargs):
                        return {"visible": False, "reason": ""}
                    async def handoff(current, callback, payload, ghost):
                        signals.append((current.url, payload["type"]))
                        return "skip"
                    scope = {
                        "asyncio": asyncio,
                        "datetime": datetime,
                        "timezone": timezone,
                        "frontend_entry_url": lambda ch, src, stay: src,
                        "allowed_by_robots": lambda url, robots: True,
                        "google_click_ota_listing": google_click,
                        "_classify_ota_url": lambda url: channel if url == page.url and url != "about:blank" else "",
                        "_plausible_ota_listing_url": lambda ch, src: src == url,
                        "dismiss_cookie": dismiss,
                        "_visible_human_challenge": challenge,
                        "_human_assist": handoff,
                        "OTA_META": {channel: {"label": channel.title()}},
                    }
                    observe = load_observe(scope)
                    stay = {"month": "2026-10", "checkin": "2026-10-19", "checkout": "2026-10-22", "nights": 3, "adults": 2}
                    record = await observe(
                        page, channel, url, stay, {}, "Perla Saracena", "Salve",
                        assist_callback=lambda payload: "skip", ghost=False,
                    )
                    self.assertEqual(page.navigation_count, 1)
                    self.assertEqual(len(signals), 1)
                    self.assertEqual(signals[0][0], url)
                    self.assertTrue(record["manualChallenge"]["prompted"])
                    self.assertEqual(
                        record["status"],
                        "rate_limited" if status == 429 else "human_verification_pending",
                    )


if __name__ == "__main__":
    unittest.main()
