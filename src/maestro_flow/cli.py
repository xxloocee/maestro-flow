from __future__ import annotations

import json
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from maestro_flow.ci_ops import (
    build_pr_comment,
    evaluate_run,
    load_policy_report,
    load_reviewer_output,
    load_run_state,
    post_or_update_pr_comment,
    resolve_run_dir,
    write_pr_comment_file,
)
from maestro_flow.config import load_config
from maestro_flow.git_ops import create_pr, finalize_commit, write_pr_body
from maestro_flow.integrations import INTEGRATION_TARGETS, init_spec_file, install_integration
from maestro_flow.orchestrator import DevFlowOrchestrator
from maestro_flow.providers import supported_providers
from maestro_flow.sync_back_ops import (
    apply_sync_decisions,
    build_sync_decision_template,
    load_sync_decisions,
    save_sync_decisions,
    write_manual_sync_report,
)

app = typer.Typer(help="Maestro multi-agent delivery workflow")
spec_app = typer.Typer(help="Spec-oriented workflow commands")
ci_app = typer.Typer(help="CI and PR gate commands")
sync_back_app = typer.Typer(help="Sync-back conflict resolution commands")
app.add_typer(spec_app, name="spec")
app.add_typer(ci_app, name="ci")
app.add_typer(sync_back_app, name="sync-back")
console = Console()


def _repo_root() -> Path:
    root = Path.cwd()
    load_dotenv(root / ".env")
    return root


def _run_with_requirement(
    *,
    requirement: str,
    config_path: str,
    model: str,
    mock: bool,
    skip_gates: bool,
    skip_rollback: bool,
    execution_loop: bool,
    execution_isolated: bool,
    execution_sync_back: bool,
) -> None:
    repo_root = _repo_root()
    cfg = load_config(repo_root / config_path)
    if execution_loop:
        cfg.workflow.execution_enabled = True
    if execution_isolated:
        cfg.workflow.execution_enabled = True
        cfg.workflow.execution_workspace_mode = "copy"
    if execution_sync_back:
        cfg.workflow.execution_enabled = True
        cfg.workflow.execution_workspace_mode = "copy"
        cfg.workflow.sync_back_on_success = True
    selected_model = model or cfg.default_model

    orch = DevFlowOrchestrator(
        repo_root=repo_root,
        config=cfg,
        model=selected_model,
        mock=mock,
    )

    result = orch.run(
        requirement=requirement,
        execute_quality_gates=not skip_gates,
        execute_rollback=not skip_rollback,
    )

    console.print(f"run_id: [bold]{result.run_id}[/bold]")
    console.print(f"run_dir: {result.run_dir}")
    console.print(f"verdict: {result.verdict}")
    console.print(f"summary: {result.summary_file}")


def _resolve_output_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return repo_root / path


