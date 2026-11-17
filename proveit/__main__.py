"""CLI: python -m proveit <command>

run <brief.md> [--mode live|full] [--label weak|strong]   start a run and advance it
continue <run_id>                                          advance a run after a founder step
status <run_id>                                            stage, gates and pending approvals
runs                                                       list runs
approvals list [--run ID] | approve <id> | reject <id>     founder approvals (hash-bound)
decide <run_id> <accept|stop|override|pivot|repeat|clarify_ok|gate4_approve|gate4_reject> [--reason TEXT]
ask "<text>" [--run ID]                                    Ask the assistant (guard first)
promote --weak <id> --strong <id> [--root]                 the only writer of outputs/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import approval, decisions, orchestrator, startup


def _status(run_id: str) -> dict:
    run = orchestrator.load(run_id)
    pend = [a.model_dump(mode="json") for a in approval.list_approvals(run_id, "pending")]
    return {
        "run_id": run.id,
        "label": run.label,
        "mode": run.mode,
        "stage": run.stage,
        "gate1": (run.state.get("gate1") or {}).get("outcome"),
        "gate2": (run.state.get("gate2") or {}).get("outcome"),
        "pending_approvals": pend,
        "usage": run.state.get("usage"),
        "error": run.state.get("error"),
    }


def main(argv: list[str] | None = None) -> int:
    for p in startup.check_writable():
        print("[startup] " + p, file=sys.stderr)
    ap = argparse.ArgumentParser(prog="python -m proveit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("brief")
    r.add_argument("--mode", default="live", choices=["live", "full"])
    r.add_argument("--label")
    c = sub.add_parser("continue")
    c.add_argument("run_id")
    s = sub.add_parser("status")
    s.add_argument("run_id")
    sub.add_parser("runs")
    a = sub.add_parser("approvals")
    a.add_argument("action", choices=["list", "approve", "reject"])
    a.add_argument("id", nargs="?")
    a.add_argument("--run")
    d = sub.add_parser("decide")
    d.add_argument("run_id")
    d.add_argument("decision")
    d.add_argument("--reason", default="")
    k = sub.add_parser("ask")
    k.add_argument("text")
    k.add_argument("--run")
    pr = sub.add_parser("promote")
    pr.add_argument("--weak", required=True)
    pr.add_argument("--strong", required=True)
    pr.add_argument("--root", action="store_true", help="also copy decision_log.json to the repo root")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        text = Path(args.brief).read_text(encoding="utf-8")
        run_id = orchestrator.start(text, mode=args.mode, label=args.label)
        print(f"run_id={run_id}")
        orchestrator.advance(run_id)
        print(json.dumps(_status(run_id), indent=2))
    elif args.cmd == "continue":
        orchestrator.advance(args.run_id)
        print(json.dumps(_status(args.run_id), indent=2))
    elif args.cmd == "status":
        print(json.dumps(_status(args.run_id), indent=2))
    elif args.cmd == "runs":
        for row in orchestrator.list_runs():
            print(row)
    elif args.cmd == "approvals":
        if args.action == "list":
            for x in approval.list_approvals(args.run):
                print(f"{x.id} {x.status:9} {x.action:22} sha256={x.payload_sha256} run={x.run_id} {x.note}")
        else:
            if not args.id:
                ap.error("approval id required")
            res = approval.decide(args.id, args.action == "approve", via="cli")
            print(f"{res.id} -> {res.status} (decided_by={res.decided_by})")
            stage = decisions.on_approval_decided(res.id)
            print(f"run stage: {stage}")
    elif args.cmd == "decide":
        print(json.dumps(decisions.founder_decide(args.run_id, args.decision, args.reason), indent=2))
    elif args.cmd == "ask":
        from . import ask

        print(json.dumps(ask.handle(args.text, args.run), indent=2, ensure_ascii=False))
    elif args.cmd == "promote":
        from .promote import promote

        print(json.dumps(promote(args.weak, args.strong, to_root=args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
