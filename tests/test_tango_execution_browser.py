import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from lockedin.gui import TangoWorker
from lockedin.tango.actions import ActionPlan, CellAction, create_action_plan
from lockedin.tango.browser import BrowserSessionError, FEED_URL, TANGO_URL, TangoBrowserSession
from lockedin.tango.model import Board, Cell


SOLVED = Board.from_strings(("SMSMMS", "SSMMSM", "MSMSSM", "SMSMMS", "MMSSMS", "MSMSSM"))

FIXTURE = """
<div data-testid="interactive-grid"></div>
<script>
const solution = "SMSMMS" + "SSMMSM" + "MSMSSM" + "SMSMMS" + "MMSSMS" + "MSMSSM";
const grid = document.querySelector('[data-testid="interactive-grid"]');
window.clicks = [];
window.mode = "normal";
window.setCell = (index, state) => {
  const cell = grid.querySelector(`[data-cell-idx="${index}"]`);
  cell.replaceChildren();
  if (state !== "?") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-label", state === "S" ? "Sun" : "Moon");
    cell.append(svg);
  }
};
for (let index = 0; index < 36; index++) {
  const cell = document.createElement("button");
  cell.dataset.testid = `cell-${index}`;
  cell.dataset.cellIdx = index;
  grid.append(cell);
  window.setCell(index, [0, 1, 4].includes(index) ? "?" : solution[index]);
  cell.addEventListener("click", () => {
    window.clicks.push(index);
    if (window.mode === "drop") return;
    if (window.mode === "wrong") { window.setCell(2, "M"); return; }
    const current = cell.querySelector('svg[aria-label="Sun"]') ? "S"
      : cell.querySelector('svg[aria-label="Moon"]') ? "M" : "?";
    const next = {"?": "S", "S": "M", "M": "?"}[current];
    if (window.mode === "delayed") setTimeout(() => window.setCell(index, next), 75);
    else window.setCell(index, next);
  });
}
</script>
"""


class TangoExecutionBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        if not Path(cls.playwright.chromium.executable_path).exists():
            cls.playwright.stop()
            raise unittest.SkipTest("Playwright Chromium is not installed")
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route(
            "https://www.linkedin.com/**",
            lambda route: route.fulfill(content_type="text/html", body=FIXTURE),
        )
        self.page.goto(TANGO_URL)
        self.session = TangoBrowserSession(self.page, require_login=False)
        self.plan = create_action_plan(self.session.snapshot_board(), SOLVED)

    def test_clicks_and_checks_each_state_with_delayed_updates(self) -> None:
        self.page.evaluate('window.mode = "delayed"')
        progress = []
        self.session.execute_actions(self.plan, progress=lambda done, total: progress.append((done, total)))
        self.assertEqual(self.page.evaluate("window.clicks"), [0, 1, 1, 4, 4])
        self.assertEqual(self.session.snapshot_board(), SOLVED)
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])

    def test_waits_until_displayed_time_before_final_click(self) -> None:
        self.page.evaluate("""() => {
          const timer = document.createElement('span'); timer.textContent = '0:00';
          document.body.prepend(timer); window.inputTimes = [];
          document.querySelector('[data-testid="interactive-grid"]').addEventListener(
            'click', () => window.inputTimes.push(timer.textContent), true);
          setTimeout(() => timer.textContent = '0:05', 1000);
        }""")
        self.session.execute_actions(self.plan, target_seconds=5)
        self.assertEqual(self.page.evaluate("window.clicks"), [0, 1, 1, 4, 4])
        self.assertEqual(self.page.evaluate("window.inputTimes"), ["0:00"] * 4 + ["0:05"])

    def test_timed_execution_requires_timer_before_any_click(self) -> None:
        with self.assertRaisesRegex(BrowserSessionError, "timer is not visible"):
            self.session.execute_actions(self.plan, target_seconds=5)
        self.assertEqual(self.page.evaluate("window.clicks"), [])

    def test_signed_in_worker_executes_against_local_browser_fixture(self) -> None:
        results = {}
        execute = TangoBrowserSession.execute_actions

        def launch(profile: Path) -> TangoBrowserSession:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies([{"name": "li_at", "value": "test", "url": "https://www.linkedin.com"}])
            page = context.new_page()
            page.route(
                "https://www.linkedin.com/**",
                lambda route: route.fulfill(
                    content_type="text/html",
                    body="Feed" if route.request.url == FEED_URL else FIXTURE,
                ),
            )
            return TangoBrowserSession(
                page, _playwright=playwright, _browser=browser, _context=context, _owns_browser=True
            )

        def record_execution(session, plan, **kwargs) -> None:
            execute(session, plan, **kwargs)
            results["board"] = session.snapshot_board()
            results["clicks"] = session.page.evaluate("window.clicks")

        worker = TangoWorker(Path("/test/profile"))
        with (
            patch.object(TangoBrowserSession, "launch_persistent", side_effect=launch),
            patch.object(TangoBrowserSession, "execute_actions", new=record_execution),
        ):
            worker.start()
            try:
                while True:
                    kind, message = worker.messages.get(timeout=10)
                    if kind == "ready":
                        break
                    if kind == "error":
                        self.fail(message)
            finally:
                worker.stop.set()
                worker.thread.join(timeout=10)

        self.assertFalse(worker.thread.is_alive())
        self.assertIn("Board matches the solution", message)
        self.assertEqual(results["board"], SOLVED)
        self.assertEqual(results["clicks"], [0, 1, 1, 4, 4])

    def test_rejects_stale_board_before_clicking(self) -> None:
        self.page.evaluate('window.setCell(0, "S")')
        with self.assertRaisesRegex(BrowserSessionError, "board changed since"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [])

    def test_rejects_invalid_plan_before_clicking(self) -> None:
        bad = ActionPlan(self.plan.current, self.plan.solved, (CellAction(0, Cell.MOON, 2),))
        with self.assertRaisesRegex(BrowserSessionError, "click plan"):
            self.session.execute_actions(bad)
        self.assertEqual(self.page.evaluate("window.clicks"), [])

    def test_rejects_invalid_solution_before_clicking(self) -> None:
        rows = list(SOLVED.as_strings())
        rows[0] = "SSSSSS"
        invalid = Board.from_strings(tuple(rows))
        current = Board.from_strings(("??????",) * 6)
        plan = create_action_plan(current, invalid)
        with self.assertRaisesRegex(BrowserSessionError, "invalid click plan"):
            self.session.execute_actions(plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [])

    def test_stops_on_missed_click_without_retrying(self) -> None:
        self.page.evaluate('window.mode = "drop"')
        with patch("lockedin.tango.browser.STATE_TIMEOUT", 0.1):
            with self.assertRaisesRegex(BrowserSessionError, r"cell 0.*expected S, observed \?"):
                self.session.execute_actions(self.plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [0])

    def test_stops_on_unexpected_change(self) -> None:
        self.page.evaluate('window.mode = "wrong"')
        with self.assertRaisesRegex(BrowserSessionError, "unexpected board change"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [0])

    def test_stops_if_board_changes_between_actions(self) -> None:
        def mutate_after_first_action(done: int, total: int) -> None:
            if done == 1:
                self.page.evaluate('window.setCell(4, "S")')

        with self.assertRaisesRegex(BrowserSessionError, "board changed before cell 1"):
            self.session.execute_actions(self.plan, progress=mutate_after_first_action)
        self.assertEqual(self.page.evaluate("window.clicks"), [0])

    def test_reports_click_failure_without_retrying(self) -> None:
        self.page.evaluate('document.querySelector(\'[data-cell-idx="0"]\').style.display = "none"')
        with patch("lockedin.tango.browser.CLICK_TIMEOUT_MS", 100):
            with self.assertRaisesRegex(BrowserSessionError, "could not click cell 0"):
                self.session.execute_actions(self.plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [])

    def test_cancel_then_replan_from_partially_filled_board(self) -> None:
        stop = Event()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.execute_actions(self.plan, stop=stop, progress=lambda done, total: stop.set())
        self.assertEqual(self.page.evaluate("window.clicks"), [0])
        new_plan = self.session.plan_solution()
        self.session.execute_actions(new_plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [0, 1, 1, 4, 4])
        self.assertEqual(self.session.snapshot_board(), SOLVED)

    def test_checks_final_board_after_progress_callback(self) -> None:
        def mutate_after_last_action(done: int, total: int) -> None:
            if done == total:
                self.page.evaluate('window.setCell(0, "?")')

        with self.assertRaisesRegex(BrowserSessionError, "final board does not match"):
            self.session.execute_actions(self.plan, progress=mutate_after_last_action)

    def test_rejects_wrong_page_before_clicking(self) -> None:
        self.page.route("https://example.com/**", lambda route: route.fulfill(body="other page"))
        self.page.goto("https://example.com/")
        with self.assertRaisesRegex(BrowserSessionError, "no longer on the Tango page"):
            self.session.execute_actions(self.plan)

    def test_rejects_duplicate_cells_before_clicking(self) -> None:
        self.page.evaluate(
            """() => {
                const grid = document.querySelector('[data-testid="interactive-grid"]');
                grid.append(grid.firstElementChild.cloneNode(true));
            }"""
        )
        with self.assertRaisesRegex(BrowserSessionError, "could not read"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.page.evaluate("window.clicks"), [])