def _record_manual_sync_result(*, run_dir: Path, report: dict) -> None:
    state = load_run_state(run_dir)
    execution = state.setdefault("execution", {})
    execution["sync_back_manual"] = {
        "status": report.get("status", "unknown"),
        "report_file": str(run_dir / "sync_back_manual_report.json"),
        "dry_run": bool(report.get("dry_run", False)),
        "applied_count": len(report.get("applied", [])),
        "failed_count": len(report.get("failed", [])),
        "skipped_count": len(report.get("skipped", [])),
    }
    (run_dir / "run_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@app.command()
def run(
    requirement: str = typer.Option(..., "--requirement", "-r", help="Product requirement text"),
    config: str = typer.Option("agents/agents.yaml", help="Config file path"),
    model: str = typer.Option("", help="Override model name"),
    mock: bool = typer.Option(False, help="Run without LLM calls"),
    skip_gates: bool = typer.Option(False, help="Skip quality gates"),
    skip_rollback: bool = typer.Option(False, help="Skip rollback on failure"),
    execution_loop: bool = typer.Option(False, "--execution-loop", help="Enable P6 execution loop for this run"),
    execution_isolated: bool = typer.Option(False, "--execution-isolated", help="Run execution loop in isolated copy workspace"),
    execution_sync_back: bool = typer.Option(False, "--execution-sync-back", help="Sync isolated execution changes back to repo on success"),
):
    _run_with_requirement(
        requirement=requirement,
        config_path=config,
        model=model,
        mock=mock,
        skip_gates=skip_gates,
        skip_rollback=skip_rollback,
        execution_loop=execution_loop,
        execution_isolated=execution_isolated,
        execution_sync_back=execution_sync_back,
    )


@app.command()
def report(
    run_id: str = typer.Option(..., help="Run id under .maestro/runs"),
):
    run_dir = _repo_root() / ".maestro" / "runs" / run_id
    summary = run_dir / "summary.md"
    if not summary.exists():
        raise typer.BadParameter(f"summary not found: {summary}")
    console.print(summary.read_text(encoding="utf-8"))


@app.command()
def finalize(
    run_id: str = typer.Option(..., help="Run id under .maestro/runs"),
    branch: str = typer.Option(..., help="Target branch name"),
    commit_message: str = typer.Option(..., "--commit-message", "-m"),
    create_pull_request: bool = typer.Option(False, "--pr", help="Create GitHub PR via gh CLI"),
    pr_title: str = typer.Option("chore: apply maestro run output"),
    pr_base: str = typer.Option("main"),
):
    repo_root = _repo_root()
    run_dir = repo_root / ".maestro" / "runs" / run_id
    if not run_dir.exists():
        raise typer.BadParameter(f"run directory not found: {run_dir}")

    sha = finalize_commit(
        repo_root=repo_root,
        branch=branch,
        commit_message=commit_message,
    )
    console.print(f"commit: [bold]{sha}[/bold]")

    body_file = run_dir / "pr_body.md"
    write_pr_body(run_dir=run_dir, output_file=body_file)
    console.print(f"pr body: {body_file}")

    if create_pull_request:
        url = create_pr(
            repo_root=repo_root,
            title=pr_title,
            body_file=body_file,
            base=pr_base,
        )
        console.print(f"pr: [bold]{url}[/bold]")


@app.command("providers")
def providers_cmd():
    table = Table(title="Supported Providers (OpenAI-Compatible)")
    table.add_column("Provider")
    table.add_column("API Key Env")
    table.add_column("Default Base URL")
    table.add_column("Model Hint")

    for p in supported_providers():
        table.add_row(
            p.name,
            p.key_env,
            p.default_base_url or "(official default)",
            p.model_hint,
        )

    console.print(table)
    console.print("Priority: MAESTRO_API_KEY > provider specific key env")
    console.print("Override provider with env: MAESTRO_PROVIDER")
    console.print("Override endpoint with env: MAESTRO_BASE_URL")


@app.command("install")
def install_cmd(
    target: str = typer.Option(..., help=f"Integration target: {', '.join(sorted(INTEGRATION_TARGETS.keys()))}"),
    scope: str = typer.Option("project", help="Install scope: project or user"),
    dest: str = typer.Option("", help="Optional custom destination path"),
    dry_run: bool = typer.Option(False, help="Only print install plan"),
):
    repo_root = _repo_root()
    dst, files = install_integration(
        repo_root=repo_root,
        target=target.strip().lower(),
        scope=scope.strip().lower(),
        destination_override=dest.strip() or None,
        dry_run=dry_run,
    )
    action = "plan" if dry_run else "installed"
    console.print(f"{action} target: {target} ({scope})")
    console.print(f"destination: {dst}")
    for f in files:
        console.print(f"- {f}")


@ci_app.command("evaluate")
def ci_evaluate(
    run_id: str = typer.Option("", help="Run id. If empty, use latest run."),
    fail_on_conditions: bool = typer.Option(False, help="Fail gate when merge conditions exist."),
):
    repo_root = _repo_root()
    run_dir = resolve_run_dir(repo_root=repo_root, run_id=run_id)
    state = load_run_state(run_dir)
    reviewer = load_reviewer_output(run_dir)
    policy_results = load_policy_report(run_dir)
    evaluation = evaluate_run(
        state=state,
        reviewer=reviewer,
        policy_results=policy_results,
        fail_on_conditions=fail_on_conditions,
    )

    console.print(f"run_dir: {run_dir}")
    console.print(f"run_status: {evaluation.run_status}")
    console.print(f"reviewer_verdict: {evaluation.reviewer_verdict}")
    console.print(f"gate: {'PASS' if evaluation.passed else 'FAIL'}")
    if evaluation.reasons:
        for reason in evaluation.reasons:
            console.print(f"- {reason}")
    if evaluation.reason_codes:
        console.print("reason_codes:")
        for code in evaluation.reason_codes:
            console.print(f"- {code}")

    if not evaluation.passed:
        raise typer.Exit(code=1)


@ci_app.command("comment")
def ci_comment(
    pr_number: int = typer.Option(..., help="Pull request number"),
    run_id: str = typer.Option("", help="Run id. If empty, use latest run."),
    fail_on_conditions: bool = typer.Option(False, help="Fail gate when merge conditions exist."),
    output_file: str = typer.Option("", help="Optional comment file path"),
):
    repo_root = _repo_root()
    run_dir = resolve_run_dir(repo_root=repo_root, run_id=run_id)
    state = load_run_state(run_dir)
    reviewer = load_reviewer_output(run_dir)
    policy_results = load_policy_report(run_dir)
    evaluation = evaluate_run(
        state=state,
        reviewer=reviewer,
        policy_results=policy_results,
        fail_on_conditions=fail_on_conditions,
    )

    resolved_run_id = run_dir.name
    body = build_pr_comment(
        run_id=resolved_run_id,
        run_dir=run_dir,
        state=state,
        reviewer=reviewer,
        evaluation=evaluation,
        policy_results=policy_results,
    )
    comment_file = Path(output_file) if output_file else run_dir / "pr_comment.md"
    write_pr_comment_file(output_file=comment_file, body=body)

    url = post_or_update_pr_comment(
        repo_root=repo_root,
        pr_number=pr_number,
        body_file=comment_file,
    )
    console.print(f"comment: {url}")


@spec_app.command("init")
def spec_init(
    name: str = typer.Option(..., "--name", "-n", help="Spec name"),
):
    path = init_spec_file(_repo_root(), name)
    console.print(f"spec: [bold]{path}[/bold]")


@spec_app.command("run")
def spec_run(
    file: str = typer.Option(..., "--file", "-f", help="Spec markdown file path"),
    config: str = typer.Option("agents/agents.yaml", help="Config file path"),
    model: str = typer.Option("", help="Override model name"),
    mock: bool = typer.Option(False, help="Run without LLM calls"),
    skip_gates: bool = typer.Option(False, help="Skip quality gates"),
    skip_rollback: bool = typer.Option(False, help="Skip rollback on failure"),
    execution_loop: bool = typer.Option(False, "--execution-loop", help="Enable P6 execution loop for this run"),
    execution_isolated: bool = typer.Option(False, "--execution-isolated", help="Run execution loop in isolated copy workspace"),
    execution_sync_back: bool = typer.Option(False, "--execution-sync-back", help="Sync isolated execution changes back to repo on success"),
):
    spec_path = Path(file)
    if not spec_path.is_absolute():
        spec_path = _repo_root() / spec_path
    if not spec_path.exists():
        raise typer.BadParameter(f"Spec file not found: {spec_path}")

    content = spec_path.read_text(encoding="utf-8").strip()
    requirement = (
        "Implement and deliver the following software spec.\n\n"
        f"Spec file: {spec_path}\n\n"
        f"{content}"
    )

    _run_with_requirement(
        requirement=requirement,
        config_path=config,
        model=model,
        mock=mock,
        skip_gates=skip_gates,
        skip_rollback=skip_rollback,
        execution_loop=execution_loop,
        execution_isolated=execution_isolated,
        execution_sync_back=execution_sync_back,
    )


@sync_back_app.command("plan")
def sync_back_plan(
    run_id: str = typer.Option("", help="Run id. If empty, use latest run."),
    output_file: str = typer.Option("", help="Decision file path, default is run_dir/sync_back_decisions.json"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing decision file"),
):
    repo_root = _repo_root()
    run_dir = resolve_run_dir(repo_root=repo_root, run_id=run_id)
    payload = build_sync_decision_template(repo_root=repo_root, run_dir=run_dir)
    decision_file = _resolve_output_path(repo_root, output_file) if output_file else run_dir / "sync_back_decisions.json"
    if decision_file.exists() and not force:
        raise typer.BadParameter(f"决策文件已存在: {decision_file}，如需覆盖请加 --force")
    save_sync_decisions(output_file=decision_file, payload=payload)

    items = payload.get("items", [])
    conflict_count = sum(1 for item in items if bool(item.get("conflict", False)))
    console.print(f"run_dir: {run_dir}")
    console.print(f"decision_file: {decision_file}")
    console.print(f"items: {len(items)}")
    console.print(f"conflicts: {conflict_count}")


@sync_back_app.command("apply")
def sync_back_apply(
    run_id: str = typer.Option("", help="Run id. If empty, use latest run."),
    decision_file: str = typer.Option("", help="Decision file path, default is run_dir/sync_back_decisions.json"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only evaluate decisions without writing files"),
):
    repo_root = _repo_root()
    run_dir = resolve_run_dir(repo_root=repo_root, run_id=run_id)
    resolved_decision_file = _resolve_output_path(repo_root, decision_file) if decision_file else run_dir / "sync_back_decisions.json"
    payload = load_sync_decisions(resolved_decision_file)
    report = apply_sync_decisions(
        repo_root=repo_root,
        run_dir=run_dir,
        decision_payload=payload,
        dry_run=dry_run,
    )

    report_file = write_manual_sync_report(run_dir=run_dir, report=report)
    if not dry_run:
        _record_manual_sync_result(run_dir=run_dir, report=report)

    console.print(f"run_dir: {run_dir}")
    console.print(f"decision_file: {resolved_decision_file}")
    console.print(f"report_file: {report_file}")
    console.print(f"status: {report.get('status')}")
    console.print(f"applied: {len(report.get('applied', []))}")
    console.print(f"skipped: {len(report.get('skipped', []))}")
    console.print(f"failed: {len(report.get('failed', []))}")

    if report.get("status") != "succeeded":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
