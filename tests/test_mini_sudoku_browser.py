import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from lockedin.gui import MiniSudokuWorker
from lockedin.mini_sudoku.actions import ActionPlan, CellAction, create_action_plan
from lockedin.mini_sudoku.browser import BrowserSessionError, MiniSudokuBrowserSession, SUDOKU_URL
from lockedin.mini_sudoku.model import Board
from lockedin.browser import FEED_URL


SOLVED = Board.from_strings(("354216", "612345", "126534", "543621", "435162", "261453"))
GAME_URL = "https://www.linkedin.com/games/view/mini-sudoku/desktop"
LAUNCH = '<iframe title="games" src="/games/view/mini-sudoku/desktop"></iframe>'
GAME = """
<style>.sudoku-cell { width: 40px; height: 20px; }</style>
<section data-sudoku-grid="true"></section>
<div data-control-btn="notes"><span class="sudoku-under-board__text--disabled">OFF</span></div>
<div id="keypad"></div>
<script>
(() => {
const solution = "354216612345126534543621435162261453";
const grid = document.querySelector('[data-sudoku-grid]');
window.mode = "normal"; window.clicks = []; let selected = null;
for (let i = 0; i < 36; i++) {
  const cell = document.createElement('div');
  cell.className = 'sudoku-cell';
  cell.dataset.cellIdx = i;
  const row = Math.floor(i / 6), col = i % 6;
  for (const [direction, condition] of [
    ['right', col === 2], ['left', col === 3],
    ['bottom', row === 1 || row === 3], ['top', row === 2 || row === 4]
  ]) if (condition) cell.classList.add('sudoku-cell-wall-' + direction);
  cell.innerHTML = '<div class="sudoku-cell-content"></div>';
  cell.firstElementChild.textContent = [0, 1, 2].includes(i) ? '' : solution[i];
  cell.addEventListener('click', () => {
    if (window.mode === 'selection-fail') return;
    for (const c of grid.children) c.classList.remove('sudoku-cell-active');
    selected = cell; cell.classList.add('sudoku-cell-active');
  });
  grid.append(cell);
}
for (let n = 1; n <= 6; n++) {
  const button = document.createElement('button');
  button.className = 'sudoku-input-button'; button.dataset.number = n;
  button.textContent = n;
  button.addEventListener('click', () => {
    window.clicks.push([Number(selected.dataset.cellIdx), n]);
    if (window.mode === 'drop') return;
    if (window.mode === 'wrong') grid.children[3].firstElementChild.textContent = '1';
    const apply = () => selected.firstElementChild.textContent = n;
    if (window.mode === 'delayed') setTimeout(apply, 75); else apply();
  });
  document.querySelector('#keypad').append(button);
}
})();
</script>
"""

INTRO_GAME = GAME.replace(
    '<section data-sudoku-grid="true"></section>',
    '<button id="launch-footer-start-button">Solve now</button>'
    '<div id="playable" style="display:none"><section data-sudoku-grid="true"></section>',
).replace(
    '<div id="keypad"></div>',
    '<div id="keypad"></div></div>',
).replace(
    'const solution =',
    '''window.starts = 0;
document.querySelector('#launch-footer-start-button').addEventListener('click', () => {
  window.starts++;
  document.querySelector('#playable').style.display = 'block';
  document.querySelector('#launch-footer-start-button').remove();
});
const solution =''',
)


def install_routes(page, *, intro=False):
    page.route("https://www.linkedin.com/**", lambda route: route.fulfill(
        content_type="text/html",
        body=("Feed" if route.request.url == FEED_URL else
              (INTRO_GAME if intro else GAME) if route.request.url == GAME_URL else LAUNCH),
    ))


