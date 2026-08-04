"""Command-line entrypoint."""

import argparse
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from resume_agent.backends import HeuristicBackend, LangChainBackend
from resume_agent.evidence import load_evidence, read_text_file
from resume_agent.output import write_artifacts
from resume_agent.workflow import build_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    tailor = subparsers.add_parser("tailor", help="Tailor a resume to a job description")
    tailor.add_argument("--jd", type=Path, required=True, help="Markdown or text job description")
    tailor.add_argument("--resume", type=Path, required=True, help="Master resume")
    tailor.add_argument("--evidence", type=Path, help="Directory containing Markdown/text evidence")
    tailor.add_argument("--output", type=Path, default=Path("output"), help="Output root")
    tailor.add_argument("--demo", action="store_true", help="Use deterministic offline backend")
    tailor.add_argument("--yes", action="store_true", help="Approve the verified draft automatically")
    tailor.add_argument("--model", default=os.getenv("RESUME_AGENT_MODEL", "gpt-5-mini"))
    return parser


def create_backend(args: argparse.Namespace):
    if args.demo:
        return HeuristicBackend()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required unless --demo is used")
    return LangChainBackend(
        model=args.model,
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
    )


def ask_for_review(interrupt_value: dict, auto_approve: bool) -> dict:
    resume_markdown = str(interrupt_value.get("resume_markdown", ""))
    if auto_approve:
        return {"approved": True, "resume_markdown": resume_markdown}
    print("\n--- Verified resume draft ---\n")
    print(resume_markdown)
    unsupported = interrupt_value.get("unsupported_claims", [])
    if unsupported:
        print(f"\nVerifier flagged {len(unsupported)} unsupported claim(s).")
    answer = input("\nApprove this draft? [y/N]: ").strip().lower()
    return {"approved": answer in {"y", "yes"}, "resume_markdown": resume_markdown}


def run_tailor(args: argparse.Namespace) -> Path:
    jd_text = read_text_file(args.jd)
    master_resume = read_text_file(args.resume)
    chunks = load_evidence(args.resume, args.evidence)
    backend = create_backend(args)
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir = args.output.expanduser().resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    connection = sqlite3.connect(run_dir / "checkpoints.sqlite", check_same_thread=False)
    try:
        graph = build_graph(backend, SqliteSaver(connection))
        config = {"configurable": {"thread_id": run_id}}
        state = graph.invoke(
            {
                "jd_text": jd_text,
                "master_resume": master_resume,
                "evidence_chunks": [chunk.model_dump() for chunk in chunks],
            },
            config=config,
        )
        interrupts = state.get("__interrupt__", [])
        if not interrupts:
            raise RuntimeError("Workflow finished without the required human review")
        decision = ask_for_review(interrupts[0].value, args.yes)
        final_state = graph.invoke(Command(resume=decision), config=config)
        write_artifacts(run_dir, final_state)
    finally:
        connection.close()
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "tailor":
            run_dir = run_tailor(args)
            print(f"Artifacts written to {run_dir}")
            return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
