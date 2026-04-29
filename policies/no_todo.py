from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def run(
    stage_outputs: dict[str, Any],
    config: Any,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    示例策略插件：检查阶段输出中是否出现 TODO / FIXME。
    命中时返回阻断失败，未命中则通过。
    """
    flattened = json.dumps(stage_outputs, ensure_ascii=False)
    matched = re.search(r"\b(TODO|FIXME)\b", flattened, flags=re.IGNORECASE)
    if matched:
        keyword = matched.group(1).upper()
        return {
            "policy_id": "PLUGIN_NO_TODO",
            "status": "fail",
            "blocking": True,
            "message": f"检测到待办标记 {keyword}，请在合并前清理。",
        }

    return {
        "policy_id": "PLUGIN_NO_TODO",
        "status": "pass",
        "blocking": True,
        "message": "未检测到 TODO/FIXME 标记。",
    }

