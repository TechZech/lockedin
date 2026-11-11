"""Command-line entry points for LockedIn."""

from __future__ import annotations

import argparse
import sys

from .tango.browser import BrowserSessionError, TangoBrowserSession
from .tango.workflow import solve_and_report
from .mini_sudoku.browser import MiniSudokuBrowserSession
from .mini_sudoku.workflow import solve_and_report as solve_sudoku_and_report
from .zip.browser import ZipBrowserSession
from .zip.workflow import solve_and_report as solve_zip_and_report
from .queens.browser import QueensBrowserSession
from .queens.workflow import solve_and_report as solve_queens_and_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lockedin")
    subcommands = parser.add_subparsers(dest="game", required=True)
    for game, description in (("tango", "Tango"), ("mini-sudoku", "Mini Sudoku"), ("zip", "Zip"),
                              ("queens", "Queens")):
        command = subcommands.add_parser(game, help=f"solve a LinkedIn {description} board")
        command.add_argument("--cdp-url", default="http://127.0.0.1:9222")
        command.add_argument("--page-url-contains", default=(
            f"linkedin.com/games/{game}" if game in ("mini-sudoku", "zip", "queens") else "linkedin.com"
        ))
        command.add_argument("--execute", action="store_true", help="perform browser clicks")
    subcommands.add_parser("ui", help="open the desktop interface")
    args = parser.parse_args(argv)

    if args.game == "tango":
        return _run_tango(args)
    if args.game == "mini-sudoku":
        return _run_sudoku(args)
    if args.game == "zip":
        return _run_zip(args)
    if args.game == "queens":
        return _run_queens(args)
    if args.game == "ui":
        from .gui import main as gui_main

        return gui_main()
    return 2


def _run_tango(args: argparse.Namespace) -> int:
    session = None
    try:
        session = TangoBrowserSession.connect_over_cdp(args.cdp_url, args.page_url_contains)
        plan = solve_and_report(session)
        if args.execute:
            session.execute_actions(plan)
            print("\nBoard matches the solution; game completion was not verified.")
        else:
            print("\nDry run only; no browser clicks were performed.")
        return 0
    except (BrowserSessionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        if args.execute:
            print("The board may be partially filled; run again to read and plan afresh.", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _run_sudoku(args: argparse.Namespace) -> int:
    session = None
    try:
        session = MiniSudokuBrowserSession.connect_over_cdp(args.cdp_url, args.page_url_contains)
        plan = solve_sudoku_and_report(session)
        if args.execute:
            session.execute_actions(plan)
            print("\nBoard matches the solution; game completion was not verified.")
        else:
            print("\nDry run only; no browser clicks were performed.")
        return 0
    except (BrowserSessionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        if args.execute:
            print("The board may be partially filled; run again to read and plan afresh.", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _run_zip(args: argparse.Namespace) -> int:
    session = None
    try:
        session = ZipBrowserSession.connect_over_cdp(args.cdp_url, args.page_url_contains)
        plan = solve_zip_and_report(session)
        if args.execute:
            session.execute_actions(plan)
            print("\nBoard matches the solution; game completion was not verified.")
        else:
            print("\nDry run only; no browser inputs were performed.")
        return 0
    except (BrowserSessionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        if args.execute:
            print("The path may be partially drawn; reset it before retrying.", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _run_queens(args: argparse.Namespace) -> int:
    session = None
    try:
        session = QueensBrowserSession.connect_over_cdp(args.cdp_url, args.page_url_contains)
        plan = solve_queens_and_report(session)
        if args.execute:
            session.execute_actions(plan)
            print("\nBoard matches the solution; game completion was not verified.")
        else:
            print("\nDry run only; no browser clicks were performed.")
        return 0
    except (BrowserSessionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        if args.execute:
            print("The board may be partially filled; run again to read and plan afresh.", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()