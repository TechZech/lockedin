"""Command-line entry points for LockedIn."""

from __future__ import annotations

import argparse
import sys

from .tango.browser import BrowserSessionError, TangoBrowserSession
from .tango.workflow import solve_and_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lockedin")
    subcommands = parser.add_subparsers(dest="game", required=True)
    tango = subcommands.add_parser("tango", help="solve a LinkedIn Tango board")
    tango.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    tango.add_argument("--page-url-contains", default="linkedin.com")
    tango.add_argument("--execute", action="store_true", help="perform browser clicks")
    subcommands.add_parser("ui", help="open the desktop interface")
    args = parser.parse_args(argv)

    if args.game == "tango":
        return _run_tango(args)
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