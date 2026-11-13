"""Regressions for opt-in Dark inclusivo: no layout or scraping changes."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT/"src"/"VeloraWorkspace.tsx").read_text(encoding="utf-8")
MAIN = (ROOT/"src"/"main.tsx").read_text(encoding="utf-8")
CSS = (ROOT/"src"/"velora-inclusive-dark.css").read_text(encoding="utf-8")
APP = (ROOT/"src"/"App.tsx").read_text(encoding="utf-8")


class InclusiveThemeContracts(unittest.TestCase):
    def test_theme_opt_in_and_reversible(self):
        self.assertIn('velora-color-mode', SHELL)
        self.assertIn('velora-inclusive-dark', SHELL)
        self.assertIn('aria-pressed={inclusiveDark}', SHELL)
        self.assertIn('onClick={toggleInclusiveDark}', SHELL)
        self.assertIn('setInclusiveDark(next)', SHELL)
        self.assertIn('next ? "dark-inclusive" : "original"', SHELL)

    def test_theme_survives_reload_and_initial_theme_is_original(self):
        self.assertIn('window.localStorage.getItem("velora-color-mode") === "dark-inclusive"', MAIN)
        self.assertIn('import "./velora-inclusive-dark.css"', MAIN)
        self.assertIn('html.velora-inclusive-dark', CSS)
        self.assertNotIn('html:not(.velora-inclusive-dark)', CSS)

    def test_only_palette_and_the_existing_assisted_dialog(self):
        self.assertIn("data-velora-assisted-dialog", APP)
        self.assertIn("data-velora-priority", CSS)
        self.assertIn("velora-radar__slice", CSS)
        self.assertIn("velora-admin", CSS)
        # Explicitly no image conversion, no layout or typography changes.
        for prop in ('filter:grayscale(', 'hue-rotate(', 'invert(', 'grid-template-columns:',
                     'font-size:', 'font-weight:700!important', 'transform:scale('):
            self.assertNotIn(prop, CSS)


if __name__ == "__main__":
    unittest.main()
