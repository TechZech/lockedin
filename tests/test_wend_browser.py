import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

from lockedin.browser import BrowserSessionError
from lockedin.gui import WendWorker
from lockedin.wend.browser import WEND_URL, WendBrowserSession, _is_result_page
from lockedin.wend.dom import Snapshot
from lockedin.wend.model import Board


GAME = """
<style>
  #grid { display: grid; grid-template-columns: repeat(3, 45px); }
  [data-cell-idx] { width: 45px; height: 45px; }
</style>
<span id="timer">0:00</span>
<div data-testid="wend-game-board"><div id="grid" data-testid="interactive-grid" data-trail-grid></div></div>
<div data-testid="wend-word-list">
  <div data-testid="wend-word-list-row-0"><div data-testid="wend-word-list-slot-0-0"></div><div data-testid="wend-word-list-slot-0-1"></div><div data-testid="wend-word-list-slot-0-2"></div></div>
  <div data-testid="wend-word-list-row-1"><div data-testid="wend-word-list-slot-1-0"></div><div data-testid="wend-word-list-slot-1-1"></div><div data-testid="wend-word-list-slot-1-2"></div></div>
</div>
<button id="undo">Undo</button><button id="hint">Hint</button>
<script>
const grid = document.querySelector('#grid');
let path = [], rejected = null, accepted = 0;
window.attempts = []; window.hints = 0;
for (let i = 0; i < 6; i++) {
  const cell = document.createElement('div');
  cell.dataset.cellIdx = i; cell.dataset.testid = `cell-${i}`;
  cell.innerHTML = `<span>${'CATDOG'[i]}</span>`;
  grid.append(cell);
}
grid.addEventListener('mousedown', e => {
  const cell = e.target.closest('[data-cell-idx]');
  if (cell) path = [Number(cell.dataset.cellIdx)];
});
grid.addEventListener('mouseover', e => {
  const cell = e.target.closest('[data-cell-idx]');
  if (e.buttons && cell) {
    const index = Number(cell.dataset.cellIdx);
    if (path[path.length - 1] !== index) path.push(index);
  }
});
document.addEventListener('mouseup', () => {
  if (!path.length) return;
  const word = path.map(i => 'CATDOG'[i]).join('');
  window.attempts.push([word, document.querySelector('#timer').textContent]);
  const row = [...document.querySelectorAll('[data-testid^="wend-word-list-row-"]')]
    .find(e => !e.dataset.locked);
  const slots = row.querySelectorAll('[data-testid^="wend-word-list-slot-"]');
  [...slots].forEach((slot, i) => slot.textContent = word[i] || '');
  if (word === 'CAT' || word === 'DOG') {
    row.dataset.locked = 'true';
    path.forEach(i => grid.children[i].dataset.cellIsLocked = 'true');
    accepted++;
    if (accepted === 2 && !window.noWin)
      setTimeout(() => location.href = '/games/wend/results/guest/', 100);
  } else {
    rejected = row;
  }
  path = [];
});
document.querySelector('#undo').onclick = () => {
  if (rejected) rejected.querySelectorAll('[data-testid^="wend-word-list-slot-"]')
    .forEach(slot => slot.textContent = '');
  rejected = null;
};
document.querySelector('#hint').onclick = () => window.hints++;
</script>
"""

RESULT = "<body>Wend Test<br>Solved in 0:05</body>"


class FixtureSolver:
    def solutions(self, board, *, check=None):
        yield ((3, 4, 5), (2, 1, 0))
        yield ((3, 4, 5), (0, 1, 2))