class MiniSudokuBrowserTests(unittest.TestCase):
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
        install_routes(self.page)
        self.page.goto(SUDOKU_URL)
        self.session = MiniSudokuBrowserSession(self.page, require_login=False)
        self.frame = self.page.frame(url=GAME_URL)
        self.plan = create_action_plan(self.session.snapshot_board(), SOLVED)

    def test_execute_verifies_delayed_updates(self):
        self.frame.evaluate('window.mode = "delayed"')
        progress = []
        self.session.execute_actions(self.plan, progress=lambda done, total: progress.append((done, total)))
        self.assertEqual(self.session.snapshot_board(), SOLVED)
        self.assertEqual(self.frame.evaluate("window.clicks"), [[0, 3], [1, 5], [2, 4]])
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])

    def test_intro_hidden_board_is_not_read_until_game_is_started(self):
        self.frame.set_content(INTRO_GAME)
        with self.assertRaisesRegex(BrowserSessionError, "board not found"):
            self.session.snapshot_board()
        self.session.wait_for_board(Event(), timeout=3)
        self.assertEqual(self.frame.evaluate("window.starts"), 1)
        plan = create_action_plan(self.session.snapshot_board(), SOLVED)
        self.session.execute_actions(plan)
        self.assertEqual(self.session.snapshot_board(), SOLVED)

    def test_ready_board_is_not_restarted(self):
        self.session.wait_for_board(Event(), timeout=1)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])

    def test_hidden_board_never_becomes_ready_without_start_control(self):
        self.frame.locator('[data-sudoku-grid="true"]').evaluate("(e) => e.style.display = 'none'")
        with self.assertRaisesRegex(BrowserSessionError, "timed out"):
            self.session.wait_for_board(Event(), timeout=0)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])

    def test_intro_start_is_not_clicked_after_cancellation_or_expired_login(self):
        self.frame.set_content(INTRO_GAME)
        stop = Event()
        stop.set()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.wait_for_board(stop)
        self.session._context = self.page.context
        self.session.require_login = True
        with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
            self.session.wait_for_board(Event(), timeout=1)
        self.assertEqual(self.frame.evaluate("window.starts"), 0)

    def test_stale_board_and_bad_plan_are_rejected_before_input(self):
        self.frame.locator('[data-cell-idx="0"] .sudoku-cell-content').evaluate("(e) => e.textContent = '3'")
        with self.assertRaisesRegex(BrowserSessionError, "board changed since"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])
        bad = ActionPlan(self.plan.current, SOLVED, (CellAction(0, 2),))
        with self.assertRaisesRegex(BrowserSessionError, "action plan"):
            self.session.execute_actions(bad)

    def test_notes_and_failed_selection_are_rejected(self):
        self.frame.locator('[data-control-btn="notes"] span').evaluate(
            "(e) => e.className = 'sudoku-under-board__text--active'"
        )
        with self.assertRaisesRegex(BrowserSessionError, "Notes OFF"):
            self.session.execute_actions(self.plan)
        self.frame.locator('[data-control-btn="notes"] span').evaluate(
            "(e) => e.className = 'sudoku-under-board__text--disabled'"
        )
        self.frame.evaluate('window.mode = "selection-fail"')
        with self.assertRaisesRegex(BrowserSessionError, "not selected"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])

    def test_missed_input_and_unexpected_change_stop_execution(self):
        self.frame.evaluate('window.mode = "drop"')
        with patch("lockedin.mini_sudoku.browser.STATE_TIMEOUT", 0.1):
            with self.assertRaisesRegex(BrowserSessionError, "timed out"):
                self.session.execute_actions(self.plan)
        self.assertEqual(len(self.frame.evaluate("window.clicks")), 1)
        self.frame.evaluate('window.mode = "wrong"')
        with self.assertRaisesRegex(BrowserSessionError, "unexpected board change"):
            self.session.execute_actions(self.plan)
        self.assertEqual(len(self.frame.evaluate("window.clicks")), 2)

    def test_unsupported_regions_fail_closed(self):
        self.frame.locator('[data-cell-idx="2"]').evaluate(
            "(e) => e.classList.remove('sudoku-cell-wall-right')"
        )
        with self.assertRaisesRegex(BrowserSessionError, "region layout"):
            self.session.snapshot_board()

    def test_cancelled_sign_in_and_board_wait_do_not_navigate_or_click(self):
        stop = Event()
        stop.set()
        self.session._context = self.page.context
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.open_logged_in_sudoku(stop)
        self.assertEqual(self.page.url, SUDOKU_URL)
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.wait_for_board(stop)
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.execute_actions(self.plan, stop=stop)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])

    def test_cancellation_between_entries_stops_without_more_input(self):
        stop = Event()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.execute_actions(
                self.plan, stop=stop, progress=lambda done, total: stop.set()
            )
        self.assertEqual(self.frame.evaluate("window.clicks"), [[0, 3]])

    def test_expired_login_stops_before_board_or_execution(self):
        self.session._context = self.page.context
        self.session.require_login = True
        with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
            self.session.wait_for_board(Event())
        with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
            self.session.execute_actions(self.plan)
        self.assertEqual(self.frame.evaluate("window.clicks"), [])

    def test_signed_out_mode_does_not_require_a_login_cookie(self):
        self.session._context = self.page.context
        self.session.wait_for_board(Event())
        self.session.execute_actions(self.plan)
        self.assertEqual(self.session.snapshot_board(), SOLVED)

    def test_login_expiring_between_entries_stops_execution(self):
        self.page.context.add_cookies(
            [{"name": "li_at", "value": "test", "url": "https://www.linkedin.com"}]
        )
        self.session._context = self.page.context
        self.session.require_login = True
        with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
            self.session.execute_actions(
                self.plan, progress=lambda done, total: self.page.context.clear_cookies()
            )
        self.assertEqual(self.frame.evaluate("window.clicks"), [[0, 3]])


class MiniSudokuWorkerTests(unittest.TestCase):
    def run_worker(self, test):
        result = {}

        def launch(*args):
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            if not test:
                context.add_cookies([{"name": "li_at", "value": "test", "url": "https://www.linkedin.com"}])
            page = context.new_page()
            install_routes(page, intro=True)
            return MiniSudokuBrowserSession(
                page, _playwright=playwright, _browser=browser, _context=context,
                require_login=not test, _owns_browser=True,
            )

        execute = MiniSudokuBrowserSession.execute_actions

        def record(session, plan, **kwargs):
            result["starts"] = session._game_frame().evaluate("window.starts")
            execute(session, plan, **kwargs)
            result["board"] = session.snapshot_board()

        worker = MiniSudokuWorker(Path("/test/profile"), test=test)
        launch_method = "launch_temporary" if test else "launch_persistent"
        with (patch.object(MiniSudokuBrowserSession, launch_method, side_effect=launch),
              patch.object(MiniSudokuBrowserSession, "execute_actions", new=record)):
            worker.start()
            try:
                while True:
                    kind, message = worker.messages.get(timeout=15)
                    if kind == "ready":
                        break
                    if kind == "error":
                        self.fail(message)
            finally:
                worker.stop.set()
                worker.thread.join(timeout=10)
        self.assertFalse(worker.thread.is_alive())
        self.assertIn("matches the solution", message)
        self.assertEqual(result["board"], SOLVED)
        self.assertEqual(result["starts"], 1)

    def test_signed_out_worker(self):
        self.run_worker(True)

    def test_signed_in_worker(self):
        self.run_worker(False)
