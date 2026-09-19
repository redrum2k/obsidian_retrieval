import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .approval import export_request
from .common import VaultError, canonical
from .config import Config
from .coordinator import Coordinator, next_trigger
from .output import measured, page
from .service import Service


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise VaultError("invalid_input", message + "; use vault --help or vault COMMAND --help.")


def parser():
    root = Parser(
        prog="vault",
        description="Local bounded retrieval and approved processing.",
        epilog="Examples: vault --config config.local.json search --query 'echelon form'",
    )
    root.add_argument("--config", default="config.local.json", help="Explicit JSON configuration")
    sub = root.add_subparsers(dest="command", required=True)
    help_text = {
        "validate": "Validate configuration without opening source contents or initializing an index",
        "extract": "Extract and index selected discovered documents; may run OCR/converters",
        "refresh": "Refresh incremental inventory; --full reconciles all hashes",
        "rebuild": "Rebuild search data, retaining pending work and approval history",
        "search": "Find ranked evidence sections",
        "read-sections": "Read selected revision-scoped sections",
        "changes": "Read eligible changes after a sequence checkpoint",
        "neighbors": "Find adjacent sections or provenance links",
        "processing-status": "Inspect relevant processing and grounding state",
        "health": "Inspect counts and freshness without source text",
        "pending": "List retained work for the existing agent planner",
        "notifications": "List undelivered proposals using stable delivery keys",
        "intake": "Refresh and expose pending work to the existing scheduler's agent",
        "propose": "Persist a concrete reviewable plan without vault writes",
        "acknowledge": "Confirm the existing host delivered a proposal notification",
        "approval-request": "Export an immutable request for the owner-facing macOS review app",
        "apply-hook": "Resume a batch authorized by a recorded conversation hook event",
        "apply": "Apply only a proposal with a trusted signed approval receipt",
        "schedule": "Show next external trigger time; does not install a scheduler",
        "visual": "Locate cached renders for current source evidence",
    }
    examples = {
        "extract": "--ids DOCUMENT_ID",
        "search": "--query 'echelon form'",
        "read-sections": "--ids SECTION_ID",
        "changes": "--since 0",
        "neighbors": "--id SECTION_ID --relation adjacent",
        "processing-status": "--ids DOCUMENT_ID",
        "propose": "--plan plan.json",
        "acknowledge": "--id PROPOSAL_ID",
        "approval-request": "--id PROPOSAL_ID",
        "apply-hook": "--id PROPOSAL_ID",
        "apply": "--id PROPOSAL_ID --receipt receipt.json",
        "visual": "--id DOCUMENT_ID",
    }
    for name, description in help_text.items():
        p = sub.add_parser(
            name,
            help=description,
            description=description,
            epilog=f"Examples: vault --config config.local.json {name} {examples.get(name, '')}",
        )
        p.add_argument("--budget", type=int, default=4000 if name == "read-sections" else 2000)
        p.add_argument("--limit", type=int, default=8)
        p.add_argument("--continuation")
        if name in {"search", "changes"}:
            p.add_argument("--project")
        if name == "search":
            p.add_argument("--query", required=True)
            p.add_argument("--source-role")
        if name in {"read-sections", "processing-status", "extract"}:
            p.add_argument("--ids", nargs="+", required=True)
        if name in {
            "neighbors",
            "acknowledge",
            "apply",
            "visual",
            "approval-request",
            "apply-hook",
        }:
            p.add_argument("--id", required=True)
        if name == "neighbors":
            p.add_argument(
                "--relation",
                choices=["adjacent", "links", "backlinks", "sources", "outputs"],
                required=True,
            )
        if name == "changes":
            p.add_argument("--since", default="0")
        if name == "refresh":
            p.add_argument("--full", action="store_true")
        if name in {"propose", "intake"}:
            p.add_argument(
                "--plan", required=name == "propose", help="JSON plan file, or - for stdin"
            )
        if name == "intake":
            p.add_argument(
                "--quiet",
                action="store_true",
                help="Emit nothing when no new host action is required",
            )
        if name == "acknowledge":
            p.add_argument(
                "--session-id", help="Conversation where the complete proposal was delivered"
            )
        if name == "apply":
            p.add_argument("--receipt", required=True)
    return root


def read_json(name):
    return json.load(sys.stdin) if name == "-" else json.loads(Path(name).read_text())


