from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import pytest
from playwright.sync_api import sync_playwright

from lockedin.browser import BrowserSessionError
from lockedin.cli import main
from lockedin.gui import QueensWorker
from lockedin.queens.browser import QUEENS_URL, QueensBrowserSession, _valid_transition
from lockedin.queens.model import Board, Cell


GAME = """
<style>[data-cell-idx] { width: 40px; height: 25px; display: inline-block; }</style>
<span id="timer">0:00</span>
<section id="queens-game-board"><div data-testid="interactive-grid"></div></section>
<script>
const grid = document.querySelector('[data-testid="interactive-grid"]');
window.clicks = []; window.mode = 'normal';
const update = cell => {
  const i = Number(cell.dataset.cellIdx);
  cell.setAttribute('aria-label',
    `${cell.dataset.state} of color ${Math.floor(i / 4)}, row ${Math.floor(i / 4) + 1}, column ${i % 4 + 1}`);
};
for (let i = 0; i < 16; i++) {
  const cell = document.createElement('div');
  cell.dataset.cellIdx = i; cell.dataset.state = i === 2 ? 'Cross' : 'Empty cell';
  cell.dataset.testid = 'cell-' + i;
  update(cell);
  cell.addEventListener('click', () => {
    window.clicks.push([i, document.querySelector('#timer').textContent]);
    if (window.mode === 'drop') return;
    const apply = () => {
      cell.dataset.state = {'Empty cell': 'Cross', 'Cross': 'Queen', 'Queen': 'Empty cell'}[cell.dataset.state];
      update(cell);
      if (cell.dataset.state === 'Queen' && window.mode.startsWith('auto')) {
        for (const other of grid.children) {
          const j = Number(other.dataset.cellIdx);
          const sameRow = Math.floor(i / 4) === Math.floor(j / 4);
          const sameColumn = i % 4 === j % 4;
          const adjacent = Math.abs(Math.floor(i / 4) - Math.floor(j / 4)) <= 1
            && Math.abs(i % 4 - j % 4) <= 1;
          if (other.dataset.state === 'Empty cell' && (sameRow || sameColumn || adjacent)) {
            other.dataset.state = 'Cross'; update(other);
          }
        }
        if (window.mode === 'auto-wrong') {
          const wrong = grid.children[7];
          wrong.dataset.state = 'Cross'; update(wrong);
        }
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
    page.goto(QUEENS_URL)
    yield QueensBrowserSession(page, require_login=False)
    page.close()


def test_executes_and_verifies_each_delayed_transition(session):
    session.page.evaluate("window.mode = 'delayed'")
    session.wait_for_board(Event(), timeout=1)
    plan = session.plan_solution()
    progress = []
    session.execute_actions(plan, progress=lambda done, total: progress.append((done, total)))
    assert session.snapshot_board() == plan.solved
    assert [entry[0] for entry in session.page.evaluate("window.clicks")] == [1, 1, 7, 7, 8, 8, 14, 14]
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_automatic_crosses_are_accepted_and_final_board_verified(session):
    session.page.evaluate("window.mode = 'auto'")
    plan = session.plan_solution()
    session.execute_actions(plan)
    observed = session.snapshot_board()
    assert [index for index in range(16)
            if observed.cells[index // 4][index % 4].value == 'queen'] == [1, 7, 8, 14]
    assert observed.cells[0][0].value == 'cross'
    assert len(session.page.evaluate("window.clicks")) == 8


def test_automatic_cross_on_future_queen_stops_execution(session):
    session.page.evaluate("window.mode = 'auto-wrong'")
    with pytest.raises(BrowserSessionError, match="unexpected board change"):
        session.execute_actions(session.plan_solution())
    assert len(session.page.evaluate("window.clicks")) == 2


def test_automatic_crosses_respect_regions_and_preserve_existing_marks():
    regions = tuple(tuple(row) for row in ("AABC", "AABC", "AABC", "DDBC"))
    cells = tuple(tuple(Cell.EMPTY for _ in range(4)) for _ in range(4))
    before = Board(regions, cells).with_cell(0, Cell.CROSS).with_cell(7, Cell.CROSS)
    after = before.with_cell(0, Cell.QUEEN)
    solved = after.with_cell(5, Cell.QUEEN)
    assert _valid_transition(before, after, solved, after.with_cell(9, Cell.CROSS), 0)
    assert not _valid_transition(before, after, solved, after.with_cell(5, Cell.CROSS), 0)
    assert not _valid_transition(before, after, solved, after.with_cell(10, Cell.CROSS), 0)
    assert not _valid_transition(before, after, solved, after.with_cell(7, Cell.EMPTY), 0)
    assert not _valid_transition(before, after, solved, after.with_cell(1, Cell.QUEEN), 0)
    empty = before.with_cell(0, Cell.EMPTY)
    assert not _valid_transition(empty, before, solved, before.with_cell(1, Cell.CROSS), 0)


def test_automatic_crosses_still_hold_last_click_for_timer(session):
    session.page.evaluate("""() => {
      window.mode = 'auto';
      setTimeout(() => document.querySelector('#timer').textContent = '0:05', 900);
    }""")
    session.execute_actions(session.plan_solution(), target_seconds=5)
    times = [entry[1] for entry in session.page.evaluate("window.clicks")]
    assert times == ["0:00"] * 7 + ["0:05"]


def test_timer_holds_only_final_click(session):
    session.page.evaluate("setTimeout(() => document.querySelector('#timer').textContent = '0:05', 900)")
    plan = session.plan_solution()
    session.execute_actions(plan, target_seconds=5)
    times = [entry[1] for entry in session.page.evaluate("window.clicks")]
    assert times == ["0:00"] * 7 + ["0:05"]
    assert session.snapshot_board() == plan.solved


def test_missing_timer_uses_estimate_for_final_click(session):
    session.page.locator("#timer").evaluate("(e) => e.style.display = 'none'")
    session.page.evaluate("""() => {
      window.clickTimes = [];
      document.querySelector('[data-testid="interactive-grid"]').addEventListener(
        'click', () => window.clickTimes.push(performance.now()), true);
    }""")
    plan = session.plan_solution()
    started = session.page.evaluate("performance.now()")
    session.mark_board_ready()
    statuses = []
    session.execute_actions(plan, target_seconds=1, status=statuses.append)
    times = session.page.evaluate("window.clickTimes")
    assert times[-2] - started < 1000
    assert times[-1] - started >= 1000
    assert any("estimated timer" in status for status in statuses)
    assert session.snapshot_board() == plan.solved


def test_timer_disappears_during_wait_and_estimate_completes(session):
    session.page.evaluate("""() => {
      window.clickTimes = [];
      document.querySelector('[data-testid="interactive-grid"]').addEventListener(
        'click', () => window.clickTimes.push(performance.now()), true);
      setTimeout(() => document.querySelector('#timer').style.display = 'none', 500);
    }""")
    plan = session.plan_solution()
    started = session.page.evaluate("performance.now()")
    statuses = []
    session.execute_actions(plan, target_seconds=1, status=statuses.append)
    times = session.page.evaluate("window.clickTimes")
    assert times[-2] - started < 500
    assert times[-1] - started >= 1000
    assert any("estimated timer" in status for status in statuses)
    assert session.snapshot_board() == plan.solved


def test_missing_timer_board_change_still_prevents_final_click(session):
    session.page.locator("#timer").evaluate("(e) => e.style.display = 'none'")
    plan = session.plan_solution()
    session.page.evaluate("""setTimeout(() => {
      const cell = document.querySelector('[data-cell-idx="3"]');
      cell.setAttribute('aria-label', 'Cross of color 0, row 1, column 4');
    }, 500)""")
    with pytest.raises(BrowserSessionError, match="changed while waiting"):
        session.execute_actions(plan, target_seconds=2)
    assert len(session.page.evaluate("window.clicks")) == 7


def test_cancellation_and_changed_board_during_timer_wait(session):
    plan = session.plan_solution()
    session.page.evaluate("""setTimeout(() => {
      const cell = document.querySelector('[data-cell-idx="3"]');
      cell.setAttribute('aria-label', 'Cross of color 0, row 1, column 4');
    }, 800)""")
    with pytest.raises(BrowserSessionError, match="changed while waiting"):
        session.execute_actions(plan, target_seconds=5)
    assert len(session.page.evaluate("window.clicks")) == 7
    stop = Event()
    stop.set()
    with pytest.raises(BrowserSessionError, match="cancelled"):
        session.execute_actions(plan, stop=stop)


def test_stale_plan_and_missing_transition_stop_execution(session):
    plan = session.plan_solution()
    session.page.locator('[data-cell-idx="3"]').evaluate(
        "(e) => e.setAttribute('aria-label', 'Cross of color 0, row 1, column 4')"
    )
    with pytest.raises(BrowserSessionError, match="changed since"):
        session.execute_actions(plan)
    assert session.page.evaluate("window.clicks") == []
    session.page.evaluate("window.mode = 'drop'")
    with patch("lockedin.queens.browser.STATE_TIMEOUT", 0):
        with pytest.raises(BrowserSessionError, match="timed out"):
            session.execute_actions(session.plan_solution())
    assert len(session.page.evaluate("window.clicks")) == 1


def test_worker_forwards_queens_plan_and_target(session):
    fake = Mock()
    fake.snapshot_board.return_value = session.snapshot_board()
    fake.keep_alive.side_effect = lambda: Event().wait(0.01)
    with patch("lockedin.gui.QueensBrowserSession.launch_temporary", return_value=fake):
        worker = QueensWorker(Path("/unused"), test=True)
        worker.start(17)
        try:
            while True:
                kind, message = worker.messages.get(timeout=5)
                if kind == "ready":
                    break
                if kind == "error":
                    pytest.fail(message)
        finally:
            worker.stop.set()
            worker.thread.join(timeout=5)
        fake.open_queens.assert_called_once_with()
        assert fake.execute_actions.call_args.kwargs["target_seconds"] == 17
        fake.close.assert_called_once()


def test_cli_defaults_to_dry_run_and_execute_is_explicit(session):
    with patch("lockedin.cli.QueensBrowserSession.connect_over_cdp", return_value=session), \
            patch.object(QueensBrowserSession, "close"), \
            patch.object(QueensBrowserSession, "execute_actions") as execute:
        assert main(["queens"]) == 0
        execute.assert_not_called()
        assert main(["queens", "--execute"]) == 0
        execute.assert_called_once()
