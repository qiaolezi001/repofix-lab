"""Small reproducible CLI. Live inference always requires an explicit opt-in."""

import argparse
import json
from pathlib import Path

from repofix.config import DEMO_ISSUE, Settings, demo_source
from repofix.engine import Engine
from repofix.providers import LiveProvider
from repofix.reports import markdown, public_state
from repofix.sandbox import Sandbox


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="repofix")
    commands = cli.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the localhost UI/API (one process).")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    run = commands.add_parser("run")
    run.add_argument("source", type=Path)
    run.add_argument("--issue", required=True)
    run.add_argument("--mode", choices=["mock", "live"], default="mock")
    run.add_argument("--strategy", choices=["agent", "baseline"], default="agent")
    run.add_argument("--allow-paid", action="store_true")
    run.add_argument("--max-calls", type=int, default=16)
    run.add_argument("--timeout", type=int, default=180)
    run.add_argument("--output", type=Path)
    demo = commands.add_parser("demo", help="Run the dedicated scripted mock fixture.")
    demo.add_argument("--output", type=Path)
    commands.add_parser("doctor", help="Check local configuration without paid inference.")
    check = commands.add_parser("model-check", help="Explicit 2-call function protocol probe.")
    check.add_argument("--allow-paid", action="store_true")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--mode", choices=["mock", "live"], default="mock")
    evaluate.add_argument("--split", choices=["dev", "eval"], default="dev")
    evaluate.add_argument("--output", type=Path, default=Path("reports/evaluation"))
    evaluate.add_argument("--allow-paid", action="store_true")
    evaluate.add_argument("--max-calls", type=int, default=12)
    evaluate.add_argument(
        "--task-id",
        action="append",
        help="Select an explicit task in the split; repeat for a bounded pilot.",
    )
    resume = commands.add_parser("resume")
    resume.add_argument("task_id")
    show = commands.add_parser("show")
    show.add_argument("task_id")
    cancel = commands.add_parser("cancel")
    cancel.add_argument("task_id")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "serve":
            import uvicorn

            from repofix.api import create_app

            uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1)
            return 0
        if args.command == "doctor":
            result = {
                "api_key_configured": bool(settings.api_key),
                "model": settings.model or None,
                "data_dir": str(settings.data_dir),
                "demo_available": demo_source().is_dir(),
                "docker": Sandbox(image=settings.sandbox_image).available(),
                "live_benchmark": "not measured",
            }
        elif args.command == "model-check":
            if not args.allow_paid:
                raise ValueError(
                    "Probe uses 2 calls (up to 128 output tokens each); pass --allow-paid after reviewing provider prices."
                )
            result = LiveProvider(settings).check()
        elif args.command == "evaluate":
            from repofix.evaluation import evaluate

            result = evaluate(
                settings,
                split=args.split,
                mode=args.mode,
                output=args.output,
                allow_paid=args.allow_paid,
                max_calls=args.max_calls,
                task_ids=args.task_id,
            )
        else:
            engine = Engine(settings)
            if args.command == "show":
                result = public_state(engine.get(args.task_id))
            elif args.command == "cancel":
                result = public_state(engine.cancel(args.task_id))
            elif args.command == "resume":
                result = public_state(engine.run(args.task_id))
            else:
                source = demo_source() if args.command == "demo" else args.source
                issue = DEMO_ISSUE if args.command == "demo" else args.issue
                state = engine.create(
                    source,
                    issue,
                    mode="mock" if args.command == "demo" else args.mode,
                    strategy="agent" if args.command == "demo" else args.strategy,
                    limits={}
                    if args.command == "demo"
                    else {"max_model_calls": args.max_calls, "timeout_seconds": args.timeout},
                    allow_paid=False if args.command == "demo" else args.allow_paid,
                )
                state = engine.run(state["id"])
                result = public_state(state)
                if args.output:
                    args.output.mkdir(parents=True, exist_ok=True)
                    (args.output / "report.md").write_text(markdown(state), encoding="utf-8")
                    (args.output / "report.json").write_text(
                        json.dumps(result, indent=2), encoding="utf-8"
                    )
                    (args.output / "candidate.patch").write_text(
                        state["candidate_patch"], encoding="utf-8"
                    )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
