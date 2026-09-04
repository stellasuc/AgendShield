"""Policy inspection, LangGraph demos, execution, and audit timelines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from agentshield.regulations.loader import RegulationLoader
from agentshield.shield import default_package_root


PACKAGE_ROOT = default_package_root()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentshield")
    subcommands = parser.add_subparsers(dest="command", required=True)
    policy = subcommands.add_parser("policy", help="Inspect curated regulation packages")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_commands.add_parser("list", help="List supported regulation packages")
    show = policy_commands.add_parser("show", help="Show selected technical controls")
    show.add_argument("regulation")
    autopolicy = subcommands.add_parser(
        "autopolicy", help="Run or inspect the pinned AutoPolicy extraction pipeline"
    )
    autopolicy_commands = autopolicy.add_subparsers(
        dest="autopolicy_command", required=True
    )
    autopolicy_inspect = autopolicy_commands.add_parser(
        "inspect", help="Validate an AutoPolicy extraction directory"
    )
    autopolicy_inspect.add_argument("extraction_directory")
    autopolicy_review = autopolicy_commands.add_parser(
        "review-template", help="Export a non-executable human review template"
    )
    autopolicy_review.add_argument("extraction_directory")
    autopolicy_review.add_argument("--output", required=True)
    autopolicy_extract = autopolicy_commands.add_parser(
        "extract", help="Extract policy candidates with the pinned upstream"
    )
    autopolicy_extract.add_argument("document")
    autopolicy_extract.add_argument("--organization", required=True)
    autopolicy_extract.add_argument("--input-type", choices=("pdf", "html", "txt"), required=True)
    autopolicy_extract.add_argument("--output-dir", default=".agentshield/autopolicy")
    autopolicy_extract.add_argument("--organization-description", default="")
    autopolicy_extract.add_argument("--target-subject", default="Web task agent")
    autopolicy_extract.add_argument("--user-request", default="提取约束 Web Agent 行为的明确政策")
    autopolicy_extract.add_argument("--page-range", default="1-10000")
    autopolicy_extract.add_argument("--deep-policy", action="store_true")
    autopolicy_extract.add_argument(
        "--extract-ltl",
        action="store_true",
        help="Also run the upstream GPT-4o LTLRuleExtractor",
    )
    autopolicy_extract.add_argument("--exploration-budget", type=int, default=20)
    upstream = subcommands.add_parser(
        "upstream", help="Inspect pinned AutoPolicy, AWM, and WebArena checkouts"
    )
    upstream.add_subparsers(dest="upstream_command", required=True).add_parser("status")
    webarena = subcommands.add_parser(
        "webarena", help="Run the pinned AWM task agent behind ShieldAgent"
    )
    webarena_commands = webarena.add_subparsers(dest="webarena_command", required=True)
    webarena_commands.add_parser("status")
    webarena_run = webarena_commands.add_parser("run")
    webarena_run.add_argument("task_name", help="BrowserGym task, for example webarena.0")
    webarena_run.add_argument("--model", default="openai/gpt-4o")
    webarena_run.add_argument("--workflow", default="shopping")
    webarena_run.add_argument("--regulations", nargs="+", default=["GDPR"])
    webarena_run.add_argument("--max-steps", type=int, default=10)
    webarena_run.add_argument("--max-replans", type=int, default=2)
    webarena_run.add_argument("--output-dir", default=".agentshield/webarena")
    webarena_run.add_argument("--headed", action="store_true")
    webarena_run.add_argument("--prompt", default="")
    webarena_run.add_argument("--start-url", default="")
    webarena_run.add_argument(
        "--python-executable",
        default=None,
        help="Python from the isolated AWM environment (defaults to .venv-awm when present)",
    )
    demo = subcommands.add_parser("demo", help="Run a local LangGraph runtime demo")
    demo.add_argument(
        "name",
        choices=(
            "langgraph-unprotected",
            "langgraph-gdpr",
            "langgraph-memory",
            "langgraph-response",
            "gdpr",
            "pipl",
            "gdpr-broker",
            "pipl-approval",
            "idempotency",
        ),
    )
    demo.add_argument("--audit-dir", default=".agentshield/audit")
    demo.add_argument("--db")
    demo.add_argument("--pause-only", action="store_true")
    run = subcommands.add_parser("run", help="Run the deterministic customer-service agent")
    run.add_argument("--regulations", nargs="+", default=["GDPR"])
    run.add_argument("--adapter", choices=("langgraph",), default="langgraph")
    run.add_argument("--audit-dir", default=".agentshield/audit")
    audit = subcommands.add_parser("audit", help="Render a payload-free runtime timeline")
    audit.add_argument("run_id")
    audit.add_argument("--audit-dir", default=".agentshield/audit")
    audit.add_argument("--db", default=".agentshield/runtime.db")
    transactions = subcommands.add_parser("transactions", help="Inspect durable effect transactions")
    transaction_commands = transactions.add_subparsers(dest="transaction_command", required=True)
    transaction_list = transaction_commands.add_parser("list")
    transaction_list.add_argument("--db", default=".agentshield/runtime.db")
    transaction_show = transaction_commands.add_parser("show")
    transaction_show.add_argument("transaction_id")
    transaction_show.add_argument("--db", default=".agentshield/runtime.db")
    approvals = subcommands.add_parser("approvals", help="List durable approvals")
    approval_commands = approvals.add_subparsers(dest="approval_command", required=True)
    approval_list = approval_commands.add_parser("list")
    approval_list.add_argument("--db", default=".agentshield/runtime.db")
    approve = subcommands.add_parser("approve", help="Approve and reverify a paused effect")
    approve.add_argument("transaction_id")
    approve.add_argument("--db", default=".agentshield/runtime.db")
    deny = subcommands.add_parser("deny", help="Deny a paused effect")
    deny.add_argument("transaction_id")
    deny.add_argument("--db", default=".agentshield/runtime.db")
    timeline = subcommands.add_parser(
        "timeline", help="Export a payload-safe structured security timeline"
    )
    timeline.add_argument("run_id")
    timeline.add_argument("--db", default=".agentshield/runtime.db")
    subcommands.add_parser("dashboard", help="Launch the local security visualizer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    loader = RegulationLoader(PACKAGE_ROOT)
    if args.command == "policy" and args.policy_command == "list":
        for regulation_id in ("GDPR", "PIPL"):
            package = loader.load(regulation_id)
            print(f"{package.metadata.regulation_id:<8} supported")
        return 0
    if args.command == "policy" and args.policy_command == "show":
        package = loader.load(args.regulation.upper())
        print(f"{package.metadata.regulation_id}: {package.metadata.official_name}")
        print("Selected runtime-assistive technical controls:")
        for requirement in package.requirements:
            print(
                f"- {requirement.requirement_id} | {requirement.source.article} | "
                f"{requirement.normalized_concept}"
            )
            print(f"  Source: {requirement.source.official_url}")
        print("Technical compliance assistance only; not legal advice or complete coverage.")
        return 0
    if args.command == "upstream" and args.upstream_command == "status":
        from agentshield.integrations.upstreams import inspect_upstreams

        for status in inspect_upstreams():
            label = "READY" if status.ready else "NOT_READY"
            print(
                f"{status.project.display_name:<30} {label:<10} "
                f"{status.detail} [{status.project.license}]"
            )
        return 0
    if args.command == "autopolicy":
        from agentshield.integrations.autopolicy import (
            AutoPolicyExtractionRequest,
            AutoPolicyRunner,
            load_autopolicy_bundle,
        )

        if args.autopolicy_command == "inspect":
            bundle = load_autopolicy_bundle(args.extraction_directory)
        elif args.autopolicy_command == "review-template":
            from agentshield.integrations.autopolicy import render_review_template

            bundle = load_autopolicy_bundle(args.extraction_directory)
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(render_review_template(bundle), encoding="utf-8")
            print(f"审核模板已写入 {output_path}")
            print("该模板不可执行；完成审核后仍需转换为受信任的法规规则包。")
            return 0
        else:
            request = AutoPolicyExtractionRequest(
                document=args.document,
                organization=args.organization,
                input_type=args.input_type,
                organization_description=args.organization_description,
                target_subject=args.target_subject,
                user_request=args.user_request,
                initial_page_range=args.page_range,
                deep_policy=args.deep_policy,
                exploration_budget=args.exploration_budget,
            )
            bundle = AutoPolicyRunner().run(
                request,
                args.output_dir,
                extract_ltl=args.extract_ltl,
            )
        print(json.dumps(bundle.audit_view(), ensure_ascii=False, indent=2))
        print("候选规则尚不可执行；必须完成来源、语义和运行时谓词的人工审核。")
        return 0
    if args.command == "webarena":
        from agentshield.integrations.awm_webarena import (
            AWMWebArenaConfig,
            AWMWebArenaRunner,
            inspect_awm_webarena,
        )

        if args.webarena_command == "status":
            print(json.dumps(inspect_awm_webarena().audit_view(), ensure_ascii=False, indent=2))
            return 0
        config = AWMWebArenaConfig(
            task_name=args.task_name,
            model_name=args.model,
            regulations=tuple(args.regulations),
            workflow=args.workflow,
            max_steps=args.max_steps,
            headless=not args.headed,
            max_replans=args.max_replans,
            task_prompt=args.prompt,
            start_url=args.start_url,
        )
        result = AWMWebArenaRunner(python_executable=args.python_executable).run(
            config, args.output_dir
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "demo":
        if args.name.startswith("langgraph-"):
            from examples.langgraph_customer_service.demo import render_demo

            print(render_demo(args.name, audit_directory=args.audit_dir))
            return 0
        from tempfile import TemporaryDirectory
        from examples.portfolio.demo import render_demo as render_portfolio_demo

        portfolio_name = {
            "gdpr": "gdpr-broker",
            "pipl": "pipl-approval",
        }.get(args.name, args.name)
        if args.pause_only and portfolio_name != "pipl-approval":
            raise SystemExit("--pause-only is supported only by pipl")
        if args.db:
            print(
                render_portfolio_demo(
                    portfolio_name,
                    args.db,
                    pause_only=args.pause_only,
                )
            )
        elif args.pause_only:
            print(
                render_portfolio_demo(
                    portfolio_name,
                    ".agentshield/runtime.db",
                    pause_only=True,
                )
            )
        else:
            with TemporaryDirectory(prefix="agentshield-demo-") as directory:
                print(
                    render_portfolio_demo(
                        portfolio_name,
                        Path(directory) / "runtime.db",
                    )
                )
        return 0
    if args.command == "run":
        from agentshield.shield import AgentShield
        from examples.langgraph_customer_service.agent import build_customer_service_agent
        from examples.langgraph_customer_service.demo import REQUEST_EMAIL

        agent = build_customer_service_agent()
        secured = AgentShield(regulations=args.regulations).wrap(
            agent,
            adapter=args.adapter,
            audit_directory=args.audit_dir,
        )
        result = secured.invoke({"messages": [{"role": "user", "content": REQUEST_EMAIL}]})
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "audit":
        from agentshield.effects.store import SQLiteRuntimeStore

        database = Path(args.db)
        if database.is_file():
            records = SQLiteRuntimeStore(database).read_audit(args.run_id)
            if records:
                for index, record in enumerate(records, 1):
                    payload = record["payload"]
                    print(
                        f"[{index:02d}] {record['event_type']:<24} "
                        f"{payload.get('capability_id', ''):<18} "
                        f"{payload.get('status', '')} {payload.get('decision', '')}"
                    )
                return 0
        path = Path(args.audit_dir) / f"{args.run_id}.jsonl"
        if not path.is_file():
            raise SystemExit(f"No audit log for run {args.run_id!r} in {args.audit_dir}")
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for index, record in enumerate(records, 1):
            event = record["event"]
            tool = event.get("tool") or ""
            outcome = record.get("final_outcome", "")
            execution = record.get("execution_outcome", "")
            repair = record.get("repair") or {}
            suffix = f" repair={repair.get('strategy')}" if repair else ""
            print(
                f"[{index:02d}] {event['event_type']:<20} {tool:<22} "
                f"{outcome} [{execution}]{suffix}"
            )
        return 0
    if args.command == "transactions":
        from agentshield.effects.store import SQLiteRuntimeStore

        store = SQLiteRuntimeStore(args.db)
        if args.transaction_command == "list":
            for transaction in store.list_transactions():
                print(
                    f"{transaction.transaction_id} {transaction.status.value:<20} "
                    f"{transaction.capability_id:<18} {transaction.decision}"
                )
            return 0
        transaction = store.get_transaction(args.transaction_id)
        print(json.dumps(_transaction_view(transaction), indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "approvals" and args.approval_command == "list":
        from agentshield.effects.store import SQLiteRuntimeStore

        print(json.dumps(SQLiteRuntimeStore(args.db).list_approvals(), indent=2, default=str))
        return 0
    if args.command in {"approve", "deny"}:
        from agentshield.capabilities.broker import CapabilityBroker
        from agentshield.effects.store import SQLiteRuntimeStore

        store = SQLiteRuntimeStore(args.db)
        transaction = store.get_transaction(args.transaction_id)
        regulations = tuple(transaction.result_metadata.get("regulations") or ("GDPR",))
        broker = CapabilityBroker(args.db, regulations=regulations)
        result = (
            broker.approve(args.transaction_id)
            if args.command == "approve"
            else broker.deny(args.transaction_id)
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "timeline":
        from agentshield.observability import SecurityTimeline

        print(SecurityTimeline(args.db).to_json(args.run_id))
        return 0
    if args.command == "dashboard":
        from agentshield.dashboard_launcher import launch_dashboard

        return launch_dashboard()
    raise AssertionError("Unhandled command")


def _transaction_view(transaction) -> dict[str, object]:
    from agentshield.runtime.lifecycle import _fingerprint

    return {
        "transaction_id": transaction.transaction_id,
        "effect_id": transaction.effect_id,
        "request_id": transaction.request_id,
        "trajectory_id": transaction.trajectory_id,
        "capability_id": transaction.capability_id,
        "original_arguments": _fingerprint(transaction.original_arguments),
        "effective_arguments": _fingerprint(transaction.effective_arguments),
        "referenced_data_objects": list(transaction.referenced_data_objects),
        "decision": transaction.decision,
        "activated_rules": list(transaction.activated_rules),
        "status": transaction.status.value,
        "repair_parent": transaction.repair_parent,
        "approval_required": transaction.approval_required,
        "execution_attempts": transaction.execution_attempts,
        "result_metadata": _safe_cli_metadata(transaction.result_metadata),
        "error": transaction.error,
    }


def _safe_cli_metadata(value, *, field: str | None = None):
    """Keep operational metadata visible without printing payload-shaped values."""
    from collections.abc import Mapping
    from agentshield.runtime.lifecycle import _fingerprint

    payload_fields = {
        "arguments",
        "original_arguments",
        "effective_arguments",
        "value",
        "body",
        "data",
        "response",
    }
    if field in payload_fields:
        return _fingerprint(value)
    if isinstance(value, Mapping):
        return {
            str(key): _safe_cli_metadata(item, field=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_cli_metadata(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
