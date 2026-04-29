import json
from pathlib import Path

from maestro_flow.ci_ops import (
    build_pr_comment,
    evaluate_run,
    load_policy_report,
    load_reviewer_output,
    load_run_state,
)


def test_evaluate_run_passes_on_succeeded_and_non_request_changes():
    state = {"status": "succeeded"}
    reviewer = {"verdict": "approve_with_conditions", "merge_conditions": ["run tests"]}
    ev = evaluate_run(state=state, reviewer=reviewer, policy_results=[], fail_on_conditions=False)
    assert ev.passed is True


def test_evaluate_run_fails_on_request_changes():
    state = {"status": "succeeded"}
    reviewer = {"verdict": "request_changes"}
    ev = evaluate_run(state=state, reviewer=reviewer, policy_results=[], fail_on_conditions=False)
    assert ev.passed is False
    assert "reviewer_verdict=request_changes" in ev.reasons
    assert "REVIEWER_REQUEST_CHANGES" in ev.reason_codes


def test_evaluate_run_fails_on_blocking_policy():
    state = {"status": "succeeded"}
    reviewer = {"verdict": "approve"}
    ev = evaluate_run(
        state=state,
        reviewer=reviewer,
        policy_results=[
            {"policy_id": "EXECUTION_COMMAND_ALLOWED", "status": "fail", "blocking": True, "message": "策略阻断"}
        ],
    )
    assert ev.passed is False
    assert "POLICY_BLOCKING_FAILURE" in ev.reason_codes


def test_loaders_and_comment_builder(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_state.json").write_text(
        json.dumps({"status": "succeeded", "stages": {"pm": {"status": "succeeded", "attempts": 1, "max_attempts": 2}}}),
        encoding="utf-8",
    )
    (run_dir / "stage_reviewer.json").write_text(
        json.dumps({"verdict": "approve", "findings": [], "merge_conditions": []}),
        encoding="utf-8",
    )
    (run_dir / "policy_report.json").write_text(
        json.dumps(
            [
                {
                    "policy_id": "DEV_VERIFY_COMMAND_REQUIRED",
                    "status": "fail",
                    "blocking": True,
                    "message": "开发阶段必须提供本地验证命令。",
                }
            ]
        ),
        encoding="utf-8",
    )

    state = load_run_state(run_dir)
    reviewer = load_reviewer_output(run_dir)
    policies = load_policy_report(run_dir)
    ev = evaluate_run(state=state, reviewer=reviewer, policy_results=policies)
    body = build_pr_comment(
        run_id="20260101-000000",
        run_dir=run_dir,
        state=state,
        reviewer=reviewer,
        evaluation=ev,
        policy_results=policies,
    )
    assert "Maestro Flow 报告" in body
    assert "门禁结果: `FAIL`" in body
    assert "策略门禁" in body
    assert "阻断摘要" in body
    assert "门禁失败原因码" in body
    assert "DEV_VERIFY_COMMAND_REQUIRED" in body
