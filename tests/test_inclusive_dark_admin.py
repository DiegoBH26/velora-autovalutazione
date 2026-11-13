"""Ensure the admin homepage offers the same reversible color mode as Velora."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = (ROOT/"src"/"AuthGate.tsx").read_text(encoding="utf-8")
SHELL = (ROOT/"src"/"VeloraWorkspace.tsx").read_text(encoding="utf-8")
COLORS = (ROOT/"src"/"velora-inclusive-dark.css").read_text(encoding="utf-8")


class AdminInclusiveToggleTest(unittest.TestCase):
    def test_button_is_in_admin_header(self):
        area = ADMIN.split('className="velora-admin__actions"', 1)[1].split('</header>', 1)[0]
        self.assertIn("data-velora-inclusive-switch", area)
        self.assertIn("aria-pressed={inclusiveDark}", area)
        self.assertIn("onClick={toggleInclusiveDark}", area)
        self.assertIn('Dark inclusivo', area)
        self.assertIn('onClick={onClose}', area)

    def test_same_preference_and_no_reload(self):
        key = '"velora-color-mode"'
        self.assertIn(key, ADMIN)
        self.assertIn(key, SHELL)
        self.assertIn("window.localStorage.setItem", ADMIN)
        self.assertIn("window.localStorage.setItem", SHELL)
        self.assertIn('"dark-inclusive" : "original"', ADMIN)
        self.assertIn('"dark-inclusive" : "original"', SHELL)
        self.assertIn('document.documentElement.classList.toggle("velora-inclusive-dark", next)', ADMIN)
        self.assertIn('document.documentElement.classList.toggle("velora-inclusive-dark", next)', SHELL)

    def test_distinct_active_state_and_accessible_focus(self):
        self.assertIn('aria-label={inclusiveDark ?', ADMIN)
        self.assertIn('.velora-admin__inclusive-toggle[aria-pressed="true"]', COLORS)
        self.assertIn('.velora-admin__inclusive-toggle:focus-visible', COLORS)


if __name__ == "__main__":
    unittest.main()
