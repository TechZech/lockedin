from pathlib import Path
from threading import Event, Timer
from unittest.mock import Mock, patch

import pytest
from playwright.sync_api import sync_playwright

from lockedin.browser import BrowserSessionError
from lockedin.cli import main
from lockedin.gui import PatchesWorker
from lockedin.patches.browser import PATCHES_URL, PatchesBrowserSession
from lockedin.patches.model import Board, Clue, Patch, Shape


GAME = """
<style>
[data-testid=interactive-grid] { display:grid; grid-template-columns:repeat(3, 40px); width:120px; }
[data-cell-idx] { width:40px; height:40px; }
</style>
<span id="timer">0:00</span><div data-testid="interactive-grid" data-trail-grid></div>
<script>
const grid = document.querySelector('[data-testid=interactive-grid]');
window.moves = []; window.mode = 'normal'; let start = null;
const labels = [
  'Row 1, column 1, wide rectangle clue, 3 cells', 'Row 1, column 2', 'Row 1, column 3',
  'Row 2, column 1', 'Row 2, column 2', 'Row 2, column 3, wide rectangle clue, 3 cells'
];
for (let i = 0; i < 6; i++) {
  const cell = document.createElement('div');
  cell.dataset.cellIdx = i; cell.setAttribute('aria-label', labels[i]);
  cell.addEventListener('mousedown', () => { start = i; });
  cell.addEventListener('mouseup', () => {
    if (start === null) return;
    const end = i, first = start; start = null;
    window.moves.push([first, end, document.querySelector('#timer').textContent]);
    if (window.mode === 'drop') return;
    const apply = () => {
      const owner = first === 0 ? 0 : 5;
      const row = Math.floor(first / 3);
      for (let col = 0; col < 3; col++) {
        const index = row * 3 + col, element = grid.children[index];
        element.setAttribute('aria-label', labels[index] + (index === owner
          ? ', in drawn region'
          : `, in region with clue at row ${Math.floor(owner / 3) + 1}, column ${owner % 3 + 1}`));
      }
    };
    if (window.mode === 'delayed') setTimeout(apply, 75); else apply();
  });
  grid.append(cell);
}
</script>
"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Playwright Chromium is not installed")
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def session(browser):
    page = browser.new_page()
    page.route("https://www.linkedin.com/**", lambda route: route.fulfill(content_type="text/html", body=GAME))
    page.goto(PATCHES_URL)
    yield PatchesBrowserSession(page, require_login=False)
    page.close()


def test_drags_and_verifies_delayed_transitions(session):
    session.page.evaluate("window.mode = 'delayed'")
    session.wait_for_board(Event(), timeout=1)
    plan = session.plan_solution()
    progress = []
    session.execute_actions(plan, progress=lambda done, total: progress.append((done, total)))
    assert session.snapshot_board() == plan.solved
    assert session.page.evaluate("window.moves") == [[0, 2, "0:00"], [3, 5, "0:00"]]
    assert progress == [(1, 2), (2, 2)]


def test_final_patch_waits_for_game_timer(session):
    session.page.evaluate("setTimeout(() => document.querySelector('#timer').textContent = '0:05', 600)")
    session.execute_actions(session.plan_solution(), target_seconds=5)
    assert session.page.evaluate("window.moves") == [[0, 2, "0:00"], [3, 5, "0:05"]]


def test_changed_board_during_timer_wait_stops_before_final_drag(session):
    session.page.evaluate("""setTimeout(() => {
      document.querySelector('[data-cell-idx="3"]').setAttribute('aria-label', 'unexpected');
    }, 400)""")
    with pytest.raises(BrowserSessionError, match="could not read"):
        session.execute_actions(session.plan_solution(), target_seconds=5)
    assert len(session.page.evaluate("window.moves")) == 1


def test_estimated_timer_holds_final_patch(session):
    session.page.locator("#timer").evaluate("(e) => e.style.display = 'none'")
    session.mark_board_ready()
    started = session.page.evaluate("performance.now()")
    session.page.evaluate("""window.times = [];
      document.querySelector('[data-testid=interactive-grid]').addEventListener(
        'mouseup', () => window.times.push(performance.now()), true)""")
    statuses = []
    session.execute_actions(session.plan_solution(), target_seconds=1, status=statuses.append)
    times = session.page.evaluate("window.times")
    assert times[0] - started < 1000 <= times[1] - started
    assert any("estimated timer" in message for message in statuses)


def test_resume_preserves_existing_patch(session):
    plan = session.plan_solution()
    session._draw_patch(plan.actions[0], plan.current.columns)
    resumed = session.plan_solution()
    assert resumed.current.patches == (Patch(0, 0, 0, 2),)
    assert resumed.actions == (Patch(1, 0, 1, 2),)
    session.execute_actions(resumed)
    assert session.snapshot_board() == resumed.solved


def test_dropped_drag_stops_without_next_move(session):
    session.page.evaluate("window.mode = 'drop'")
    with patch("lockedin.patches.browser.STATE_TIMEOUT", 0.1):
        with pytest.raises(BrowserSessionError, match="timed out"):
            session.execute_actions(session.plan_solution())
    assert len(session.page.evaluate("window.moves")) == 1


def test_cancelled_execution_makes_no_moves(session):
    plan = session.plan_solution()
    stop = Event()
    stop.set()
    with pytest.raises(BrowserSessionError, match="cancelled"):
        session.execute_actions(plan, stop=stop)
    assert session.page.evaluate("window.moves") == []


def test_changed_board_before_execution_makes_no_moves(session):
    plan = session.plan_solution()
    session._draw_patch(plan.actions[0], plan.current.columns)
    with pytest.raises(BrowserSessionError, match="board changed"):
        session.execute_actions(plan)
    assert len(session.page.evaluate("window.moves")) == 1


def test_cancel_during_timer_wait_makes_no_final_move(session):
    stop = Event()
    plan = session.plan_solution()
    cancellation = Timer(0.3, stop.set)

    def on_progress(done, total):
        if done == total - 1:
            cancellation.start()

    try:
        with pytest.raises(BrowserSessionError, match="cancelled"):
            session.execute_actions(plan, stop=stop, progress=on_progress, target_seconds=5)
    finally:
        cancellation.cancel()
        cancellation.join()
    assert len(session.page.evaluate("window.moves")) == 1


def test_cli_dry_run_and_execute(session):
    with patch("lockedin.cli.PatchesBrowserSession.connect_over_cdp", return_value=session):
        assert main(["patches"]) == 0
        assert session.page.evaluate("window.moves") == []
        assert main(["patches", "--execute"]) == 0
        assert len(session.page.evaluate("window.moves")) == 2


def test_patches_worker_uses_separate_temporary_mode():
    worker = PatchesWorker(test=True)
    assert worker.test
    assert worker.adapter.name == "Patches"
    assert worker.profile.name == "patches-chromium-profile"


def test_patches_worker_passes_timer_and_reports_patch_progress():
    fake = Mock()
    fake.snapshot_board.return_value = Board(1, 2, (Clue(0, Shape.WIDE, 2),))
    fake.keep_alive.side_effect = lambda: Event().wait(0.01)
    fake.execute_actions.side_effect = lambda plan, **kwargs: kwargs["progress"](1, 1)
    with patch("lockedin.gui.PatchesBrowserSession.launch_temporary", return_value=fake):
        worker = PatchesWorker(test=True)
        worker.start(5)
        statuses = []
        try:
            while True:
                kind, message = worker.messages.get(timeout=5)
                if kind == "ready":
                    assert "matches the solution" in message
                    break
                assert kind != "error", message
                if kind == "status":
                    statuses.append(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=3)
        assert "Test mode: filled 1/1 patches." in statuses
        fake.open_patches.assert_called_once()
        assert fake.execute_actions.call_args.kwargs["target_seconds"] == 5
