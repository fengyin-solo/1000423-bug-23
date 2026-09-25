"""报警中心业务规则：状态流转、字段校验与统计口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["报警编号", "报警类型", "报警等级"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认报警": "已确认", "处置报警": "已处置", "忽略报警": "已忽略"}

# 待确认、已确认都还没闭环，计入待处理；已处置、已忽略都算闭环，不再待处理。
OPEN_STATUSES = {"待确认", "已确认"}
# 各状态允许执行的动作：已处置、已忽略是终态，只能幂等重复，不能再改判回其他状态。
ALLOWED_ACTIONS = {
    "待确认": {"确认报警", "处置报警", "忽略报警"},
    "已确认": {"处置报警", "忽略报警"},
    "已处置": set(),
    "已忽略": set(),
}
# 异常量只看报警等级：高等级报警无论被确认、处置还是忽略都计入异常，与动作无关。
HIGH_LEVEL_KEYWORDS = ("高", "紧急", "重大")


def is_high_level(level: Any) -> bool:
    """判断报警等级是否属于高等级，异常量统计与卡片都走这一个口径。"""
    text = str(level or "")
    return any(keyword in text for keyword in HIGH_LEVEL_KEYWORDS)


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        alarm_type: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("报警编号", ""))]
        if alarm_type:
            rows = [row for row in rows if alarm_type in str(row.get("报警类型", ""))]
        if level:
            rows = [row for row in rows if level in str(row.get("报警等级", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> list[dict[str, Any]]:
        """报警页统计卡片：与列表、运营概览读同一份数据，刷新后口径一致；无数据时返回零值。"""
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        return [
            {"label": "今日报警", "value": sum(1 for row in rows if str(row.get("触发时间") or "").startswith(today))},
            {"label": "待确认报警", "value": sum(1 for row in rows if row.get("status") == "待确认")},
            {"label": "高等级报警", "value": sum(1 for row in rows if is_high_level(row.get("报警等级")))},
        ]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["报警状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = is_high_level(entry.get("报警等级"))
        if not str(values.get("触发时间") or "").strip():
            entry["触发时间"] = date.today().isoformat()
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any], str] | tuple[None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"报警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于报警中心可执行范围"
        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current == target:
            # 幂等：重复确认/处置/忽略不报错，状态保持不变。
            return entry, f"报警事件已是「{target}」状态，无需重复{action}"
        if action not in ALLOWED_ACTIONS.get(current, set()):
            return None, f"报警事件当前为「{current}」，不能再执行「{action}」"
        entry["status"] = target
        entry["报警状态"] = target
        entry["pending"] = target in OPEN_STATUSES
        # 异常口径只跟报警等级走，顺手把历史遗留的 abnormal 标记拉回同一口径。
        entry["abnormal"] = is_high_level(entry.get("报警等级"))
        return entry, f"报警事件已{action}"