class WendBrowserTests(unittest.TestCase):
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
        self.page.route("https://www.linkedin.com/**", lambda route: route.fulfill(
            content_type="text/html", body=RESULT if "/results/guest" in route.request.url else GAME))
        self.page.goto(WEND_URL)
        self.session = WendBrowserSession(self.page, require_login=False)
        self.session.wait_for_board(Event(), timeout=1)

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_rejected_word_is_undone_and_locked_word_preserved_until_win(self):
        progress = []
        statuses = []
        self.session.solve_trials(progress=lambda n, total: progress.append((n, total)),
                                  status=statuses.append)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertIn("trying TAC", " ".join(statuses))
        self.assertTrue(self.page.url.startswith(WEND_URL + "results/guest"))
        self.assertIn("Solved in", self.page.locator("body").inner_text())

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_timer_is_checked_before_final_word(self):
        self.page.evaluate("setTimeout(() => document.querySelector('#timer').textContent = '0:05', 1200)")
        self.page.route("https://www.linkedin.com/games/wend/results/guest/**",
                        lambda route: route.fulfill(content_type="text/html", body=RESULT))
        recorded = []
        original = self.session._draw_path
        def capture(path, stop):
            recorded.append((path, self.page.locator("#timer").inner_text()))
            original(path, stop)
        with patch.object(WendBrowserSession, "_draw_path", side_effect=capture):
            self.session.solve_trials(target_seconds=5)
        self.assertEqual(recorded[0][1], "0:00")
        self.assertTrue(all(time == "0:05" for _, time in recorded[1:]))

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_signed_in_execution_uses_locked_words_and_undo(self):
        self.session.require_login = True
        self.page.evaluate("window.noWin = true")
        self.page.evaluate("""document.addEventListener('mouseup', () => {
          if (window.attempts.length === 3) setTimeout(
            () => location.href = '/games/wend/results/', 100);
        })""")
        self.page.route("https://www.linkedin.com/games/wend/results/",
                        lambda route: route.fulfill(content_type="text/html", body=RESULT))
        statuses = []
        self.assertTrue(self.session.solve_trials(status=statuses.append))
        self.assertTrue(any("Signed-in game: trying TAC" in message for message in statuses))
        self.assertTrue(self.page.url.endswith("/games/wend/results/"))

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    @patch("lockedin.wend.browser.RESULT_TIMEOUT", 0.3)
    def test_signed_in_locked_board_without_result_is_unverified(self):
        self.session.require_login = True
        self.page.evaluate("window.noWin = true")
        self.assertFalse(self.session.solve_trials())
        self.assertEqual(self.page.evaluate("window.attempts.map(x => x[0])"), ["DOG", "TAC", "CAT"])
        self.assertEqual(self.page.evaluate("window.hints"), 0)

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_signed_in_expired_session_stops_before_inputs(self):
        self.session.require_login = True
        self.session._context = Mock()
        with patch.object(WendBrowserSession, "has_login_cookie", return_value=False):
            with self.assertRaisesRegex(BrowserSessionError, "sign-in expired"):
                self.session.solve_trials()
        self.assertEqual(self.page.evaluate("window.attempts"), [])

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_signed_in_final_word_respects_timer(self):
        self.session.require_login = True
        self.page.evaluate("setTimeout(() => document.querySelector('#timer').textContent = '0:05', 1200)")
        recorded = []
        original = self.session._draw_path
        def capture(path, stop):
            recorded.append((path, self.page.locator("#timer").inner_text()))
            original(path, stop)
        with patch.object(WendBrowserSession, "_draw_path", side_effect=capture):
            self.assertTrue(self.session.solve_trials(target_seconds=5))
        self.assertEqual(recorded[0][1], "0:00")
        self.assertTrue(all(time == "0:05" for _, time in recorded[1:]))

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_existing_selection_is_not_overwritten(self):
        self.page.locator('[data-cell-idx="0"]').evaluate("e => e.dataset.cellIsLocked = 'true'")
        with self.assertRaisesRegex(BrowserSessionError, "existing selections"):
            self.session.solve_trials()
        self.assertEqual(self.page.evaluate("window.attempts"), [])

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    @patch("lockedin.wend.browser.RESULT_TIMEOUT", 0.3)
    def test_locked_words_are_not_reported_as_win_without_results(self):
        self.page.evaluate("window.noWin = true")
        with self.assertRaisesRegex(BrowserSessionError, "did not confirm"):
            self.session.solve_trials()
        self.assertEqual(self.page.evaluate("window.hints"), 0)

    def test_cancellation_prevents_trials(self):
        stop = Event()
        stop.set()
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            self.session.solve_trials(stop=stop)
        self.assertEqual(self.page.evaluate("window.attempts"), [])

    @patch("lockedin.wend.browser.WendBrowserSession.has_login_cookie", return_value=True)
    def test_test_browser_that_was_signed_in_is_rejected(self, _cookie):
        self.session._context = object()
        with self.assertRaisesRegex(BrowserSessionError, "signed-out"):
            self.session.solve_trials()
        self.assertEqual(self.page.evaluate("window.attempts"), [])

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    def test_board_change_during_timer_wait_stops_before_final_word(self):
        self.page.evaluate("""setTimeout(() => {
          document.querySelector('[data-cell-idx="0"] span').textContent = 'X';
        }, 300)""")
        with self.assertRaisesRegex(BrowserSessionError, "changed while waiting"):
            self.session.solve_trials(target_seconds=10)
        self.assertEqual(self.page.evaluate("window.attempts.map(x => x[0])"), ["DOG"])

    @patch("lockedin.wend.browser.Solver", FixtureSolver)
    @patch("lockedin.wend.browser.MAX_ATTEMPTS", 1)
    def test_trial_limit_stops_without_a_win(self):
        with self.assertRaisesRegex(BrowserSessionError, "after 1 Wend word attempts"):
            self.session.solve_trials()
        self.assertEqual(self.page.evaluate("window.attempts.map(x => x[0])"), ["DOG"])


