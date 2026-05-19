#!/usr/bin/env python3
"""Small CLI for Hermes WebUI gather reports.

Run from the Hermes WebUI repository root:

  python scripts/hermes-gather.py create --title "Save flow repro" --json
  python scripts/hermes-gather.py show REPORT_ID --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api import gather  # noqa: E402


def _emit(payload: dict, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    report = payload.get("report") or {}
    print(f"Report: {report.get('title') or report.get('id')}")
    if report.get("id"):
        print(f"ID: {report['id']}")
    if report.get("path"):
        print(f"Path: {report['path']}")
    ingest = payload.get("ingest") or {}
    if ingest:
        print(f"Ingest path: {ingest.get('path')}")
        print(f"Token header: {ingest.get('tokenHeader')}")
        print(f"Token: {ingest.get('token')}")
    if "events" in payload:
        print(f"Events: {len(payload.get('events') or [])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and inspect Hermes WebUI gather reports")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="Create a gather report and print its ingest endpoint")
    create.add_argument("--title", default="Gather report")
    create.add_argument("--session-id", default="")
    create.add_argument("--workspace", default="")
    create.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show a gather report and its events")
    show.add_argument("report_id")
    show.add_argument("--json", action="store_true")

    list_cmd = sub.add_parser("list", help="List recent gather reports")
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "create":
            return _emit(
                gather.create_gather_report(
                    args.title,
                    session_id=args.session_id,
                    workspace=args.workspace,
                ),
                as_json=args.json,
            )
        if args.cmd == "show":
            return _emit(gather.show_gather_report(args.report_id), as_json=args.json)
        if args.cmd == "list":
            payload = gather.list_gather_reports(limit=max(1, args.limit))
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                for report in payload.get("reports", []):
                    print(f"{report.get('id')}\t{report.get('eventCount', 0)}\t{report.get('title', '')}")
            return 0
    except gather.GatherError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
