"""Visual regressions: contrasting score pills and legacy light-status classes.

This test checks palette declarations and WCAG AA text contrast, without
interacting with stored structures, agents, rates or personal records.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
STANDARD = (ROOT / "src" / "velora-readability.css").read_text(encoding="utf-8")
INCLUSIVE = (ROOT / "src" / "velora-inclusive-dark.css").read_text(encoding="utf-8")


def relative_luminance(color: str) -> float:
    components = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in components]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def pill_colors(css: str, level: str) -> tuple[str, str]:
    selector = '[data-velora-score-badge="' + level + '"]'
    start = css.index(selector)
    block = css[start:].split("{", 1)[1].split("}", 1)[0]
    background = re.search(r'background(?:-color)?:\s*(#[0-9a-fA-F]{6})', block)
    foreground = re.search(r'(?<!-)color:\s*(#[0-9a-fA-F]{6})', block)
    if not background or not foreground:
        raise AssertionError("Incomplete badge palette for " + level)
    return foreground.group(1), background.group(1)


class DarkBadgeContrastTests(unittest.TestCase):
    def test_report_score_badge_is_semantically_identified(self):
        self.assertIn('data-velora-score-badge={label.shortLabel.toLowerCase()}', APP)
        self.assertIn('title={label.label}', APP)
        self.assertIn('punti, ${label.label}', APP)

    def test_all_score_badges_exceed_aa_text_contrast_both_modes(self):
        for name, stylesheet in (("original", STANDARD), ("inclusive", INCLUSIVE)):
            for level in ("bassa", "media", "alta"):
                with self.subTest(mode=name, level=level):
                    text_color, bg = pill_colors(stylesheet, level)
                    self.assertGreaterEqual(contrast(text_color, bg), 4.5)

    def test_legacy_pastel_status_classes_are_handled(self):
        for stylesheet in (STANDARD, INCLUSIVE):
            for token in ("amber", "yellow", "orange", "green", "emerald",
                          "teal", "red", "rose", "blue", "sky", "cyan",
                          "purple", "violet", "indigo"):
                with self.subTest(token=token):
                    self.assertIn('bg-' + token + '-100', stylesheet)
            self.assertIn('bg-amber-200', stylesheet)
            self.assertIn('bg-red-200', stylesheet)


if __name__ == "__main__":
    unittest.main()
