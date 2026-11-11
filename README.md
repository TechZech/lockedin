# TechZech's LockedIn

LockedIn solves and plays LinkedIn Tango, Mini Sudoku, Zip, Queens, Patches,
and Wend using a Python desktop app or command-line interface.

> **Before you play:** The desktop app sends inputs to the game, including
> signed-in games. A board matching the solution does not necessarily mean
> LinkedIn registered completion. Automation depends on LinkedIn's current
> page layout and may stop with a partially completed board.

## Setup

Requirements: Python 3.12 or newer, Tkinter for the desktop app, and
Playwright's Chromium browser.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install chromium
```

On Windows, use `python -m venv .venv` and activate the environment with
`.venv\Scripts\activate` instead.
If Tkinter is missing, install Tk support for your Python interpreter. For
example, Homebrew Python 3.12 users can install `python-tk@3.12`.

## Desktop app

```bash
python -m lockedin ui
```

Choose a game and select:

- **Solve today's game** to open a dedicated browser and play your signed-in
  game. Sign in, complete verification, and start the game when prompted.
- **Practice run** to play in a separate, temporary signed-out browser.
  Practice also sends inputs; it is not a dry run.

Each game has its own persistent signed-in profile under `~/.lockedin/`.
These profiles contain sensitive login data; keep them private. Browsers remain
open for retries until you close them or the app. A retry in a practice browser
may encounter the previous board. Check the status message and terminal output
if a run stops; hover over or focus a long status message to read it in full.

**Target time** is shared by the two buttons for each game. Leave it blank or
enter `0` to finish as fast as possible. A positive whole number delays the
final input until the game timer reaches that many seconds; it is a minimum,
not a guarantee of an exact or recorded completion time. If the timer is
unavailable, the app reports that it is using an estimate. Estimates cannot
account for play before detection, pauses, or resets. Invalid, ambiguous, or
stalled timers stop execution before the final input.

### Game-specific notes

- **Mini Sudoku:** Turn **Notes OFF** before execution.
- **Zip:** Reset a partially drawn path before retrying. Wall detection depends
  on LinkedIn's current CSS.
- **Queens:** Check for unintended X marks after an interrupted run,
  especially on the last attempted cell.
- **Patches:** Remove incorrect patches if they prevent a new solution.
- **Wend:** Experimental. Its `wordfreq` dictionary is not LinkedIn's word
  list, so some puzzles may have no candidate or take a long time. A stopped
  run can leave locked words; reset the board before retrying. Completion is
  confirmed only when a recognizable results screen is detected.

Signed-in live flows other than Tango still need validation; Zip's live wall
rendering also needs validation. LinkedIn changes can break any game adapter.

## Command line

The CLI connects to an **already-running** Chromium browser over CDP. Start a
dedicated profile with remote debugging enabled, open the desired LinkedIn
game, and start its board:

```bash
/path/to/chromium --remote-debugging-port=9222 --user-data-dir=/path/to/dedicated-profile
```

Then, in another terminal with the environment activated:

```bash
python -m lockedin tango              # dry run: no browser inputs
python -m lockedin tango --execute    # play the board
python -m lockedin --help
python -m lockedin tango --help
```

Replace `tango` with `mini-sudoku`, `zip`, `queens`, `patches`, or `wend`.
The default CDP address is `http://127.0.0.1:9222`; use `--cdp-url` or
`--page-url-contains` to select a different endpoint or tab. Keep the debugging
endpoint and browser profile private.

Wend's dry run prints a candidate only when it is unique within its dictionary;
that does not verify LinkedIn's answer. Its `--execute` mode tries candidates.

## Development and tests

The game packages under [`src/lockedin/`](src/lockedin/) separate board models,
solvers, action planning, and browser adapters. Shared browser lifecycle code is
in [`browser.py`](src/lockedin/browser.py); [`gui.py`](src/lockedin/gui.py) and
[`cli.py`](src/lockedin/cli.py) provide the entry points.

Install the test dependency and run tests:

```bash
python -m pip install "pytest>=8.0"
python -m pytest -q
python -m pytest tests/test_tango_solver.py -q  # focused example
```

When adding solver behavior, prefer a general rule with a regression test over
a board-specific workaround. Browser-facing tests and live validation should
also cover parsing and action verification when those layers change.
