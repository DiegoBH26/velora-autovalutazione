"""Keep detailed OTA observations optional and the contextual help available everywhere."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
SHELL = (ROOT / "src" / "VeloraWorkspace.tsx").read_text(encoding="utf-8")


class GuideAndRateHistoryTest(unittest.TestCase):
    def test_rate_history_is_collapsed_on_initial_render(self):
        marker = '<details data-velora-rate-history'
        self.assertIn(marker, APP)
        opening = APP.split(marker, 1)[1].split(">", 1)[0]
        self.assertNotIn("open=", opening)
        self.assertIn("Storico tariffe acquisite", APP)
        self.assertIn("Math.min(rateQuotes.length,20)", APP)
        self.assertIn('removeRateQuote(quote.id)', APP)

    def test_one_persisted_guide_available_in_every_workspace(self):
        self.assertEqual(APP.count("<VeloraWorkspace\n"), 3)
        self.assertEqual(APP.count("guideEnabled={guideEnabled}"), 3)
        self.assertEqual(APP.count("onGuideToggle={() => setGuideEnabled(current=>!current)}"), 3)
        self.assertIn("setGuideEnabled(parsed.guideEnabled)", APP)
        self.assertIn("guideEnabled,", APP)

    def test_global_help_covers_hover_and_keyboard_focus(self):
        for phrase in (
            "aria-pressed={guideEnabled}",
            "onPointerOver={showGuide}",
            "onFocusCapture={showGuide}",
            "onPointerLeave={hideGuide}",
            'role="tooltip"',
            "guideTextFor(target)",
            "data-guide={item.label",
        ):
            self.assertIn(phrase, SHELL)
        self.assertIn("data-guide={guideEnabled ? getGuideText", APP)


if __name__ == "__main__":
    unittest.main()
