"""报警中心业务规则：状态流转、字段校验与统计口径都收在这里。

列表、页面卡片、运营概览共用同一套由状态推导的口径，动作本身不再决定标记：
- 待确认 / 已确认 属于未闭环报警：pending=True、abnormal=True（仍有异常待跟进）；
- 已处置 / 已忽略 属于闭环：pending=False、abnormal=False
  （处置代表问题解决，忽略代表误报关闭，两者都不再算待处理或异常）。
- 已处置、已忽略是终态：已忽略的报警不能再被确认或处置；
  对终态重复执行同一动作按幂等处理，返回成功提示而不是报错。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["报警编号", "报警类型", "报警等级"]
STATUS_PENDING = "待确认"
STATUS_CONFIRMED = "已确认"
STATUS_HANDLED = "已处置"
STATUS_IGNORED = "已忽略"
STATUS_ORDER = [STATUS_PENDING, STATUS_CONFIRMED, STATUS_HANDLED, STATUS_IGNORED]
OPEN_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED)
CLOSED_STATUSES = (STATUS_HANDLED, STATUS_IGNORED)
ACTION_RULES = {
    "确认报警": STATUS_CONFIRMED,
    "处置报警": STATUS_HANDLED,
    "忽略报警": STATUS_IGNORED,
}
ACTION_VERBS = {"确认报警": "确认", "处置报警": "处置", "忽略报警": "忽略"}
HIGH_LEVEL_KEYWORDS = ("紧急", "高", "特", "一级", "重大")


def _is_open_status(status: Any) -> bool:
    return status in OPEN_STATUSES


def _is_high_level(level: Any) -> bool:
    text = str(level or "")
    return any(keyword in text for keyword in HIGH_LEVEL_KEYWORDS)


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("报警编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = True
        rows.append(entry)
        return entry, []

    def summary(self) -> dict[str, int]:
        """页面卡片指标：与列表筛选、运营概览共用同一套状态口径。

        表为空时各项自然为 0，不抛异常。
        """
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        return {
            "total": len(rows),
            "today": sum(1 for row in rows if str(row.get("触发时间", ""))[:10] == today),
            "pending": sum(1 for row in rows if row.get("status") in OPEN_STATUSES),
            "unconfirmed": sum(1 for row in rows if row.get("status") == STATUS_PENDING),
            "high_level": sum(1 for row in rows if _is_high_level(row.get("报警等级"))),
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"报警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于报警中心可执行范围"
        target = ACTION_RULES[action]
        current = entry.get("status")
        if current == target:
            # 重复忽略、重复处置等幂等场景：保持状态不变，按成功返回，不报错。
            return entry, f"报警事件已是「{target}」状态，无需重复操作"
        if current == STATUS_IGNORED:
            return None, "报警事件已忽略，不能再执行确认或处置"
        if current == STATUS_HANDLED:
            return None, "报警事件已处置完成，状态不能再变更"
        entry["status"] = target
        entry["pending"] = _is_open_status(target)
        entry["abnormal"] = _is_open_status(target)
        return entry, f"报警事件已{ACTION_VERBS[action]}"
