import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from lockedin.tango.dom import SNAPSHOT_SCRIPT, board_from_json
from lockedin.tango.model import Constraint, Relation


class TangoDomBrowserTests(unittest.TestCase):
    def test_extracts_multiple_markers_from_one_cell(self) -> None:
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if not executable.exists():
                self.skipTest("Playwright Chromium is not installed")
            browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
            try:
                page = browser.new_page()
                cells = []
                for index in range(36):
                    markers = ""
                    if index == 7:
                        markers = (
                            '<span data-testid="edge-equal" aria-label="Equal" '
                            'style="position:absolute;left:95px;top:50px;width:2px;height:2px"></span>'
                            '<span data-testid="edge-cross" aria-label="Cross" '
                            'style="position:absolute;left:50px;top:95px;width:2px;height:2px"></span>'
                        )
                    cells.append(
                        f'<div data-testid="cell-{index}" data-cell-idx="{index}" '
                        f'style="position:relative;width:100px;height:100px">{markers}</div>'
                    )
                page.set_content(
                    '<div data-testid="interactive-grid" '
                    'style="display:grid;grid-template-columns:repeat(6,100px)">'
                    + "".join(cells)
                    + "</div>"
                )
                board = board_from_json(page.evaluate(SNAPSHOT_SCRIPT))
            finally:
                browser.close()

        self.assertEqual(
            board.constraints,
            (
                Constraint((1, 1), (1, 2), Relation.EQUAL),
                Constraint((1, 1), (2, 1), Relation.OPPOSITE),
            ),
        )
