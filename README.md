# TechZech's LockedIn

A Python project for solving and playing LinkedIn Tango and Mini Sudoku through
a verified, deterministic pipeline.

This repo is intentionally structured in phases:

1. solve the logical puzzle from its board and rules
2. validate the solver with regression tests
3. read a live board from a browser or a screen
4. plan and execute clicks safely
5. wrap it in a CLI and a repeatable workflow

The core idea is to keep the solver logic pure and testable, while leaving browser/page access and input execution behind explicit adapters.

---

## Project status

The end-to-end pipeline covers:

- live board capture / DOM snapshot
- logical board solving
- action planning
- safe click execution
- CLI orchestration

The solver and verified click executor have been tested locally and on live
Tango boards. Live page compatibility can change and needs continued validation.
Mini Sudoku has a separate 6x6 solver and browser adapter. Its signed-out live
flow and signed-in fixture flow are tested; the signed-in live flow still needs
validation.

The desktop UI opens either game in a dedicated browser, waits for the board,
prints the solution and action plan, and plays the signed-in game. Separate
signed-out test modes also perform verified inputs.

---

## Repository layout

```text
lockedin/
├── README.md
├── .gitignore
├── pyproject.toml
├── uv.lock
├── src/
│   └── lockedin/
│       ├── __init__.py
│       ├── __main__.py
│       ├── browser.py
│       ├── cli.py
│       ├── gui.py
│       ├── mini_sudoku/
│       │   ├── __init__.py
│       │   ├── actions.py
│       │   ├── browser.py
│       │   ├── dom.py
│       │   ├── model.py
│       │   ├── solver.py
│       │   └── workflow.py
│       └── tango/
│           ├── __init__.py
│           ├── actions.py
│           ├── browser.py
│           ├── dom.py
│           ├── model.py
│           ├── solver.py
│           └── workflow.py
├── tests/
│   ├── test_cli.py
│   ├── test_gui.py
│   ├── test_mini_sudoku.py
│   ├── test_mini_sudoku_browser.py
│   ├── test_tango_actions.py
│   ├── test_tango_browser.py
│   ├── test_tango_dom.py
│   ├── test_tango_dom_browser.py
│   ├── test_tango_execution_browser.py
│   ├── test_tango_login_browser.py
│   ├── test_tango_model.py
│   ├── test_tango_solver.py
│   └── test_tango_workflow.py
```

---

## Environment setup

From the repository root, create a Python 3.12+ virtual environment and install
the application and test dependency:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install "pytest>=8.0"
python -m playwright install chromium
```

If you are using the workspace environment already:

```bash
source .venv/bin/activate
```

---

## Important commands

### Desktop UI

The desktop UI requires Tkinter for the same Python interpreter used by the
project and a Playwright Chromium installation. On macOS, if using Homebrew
Python 3.12, install Tk with `brew install python-tk@3.12`. Then run:

```bash
source .venv/bin/activate
python -m lockedin ui
```

Click **Solve Tango**. The browser first opens LinkedIn's feed. If needed, sign
in and complete any verification in that browser; the app waits up to five
minutes for sign-in. Once signed in, it opens today's Tango game. Start the
game if prompted; the app waits up to another five minutes for the board.
The current board, solution, and proposed clicks are printed in the terminal.
The app then clicks cells in your signed-in game, checking each transition and
the final board. Keep the terminal open to see output. A matching board is not
confirmation that LinkedIn registered completion. If a check fails, the board may be partially filled;
retry to read it and create a fresh plan.

**Solve Tango Test** opens a separate, temporary, signed-out browser and goes
straight to Tango. It never uses the saved profile, so today's signed-in game is
untouched. The temporary browser remains open between test requests until the
desktop window closes, so a retry may encounter the previous board. After
printing the plan, test mode clicks the board, checking each transition and the
final board. It reports a match to the solution, not a confirmed game
completion. If a check fails, the run stops and the board may be partially
filled. Start a new run to read and plan again.

The browsers stay open until the desktop window is closed. Its separate profile
at `~/.lockedin/chromium-profile` retains your login between runs and contains
sensitive session data; keep it private. If sign-in times out, verification
blocks access, the board cannot be read, or the solver stalls, check the message
in the window and the terminal output, then click **Solve Tango** to retry.

**Solve Mini Sudoku** and **Solve Mini Sudoku Test** follow the same signed-in
and signed-out flows. The signed-in Sudoku browser uses a separate persistent
profile at `~/.lockedin/sudoku-chromium-profile`, so sign in there separately.
Both profiles contain sensitive session data; keep them private. The desktop
workflow clicks **Solve now** when the Mini Sudoku intro screen appears. Turn
**Notes OFF** before execution. The solver preserves existing numbers
and rejects invalid or ambiguous boards. It verifies the 2x3 region layout,
each cell selection and entry, and the final board; it does not verify game
completion. If execution stops, the board may be partially filled: retry to
read it and make a fresh plan.

Run the focused solver tests:

```bash
source .venv/bin/activate
python -m pytest tests/test_tango_solver.py -q
```

Run the full test suite:

```bash
source .venv/bin/activate
python -m pytest -q
```

Run the CLI help:

```bash
source .venv/bin/activate
python -m lockedin --help
```

The CLI connects to an already-running Chromium browser using CDP, by default at
`http://127.0.0.1:9222`. Start a dedicated Chromium profile with remote
debugging enabled, open LinkedIn Tango, and start the game before running the
CLI. For example, using the Playwright-installed Chromium executable:

