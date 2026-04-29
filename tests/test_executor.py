from __future__ import annotations

from pathlib import Path

from maestro_flow.executor import apply_file_changes, run_commands


def test_apply_file_changes_writes_files_and_patch(tmp_path: Path):
    repo = tmp_path
    original = repo / "demo.txt"
    original.write_text("old\n", encoding="utf-8")
    run_dir = repo / ".maestro" / "runs" / "test"
    run_dir.mkdir(parents=True, exist_ok=True)

    report = apply_file_changes(
        repo_root=repo,
        file_changes=[
            {
                "path": "demo.txt",
                "action": "update",
                "purpose": "测试更新",
                "content": "new\n",
            },
            {
                "path": "new.txt",
                "action": "create",
                "purpose": "测试创建",
                "content": "created\n",
            },
        ],
        run_dir=run_dir,
        round_index=1,
    )

    assert (repo / "demo.txt").read_text(encoding="utf-8") == "new\n"
    assert (repo / "new.txt").read_text(encoding="utf-8") == "created\n"
    assert report["applied_count"] == 2
    assert report["patch_file"]
    assert (run_dir / "fix_round_1.patch").exists()
    assert (run_dir / "file_apply_round_1.json").exists()


def test_run_commands_blocks_disallowed_command(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["echo hello"],
        allowed_prefixes=["python -c"],
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is False
    assert results[0].exit_code == 126


def test_run_commands_supports_regex_policy(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["python -m pytest -q --maxfail=1"],
        allowed_prefixes=[],
        command_policies=[
            {
                "mode": "regex",
                "pattern": r"^python\s+-m\s+pytest\b",
                "required_args": ["--maxfail=1"],
                "forbidden_args": ["-k dangerous"],
            }
        ],
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is True


def test_run_commands_warns_on_missing_required_arg_when_policy_warn(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["python -c \"print('ok')\""],
        allowed_prefixes=[],
        command_policies=[
            {
                "mode": "prefix",
                "pattern": "python -c",
                "required_args": ["--strict"],
                "missing_required_action": "warn",
            }
        ],
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is True
    assert results[0].exit_code == 0
    assert results[0].warnings


def test_run_commands_blocks_on_forbidden_arg_when_policy_block(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["python -m pytest -q --maxfail=0"],
        allowed_prefixes=[],
        command_policies=[
            {
                "mode": "regex",
                "pattern": r"^python\s+-m\s+pytest\b",
                "forbidden_args": ["--maxfail=0"],
                "forbidden_arg_action": "block",
            }
        ],
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is False
    assert results[0].exit_code == 126


def test_run_commands_allows_unmatched_policy_when_unmatched_warn(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["python -c \"print('ok')\""],
        allowed_prefixes=[],
        command_policies=[
            {
                "mode": "regex",
                "pattern": r"^python\s+-m\s+pytest\b",
            }
        ],
        unmatched_action="warn",
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is True
    assert results[0].exit_code == 0
    assert results[0].warnings


def test_run_commands_blocks_dangerous_fragment(tmp_path: Path):
    results = run_commands(
        repo_root=tmp_path,
        commands=["python -c \"print('x')\" && rm -rf tmp"],
        allowed_prefixes=["python -c"],
        blocked_fragments=["rm -rf"],
        timeout_seconds=10,
    )

    assert len(results) == 1
    assert results[0].allowed is False
    assert results[0].exit_code == 126
