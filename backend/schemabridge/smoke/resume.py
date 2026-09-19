"""Verify a paused run survives the process ending.

This is the assumption the whole human-in-the-loop design rests on. Each HTTP
request runs in a different process, so if `interrupt()` only paused in memory,
every escalation would be lost the moment the reviewer took more than one
request to answer. Run with `--phase start` then `--phase resume` to prove the
two halves share nothing but a thread id and the database.

    python -m schemabridge.smoke.resume --phase start  --thread demo-1
    python -m schemabridge.smoke.resume --phase resume --thread demo-1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from langgraph.types import Command

from schemabridge.domain.models import (
    ColumnProfile,
    IssueStatus,
    RunPhase,
    SourceColumn,
    SourceFile,
    SourceRow,
)
from schemabridge.graph.builder import compile_graph
from schemabridge.graph.checkpointer import build_checkpointer
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.profile import profile_columns
from schemabridge.server.mongo import close_client

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"
FILES = ("employees-legacy.csv", "employees-hr-export.csv")


def initial_state(run_id: str) -> dict[str, Any]:
    files: list[SourceFile] = []
    columns: list[SourceColumn] = []
    rows: list[SourceRow] = []
    profiles: list[ColumnProfile] = []
    for index, name in enumerate(FILES):
        parsed = parse_csv(f"f{index}", name, (SAMPLES / name).read_text(encoding="utf-8"))
        if not parsed.ok:
            raise SystemExit(f"fixture {name} failed to parse: {parsed.error}")
        files.append(parsed.file)
        columns.extend(parsed.file.columns)
        rows.extend(parsed.rows)
        profiles.extend(profile_columns(parsed.file, parsed.rows))

    return {
        "run_id": run_id,
        "owner_session_id": "smoke",
        "files": tuple(files),
        "columns": tuple(columns),
        "rows": tuple(rows),
        "profiles": tuple(profiles),
        "mappings": (),
        "events": (),
        "records": (),
        "issues": (),
        "deliveries": (),
        "resolutions": {},
        "model_requests": 0,
        "phase": RunPhase.INGESTED,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("start", "resume", "cleanup"), required=True)
    parser.add_argument("--thread", default="smoke-resume")
    args = parser.parse_args()

    checkpointer = build_checkpointer()
    graph = compile_graph(checkpointer)
    config: Any = {"configurable": {"thread_id": args.thread}}

    if args.phase == "start":
        start: Any = initial_state(args.thread)
        result = graph.invoke(start, config)
        interrupts = result.get("__interrupt__", ())
        print(f"thread            : {args.thread}")
        print(f"automatic mappings: {sum(1 for m in result['mappings'] if m.target)}")
        print(f"paused            : {bool(interrupts)}")
        if interrupts:
            payload = interrupts[0].value
            print(f"awaiting decisions: {payload['count']}")
            for issue in payload["issues"]:
                print(f"  - [{issue['type']}] {issue['reason'][:88]}")
        print("\nNow run the same command with --phase resume, in a fresh process.")

    elif args.phase == "resume":
        # Nothing from the first process is in memory here. If this works, the
        # state genuinely came back from MongoDB.
        snapshot = graph.get_state(config)
        if not snapshot.next:
            print("FAIL  no paused run found for that thread id")
            sys.exit(1)

        print(f"recovered from database : yes (paused at {snapshot.next})")
        print(f"mappings already applied: {len(snapshot.values.get('mappings', ()))}")
        print(f"events already recorded : {len(snapshot.values.get('events', ()))}")

        pending = snapshot.tasks[0].interrupts if snapshot.tasks else ()
        decisions: dict[str, Any] = {}
        for pending_interrupt in pending:
            for issue in pending_interrupt.value["issues"]:
                options = issue["options"]
                decisions[issue["id"]] = (
                    {"action": "correct", "option_id": options[0]["id"]}
                    if options
                    else {"action": "exclude", "note": "Excluded during smoke test."}
                )

        print(f"resolving               : {len(decisions)} issue(s)")
        resumed = graph.invoke(Command(resume=decisions), config)

        resolved = [i for i in resumed["issues"] if i.status is IssueStatus.RESOLVED]
        print(f"resolved                : {len(resolved)}")
        print(f"records                 : {len(resumed['records'])}")
        print(f"final phase             : {resumed['phase']}")
        print("\nPASS  a run paused in one process was completed by another.")

    else:
        settings_db = build_checkpointer()
        del settings_db
        client = None
        try:
            from schemabridge.server.config import get_settings
            from schemabridge.server.mongo import get_client

            client = get_client()
            client.drop_database(f"{get_settings().mongodb_db}_checkpoints")
            print("dropped the checkpoint database")
        finally:
            if client is not None:
                close_client()
        return

    close_client()


if __name__ == "__main__":
    main()