```bash
/path/to/chromium --remote-debugging-port=9222 --user-data-dir=/path/to/dedicated-profile
```

The profile can contain sensitive login data; keep it private. Override the CDP
address with `--cdp-url` if needed. Run the Tango command in dry-run mode:

```bash
source .venv/bin/activate
python -m lockedin tango
```

Run the Tango command with explicit execution enabled:

```bash
source .venv/bin/activate
python -m lockedin tango --execute
```

If you want to call the installed entry point directly:

```bash
source .venv/bin/activate
lockedin tango --execute
```

For Mini Sudoku, open and start the game in the CDP browser, then run:

```bash
python -m lockedin mini-sudoku              # dry run
python -m lockedin mini-sudoku --execute    # enter the solution
```

The default page filter selects a Mini Sudoku game tab; use
`--page-url-contains` to select a different matching tab. Execution requires
Notes to be off. A signed-out game may run inside LinkedIn's game iframe.

---

## How the project works

### 1) Logical solver

The core of the project is the Tango solver in [src/lockedin/tango/solver.py](src/lockedin/tango/solver.py).

It works on a pure logical board representation:

- rows and columns are 6x6
- a cell can be SUN, MOON, or UNKNOWN
- row/column balance rules are enforced
- no three identical adjacent cells are allowed
- relation constraints enforce equal/opposite behavior

The solver uses iterative propagation and local contradiction checks. The important design principle is:

- keep the solver independent from browser code, screen capture, and automation
- prefer deterministic deduction rules over ad hoc heuristics
- only add a new rule when it is justified by a real failing puzzle case

### 2) Board and constraints model

The model layer is in [src/lockedin/tango/model.py](src/lockedin/tango/model.py).

It exposes:

- Cell enum
- Board object
- Constraint objects
- Relation enum
- validation checks for board shape and constraint correctness

This is the canonical structure passed into the solver.

### 3) Action planning

The action planning layer is in [src/lockedin/tango/actions.py](src/lockedin/tango/actions.py).

It takes:

- the current board
- the solved board

and produces a sequence of actions that converts the current board into the solved state.

The action planner is intentionally separate from the solver. Its assumed click
cycle is covered by local tests and was observed on one signed-out game.

The shared workflow in [src/lockedin/tango/workflow.py](src/lockedin/tango/workflow.py)
creates a plan from a board and reports it for both desktop and CLI use.

### 4) Browser session integration

The browser wrapper is in [src/lockedin/tango/browser.py](src/lockedin/tango/browser.py).

This layer is responsible for:

- connecting to Chromium over CDP
- locating the right LinkedIn page
- reading a board snapshot
- executing clicks on Tango cells
- keeping CLI execution behind an explicit execute switch

Both desktop buttons click cells: the normal button uses your signed-in game,
while the test button uses a separate signed-out browser. The CLI defaults to
a dry run and requires `--execute` to click. Execution
checks the board against the original plan, verifies each click, and stops on
an unexpected state without automatically retrying.

### 5) CLI entry point

The CLI is in [src/lockedin/cli.py](src/lockedin/cli.py).

Current supported command:

```bash
lockedin tango
```

