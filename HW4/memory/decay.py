"""遺忘 Decay：對久未使用的記憶，對其分數乘上指數衰減係數。

對應 Ebbinghaus 遺忘曲線（exponential forgetting）的工程化近似：
    weight(t) = exp(-λ · age_in_days)
其中 age 由「now − last_used_at」決定；λ 由半衰期 (`half_life_days`) 推導：
    λ = ln(2) / half_life_days

設計準則：
- 退化路徑安全：沒有 last_used_at 或 timestamp 時直接給 1.0（不衰減），避免新進記憶被誤殺。
- 純函式：(score, ts, now) 三者決定輸出。
- last_used_at 是「軟訊號」：本作業在 `retrieve()` 命中時 touch；之後即使一週沒用、
  也只是排序略後，**不會刪除**（避免破壞「持久記憶」的契約）。
"""
from __future__ import annotations
import math


_MS_PER_DAY = 1000.0 * 60.0 * 60.0 * 24.0


def decay_weight(
    last_used_at_ms: float | None,
    now_ms: float,
    half_life_days: float = 30.0,
    floor: float = 0.2,
) -> float:
    """以半衰期 `half_life_days` 算指數衰減；最低不低於 `floor`（避免完全消失）。"""
    if not last_used_at_ms or last_used_at_ms <= 0:
        return 1.0
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (now_ms - last_used_at_ms) / _MS_PER_DAY)
    lam = math.log(2.0) / half_life_days
    w = math.exp(-lam * age_days)
    return max(floor, w)


def apply_decay(
    ranked: list[dict],
    observations: dict[str, dict],
    now_ms: float,
    half_life_days: float = 30.0,
    floor: float = 0.2,
) -> list[dict]:
    """把 ranked 裡每筆的 score 乘上 decay_weight，重新排序（同分保持原順序）。"""
    new = []
    for i, r in enumerate(ranked):
        obs = observations.get(r["id"])
        last = obs.get("last_used_at") if obs else None
        w = decay_weight(last, now_ms, half_life_days, floor)
        new.append((i, r["id"], r["score"] * w))
    new.sort(key=lambda x: (-x[2], x[0]))
    return [{"id": rid, "score": s} for _, rid, s in new]