def run(args):
    if not 256 <= args.budget <= 8000 or not 1 <= args.limit <= 20:
        raise VaultError("invalid_input", "budget must be 256..8000 and limit 1..20.")
    if hasattr(args, "ids") and len(args.ids) > 20:
        raise VaultError("invalid_input", "At most 20 IDs per call.")
    if args.command == "schedule":
        return page(
            [
                {
                    "timezone": "America/New_York",
                    "weekdays": ["Monday", "Wednesday", "Friday", "Sunday"],
                    "time": "12:10",
                    "next": next_trigger(datetime.now().astimezone()),
                }
            ],
            {},
            {},
            args.budget,
            args.limit,
        )
    config = Config.load(args.config)
    if args.command == "validate":
        return page(
            [
                {
                    "valid": True,
                    "enabled": config.data.get("enabled", False),
                    "roots": config.roots,
                    "outputs": config.data["outputs"],
                    "config_revision": config.revision,
                }
            ],
            {},
            {},
            args.budget,
            args.limit,
        )
    service = Service(config)
    coordinator = Coordinator(service)
    scope = {
        k: v
        for k, v in vars(args).items()
        if k not in {"config", "budget", "limit", "continuation"} and v is not None
    }
    try:
        cmd = args.command
        if cmd in {"refresh", "rebuild"}:
            items = [service.refresh(full=getattr(args, "full", False), rebuild=cmd == "rebuild")]
        elif cmd == "extract":
            items = [service.extract_documents(args.ids)]
        elif cmd == "search":
            items = service.search(args.query, args.project, args.source_role)
        elif cmd == "read-sections":
            items = service.read_sections(args.ids)
        elif cmd == "changes":
            items = service.changes(args.since, args.project)
        elif cmd == "neighbors":
            items = service.neighbors(args.id, args.relation)
        elif cmd == "processing-status":
            items = service.processing_status(args.ids)
        elif cmd == "health":
            items = [service.health()]
        elif cmd == "intake":
            result = coordinator.run_intake(read_json(args.plan) if args.plan else None)
            if (
                args.quiet
                and result["quiet"]
                and not result["needs_planning"]
                and not result["refresh"]["failed"]
            ):
                return None
            items = [
                {
                    "kind": "run",
                    **{k: v for k, v in result.items() if k not in {"pending", "notifications"}},
                    "pending_count": len(result["pending"]),
                    "notification_count": len(result["notifications"]),
                    "next_operations": ["pending", "notifications"],
                }
            ]
        elif cmd == "pending":
            items = coordinator.pending()
        elif cmd == "notifications":
            items = [
                {
                    "proposal_id": r["id"],
                    "delivery_key": r["id"],
                    "review_file": str(config.state / "proposals" / (r["id"] + ".md")),
                }
                for r in service.db.execute(
                    "SELECT id FROM proposals WHERE state='pending' AND delivery<>'confirmed' ORDER BY created"
                )
            ]
        elif cmd == "propose":
            items = [coordinator.propose(read_json(args.plan))]
        elif cmd == "acknowledge":
            items = [coordinator.acknowledge(args.id, args.session_id)]
        elif cmd == "approval-request":
            items = [export_request(coordinator, args.id)]
        elif cmd == "apply-hook":
            from .hook_approval import recorded_receipt

            items = [coordinator.apply(args.id, recorded_receipt(service, args.id))]
        elif cmd == "apply":
            items = [coordinator.apply(args.id, read_json(args.receipt))]
        elif cmd == "visual":
            doc = service.db.execute("SELECT * FROM documents WHERE id=?", (args.id,)).fetchone()
            service.current(doc)
            folder = service.extractor.cache / doc["cache_key"]
            items = [
                {
                    "document_id": doc["id"],
                    "revision": doc["hash"],
                    "artifact": str(f),
                    "visual_review_required": True,
                }
                for f in sorted(folder.glob("page-*.png"))
            ]
            manifest = json.loads((folder / "result.json").read_text())
            items.extend(
                {
                    "document_id": doc["id"],
                    "revision": doc["hash"],
                    "artifact": str(folder / a["artifact"]),
                    "package_part": a["package_part"],
                    "visual_review_required": True,
                }
                for a in manifest.get("attachments", [])
            )
            if not items:
                raise VaultError(
                    "render_unavailable", "No cached render; check extractor dependencies."
                )
        else:
            raise VaultError("invalid_input", "Unknown command.")
        return page(
            items,
            service.snapshot(),
            scope,
            args.budget,
            args.limit,
            args.continuation,
            service.warnings,
        )
    finally:
        service.store.close()


def main():
    try:
        result = run(parser().parse_args())
        if result is not None:
            print(canonical(result))
        return 0
    except (VaultError, OSError, ValueError, KeyError, TypeError) as exc:
        error = {
            "error": getattr(exc, "code", "invalid_input"),
            "message": exc.message
            if isinstance(exc, VaultError)
            else "Invalid input or inaccessible local file; validate configuration and request schema.",
            "output_tokens": 0,
        }
        print(canonical(measured(error)))
        return 2


if __name__ == "__main__":
    sys.exit(main())