class WendWorkerTests(unittest.TestCase):
    @patch("lockedin.gui.WendBrowserSession.launch_persistent")
    def test_signed_in_worker_opens_persistent_profile_and_solves(self, launch):
        session = launch.return_value
        session.keep_alive.side_effect = lambda: Event().wait(0.01)
        session.solve_trials.return_value = False
        worker = WendWorker(Path("/unused"))
        worker.start(5)
        try:
            while True:
                kind, message = worker.messages.get(timeout=3)
                if kind == "ready":
                    self.assertIn("completion was not verified", message)
                    break
                if kind == "error":
                    self.fail(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        launch.assert_called_once_with(Path("/unused"))
        session.open_logged_in_wend.assert_called_once_with(worker.stop)
        self.assertEqual(session.solve_trials.call_args.kwargs["target_seconds"], 5)
        session.close.assert_called_once()

    @patch("lockedin.gui.WendBrowserSession.launch_temporary")
    def test_worker_uses_signed_out_trials_and_reports_confirmed_win(self, launch):
        session = launch.return_value
        session.keep_alive.side_effect = lambda: Event().wait(0.01)
        def solve(**kwargs):
            kwargs["progress"](1, 1)
            return True
        session.solve_trials.side_effect = solve
        worker = WendWorker(Path("/unused"), test=True)
        worker.start(5)
        try:
            while True:
                kind, message = worker.messages.get(timeout=3)
                if kind == "ready":
                    self.assertIn("confirmed completion", message)
                    break
                if kind == "error":
                    self.fail(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        session.open_wend.assert_called_once()
        self.assertEqual(session.solve_trials.call_args.kwargs["target_seconds"], 5)
        session.close.assert_called_once()


class WendResultRaceTests(unittest.TestCase):
    def test_result_detection_rejects_other_hosts_and_similar_paths(self):
        self.assertTrue(_is_result_page("https://www.linkedin.com/games/wend/results/"))
        self.assertFalse(_is_result_page("https://linkedin.com.example.com/games/wend/results/"))
        self.assertFalse(_is_result_page("https://www.linkedin.com/games/wend/results-fake"))

    def test_final_word_can_navigate_before_snapshot(self):
        page = Mock()
        page.url = WEND_URL + "results/"
        page.is_closed.return_value = False
        session = WendBrowserSession(page, require_login=True)
        expected = Snapshot(Board(1, 3, ("C", "A", "T"), (3,)), frozenset(), ("",))
        with patch.object(WendBrowserSession, "_won", return_value=True):
            self.assertTrue(session._wait_for_word(expected, (0, 1, 2), Event(), final=True))

    @patch("lockedin.wend.browser.RESULT_TIMEOUT", 0.01)
    def test_early_result_without_confirmation_does_not_claim_words_locked(self):
        page = Mock()
        page.url = WEND_URL + "results/"
        page.is_closed.return_value = False
        session = WendBrowserSession(page, require_login=True)
        expected = Snapshot(Board(1, 3, ("C", "A", "T"), (3,)), frozenset(), ("",))
        with patch.object(WendBrowserSession, "_won", return_value=False):
            with self.assertRaisesRegex(BrowserSessionError, "did not confirm"):
                session._wait_for_word(expected, (0, 1, 2), Event(), final=True)

    def test_navigation_between_url_check_and_snapshot_is_verified(self):
        page = Mock()
        page.url = WEND_URL
        page.is_closed.return_value = False
        session = WendBrowserSession(page, require_login=False)
        expected = Snapshot(Board(1, 3, ("C", "A", "T"), (3,)), frozenset({0, 1, 2}), ("CAT",))
        def navigating():
            page.url = WEND_URL + "results/guest/"
            raise BrowserSessionError("grid disappeared during navigation")
        with patch.object(WendBrowserSession, "_won", side_effect=[False, True]), \
                patch.object(WendBrowserSession, "_snapshot", side_effect=navigating):
            session._wait_for_win(expected, Event())

    def test_snapshot_failure_without_navigation_still_fails(self):
        page = Mock()
        page.url = WEND_URL
        page.is_closed.return_value = False
        session = WendBrowserSession(page, require_login=False)
        expected = Snapshot(Board(1, 3, ("C", "A", "T"), (3,)), frozenset({0, 1, 2}), ("CAT",))
        with patch.object(WendBrowserSession, "_won", return_value=False), \
                patch.object(WendBrowserSession, "_snapshot", side_effect=BrowserSessionError("bad board")):
            with self.assertRaisesRegex(BrowserSessionError, "bad board"):
                session._wait_for_win(expected, Event())
