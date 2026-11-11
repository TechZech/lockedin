import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from lockedin.browser import BrowserSessionError
from lockedin.gui import ZipWorker
from lockedin.zip.actions import ActionPlan
from lockedin.zip.browser import ZIP_URL, ZipBrowserSession
from lockedin.zip.model import Board
from lockedin.zip.workflow import plan_board


GAME = """
<style>
  #grid { display: grid; grid-template-columns: repeat(2, 40px); }
  [data-cell-idx] { width: 40px; height: 40px; }
</style>
<div id="grid" data-testid="interactive-grid" data-trail-grid tabindex="0"></div>
<script>
const grid = document.querySelector('#grid');
window.moves = []; window.mode = 'normal'; let current = 0;
for (let i = 0; i < 4; i++) {
  const cell = document.createElement('div');
  cell.dataset.cellIdx = i; cell.dataset.testid = `cell-${i}`;
  cell.innerHTML = '<div class="i87nfu"></div>' +
    (i === 0 || i === 1 ? `<div data-cell-content>${i + 1}</div>` : '') +
    (i === 0 ? '<div data-testid="filled-cell"></div>' : '') +
    (i === 0 ? '<div class="i87nf0 i87nf3"></div>' : '');
  grid.append(cell);
}
grid.addEventListener('keydown', e => {
  window.moves.push(e.key);
  if (window.mode === 'drop') return;
  const delta = {ArrowUp: -2, ArrowDown: 2, ArrowLeft: -1, ArrowRight: 1}[e.key];
  if (!delta) return;
  current += delta;
  grid.children[current].insertAdjacentHTML('beforeend', '<div data-testid="filled-cell"></div>');
});
</script>
"""


class ZipBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        if not Path(cls.playwright.chromium.executable_path).exists():
            cls.playwright.stop()
            raise unittest.SkipTest("Playwright Chromium is not installed")
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route("https://www.linkedin.com/**",
                        lambda route: route.fulfill(content_type="text/html", body=GAME))
        self.page.goto(ZIP_URL)
        self.session = ZipBrowserSession(self.page, require_login=False)

    def test_snapshot_walls_and_verified_execution(self):
        self.session.wait_for_board(Event(), timeout=1)
        board = self.session.snapshot_board()
        self.assertEqual(board, Board(2, 2, (0, 1), frozenset({(0, 1)})))
        plan = plan_board(board)
        progress = []
        self.session.execute_actions(plan, progress=lambda n, total: progress.append((n, total)))
        self.assertEqual(self.page.evaluate("window.moves"), ["ArrowDown", "ArrowRight", "ArrowUp"])
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(self.session._snapshot().filled, frozenset(range(4)))

    def test_waits_for_timer_before_final_arrow(self):
        self.page.evaluate("""() => {
          const timer = document.createElement('span'); timer.textContent = '0:00';
          document.body.prepend(timer); window.inputTimes = [];
          document.querySelector('#grid').addEventListener(
            'keydown', () => window.inputTimes.push(timer.textContent), true);
          setTimeout(() => timer.textContent = '0:05', 1000);
        }""")
        self.session.execute_actions(plan_board(self.session.snapshot_board()), target_seconds=5)
        self.assertEqual(self.page.evaluate("window.inputTimes"), ["0:00", "0:00", "0:05"])

    def test_changed_board_during_wait_prevents_final_move(self):
        self.page.evaluate("""() => {
          const timer = document.createElement('span'); timer.textContent = '0:00';
          document.body.prepend(timer);
          setTimeout(() => {
            document.querySelector('[data-cell-idx="0"] [data-testid="filled-cell"]').remove();
          }, 300);
        }""")
        with self.assertRaisesRegex(BrowserSessionError, "changed while waiting"):
            self.session.execute_actions(plan_board(self.session.snapshot_board()), target_seconds=5)
        self.assertEqual(self.page.evaluate("window.moves"), ["ArrowDown", "ArrowRight"])

    def test_rejects_stale_partial_and_invalid_plans(self):
        plan = plan_board(self.session.snapshot_board())
        self.page.locator('[data-cell-idx="2"]').evaluate(
            """e => e.insertAdjacentHTML('beforeend', '<div data-testid="filled-cell"></div>')"""
        )
        with self.assertRaisesRegex(BrowserSessionError, "partial path"):
            self.session.execute_actions(plan)
        with self.assertRaisesRegex(BrowserSessionError, "action plan"):
            self.session.execute_actions(ActionPlan(plan.board, plan.path, ("ArrowUp",)))
        self.assertEqual(self.page.evaluate("window.moves"), [])

    def test_missed_move_stops_and_cancellation_prevents_input(self):
        plan = plan_board(self.session.snapshot_board())
        stop = Event()
        stop.set()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.execute_actions(plan, stop=stop)
        self.page.evaluate("window.mode = 'drop'")
        with patch("lockedin.zip.browser.STATE_TIMEOUT", 0.1):
            with self.assertRaisesRegex(BrowserSessionError, "timed out"):
                self.session.execute_actions(plan)
        self.assertEqual(self.page.evaluate("window.moves"), ["ArrowDown"])

    def test_unsupported_layout_fails_closed(self):
        self.page.locator('[data-cell-idx="0"] > div').first.evaluate("e => e.className = 'unknown'")
        with self.assertRaisesRegex(BrowserSessionError, "wall detection unavailable"):
            self.session.snapshot_board()

    def test_down_wall_and_mirrored_wall_marker(self):
        self.page.locator('[data-cell-idx="1"]').evaluate(
            """e => e.insertAdjacentHTML('beforeend',
              '<div class="i87nf0 i87nf2"></div><div class="i87nf0 i87nf4"></div>')"""
        )
        self.assertEqual(self.session.snapshot_board().walls, frozenset({(0, 1), (1, 3)}))

    def test_unrecognized_wall_marker_fails_closed(self):
        self.page.locator('[data-cell-idx="0"] .i87nf0').evaluate(
            "e => e.className = 'i87nf0 unknown'"
        )
        with self.assertRaisesRegex(BrowserSessionError, "Unsupported Zip wall"):
            self.session.snapshot_board()


class ZipWorkerTests(unittest.TestCase):
    @patch("lockedin.gui.ZipBrowserSession.launch_temporary")
    def test_test_mode_opens_and_executes(self, launch):
        session = launch.return_value
        session.snapshot_board.return_value = Board(2, 2, (0, 1))
        session.keep_alive.side_effect = lambda: Event().wait(0.01)
        worker = ZipWorker(Path("/unused"), test=True)
        worker.start()
        try:
            while True:
                kind, message = worker.messages.get(timeout=3)
                if kind == "ready":
                    self.assertIn("matches the solution", message)
                    break
                if kind == "error":
                    self.fail(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        session.open_zip.assert_called_once()
        session.execute_actions.assert_called_once()
        session.close.assert_called_once()