`lockedin ui` launches the separate desktop workflow described above.

It currently supports:

- `--cdp-url`
- `--page-url-contains`
- `--execute`

This is the execution entry point for the live pipeline.

---

## How to add a new solver test

This is the workflow we have been using throughout development.

### 1) Define the board and constraints

Use `Board.from_strings(...)` and `Constraint(...)` exactly as in the tests.

Example:

```python
board = Board.from_strings(
    ("??MM??", "??????", "??????", "???MSS", "??????", "MS??MS"),
    (
        Constraint((0, 0), (0, 1), Relation.OPPOSITE),
        Constraint((0, 4), (0, 5), Relation.EQUAL),
        Constraint((2, 0), (2, 1), Relation.OPPOSITE),
        Constraint((2, 1), (2, 2), Relation.EQUAL),
        Constraint((5, 2), (5, 3), Relation.OPPOSITE),
    ),
)
```

### 2) Add the test to tests/test_tango_solver.py

The tests are all in the same class so they are easy to manage and run together.

### 3) Try the puzzle before deciding the expected answer

The workflow is:

- build the puzzle
- run `Solver().solve(board)`
- observe whether it solves or stalls
- if it stalls, inspect partial domains and look for the missing deduction pattern

### 4) If it stalls, print the partial board state

This is the standard debug loop we’ve been using:

```python
solver = Solver()
domains = solver._initial_domains(board)
queue, queued = solver._initial_queue(board)


def schedule(unit):
    if unit not in queued:
        queue.appendleft(unit)
        queued.add(unit)


def assign(position, value):
    if solver._assign(position, value, domains):
        solver._schedule_dependencies(position, board.constraints, schedule)

while queue:
    unit = queue.popleft(); queued.remove(unit)
    try:
        solver._process_unit(unit, board, domains, assign)
    except Exception:
        break

for r in range(6):
    row = []
    for c in range(6):
        v = domains[(r, c)]
        row.append('S' if v == SUN else 'M' if v == MOON else '?')
    print(''.join(row))
```

This tells us exactly where the current deduction logic gets stuck.

### 5) Turn the missing human observation into a general rule

We do not add a board-specific hack. We generalize the observation.

Examples of rule ideas already encountered:

- terminal-pair contradiction patterns such as `???ABB` / `BBA???`
- branch contradiction: if assuming a candidate forces an impossible local state, reject that candidate
- local chain propagation through equal/opposite constraints

### 6) Re-run the focused solver tests

After updating the solver, re-run:

```bash
source .venv/bin/activate
python -m pytest tests/test_tango_solver.py -q
```

### 7) Assert the full solved board

Once the board is solved, assert the whole board, not only a single cell.

Example:

```python
self.assertEqual(
    solved.as_strings(),
    ("MSMMSS", "SMSSMM", "SMMSSM", "MSMMSS", "SMSSMM", "MSSMMS"),
)
self.assertEqual(apply_actions(board, plan_actions(board, solved)), solved)
```

This gives a proper regression and proves the action plan matches the solved result.

---

## Next areas to improve

- Add solver regression cases when a real board exposes a missing deduction.
- Monitor live DOM and click-cycle compatibility as LinkedIn changes the game.
- Investigate a reliable game-completion signal before claiming completion.

---

## Safety notes

A few things are important before any live browser automation is attempted:

- CLI execution requires `--execute`; both desktop buttons explicitly play their respective games
- never assume a live page is valid without first confirming the board can be parsed
- treat browser automation as a separate step from solver correctness
- use dry-run output to validate board parsing and solve results before any click dispatch
- keep retries and failure logic bounded

---

## Verification checklist

Before claiming work is complete, the project should verify:

1. solver regression tests pass
2. action planning still reproduces solved boards
3. DOM/board parsing matches expected boards
4. browser session can find the correct page
5. CLI dry-run still works
6. execution only occurs under explicit user intent

The standard test commands are:

```bash
source .venv/bin/activate
python -m pytest tests/test_tango_solver.py -q
python -m pytest -q
```

---

## Summary

The project is currently in a healthy intermediate state:

- the solver is working and test-backed
- the repo has a clear architecture and CLI entry point
- live page compatibility and completion detection need ongoing validation
- all new solver additions follow a test-first, stall-debug-first workflow

The next milestone is not to “make it clever,” but to make it reliable and safe end-to-end.
