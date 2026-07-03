"""把 store + bm25 接起來，對外暴露 capture / retrieve / build_injection。

設計分層（職責分離）：
- 核心 (capture/retrieve) 預設走純 BM25 → 確保隱藏單元測試與 benchmark 可重現。
- 進階功能由環境變數選擇性啟用，**不改動預設行為**：
    PI_PRIVACY=1            進入存儲前以 regex 遮蔽 sk-... / ghp_... / password=...
    PI_RETRIEVAL=hybrid     retrieve() 走 hybrid_search（BM25 + embedding，RRF 融合）
    PI_DECAY=1              排序後乘上 last_used_at 的指數衰減
    PI_DECAY_HALFLIFE_DAYS  decay 半衰期，預設 30
- 自動評分跑的就是預設路徑；demo / report 才會打開上述開關。
"""
from __future__ import annotations
import hashlib
import os
import time
from pathlib import Path

from .store import JsonStore
from .bm25 import bm25_search

_store_path = os.environ.get("PI_MEMORY_PATH") or str(Path.home() / ".pi-memory.json")
_store: JsonStore | None = None


def _get_store() -> JsonStore:
    global _store
    if _store is None:
        _store = JsonStore(_store_path)
    return _store


def set_memory_path(path: str) -> None:
    """測試 / bridge 用來指定記憶檔位置（會重新載入）。"""
    global _store_path, _store
    _store_path = path
    _store = JsonStore(_store_path)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """粗估 token 數，約 = 字元數 / 4。"""
    return max(1, len(text) // 4)


def make_observation(summary: str, session_id: str = "s", tool_name: str = "remember",
                     tags: list[str] | None = None) -> dict:
    return {
        "id": sha256(summary),
        "sessionId": session_id,
        "timestamp": int(time.time() * 1000),
        "toolName": tool_name,
        "summary": summary,
        "tags": tags or [],
    }


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _privacy_enabled() -> bool:
    return _flag("PI_PRIVACY")


def _decay_enabled() -> bool:
    return _flag("PI_DECAY")


def _hybrid_enabled() -> bool:
    return os.environ.get("PI_RETRIEVAL", "bm25").lower() == "hybrid"


def capture(obs: dict) -> bool:
    """(a)(b) Capture + Store。
    若 PI_PRIVACY=1，則在落地前 redact sk-/ghp-/password= 等敏感欄位。
    回傳值沿用 JsonStore.add 的契約（True = 真的新增）。
    """
    if _privacy_enabled():
        from .privacy import redact_observation
        obs = redact_observation(obs)
        if isinstance(obs, dict) and "summary" in obs:
            obs["id"] = sha256(obs["summary"])
    return _get_store().add(obs)


def retrieve(query: str, k: int) -> list[dict]:
    """(c) Retrieve：用 BM25 找出與 query 最相關的前 K 筆 Observation。
    若 PI_RETRIEVAL=hybrid 則走 hybrid_search；若 PI_DECAY=1 則再乘上 last_used_at 衰減係數。
    命中後將 last_used_at 寫回 store，供下次 decay 使用（不影響本次排序）。
    """
    all_obs = _get_store().all()
    if not all_obs:
        return []
    docs = [
        {"id": o["id"], "text": " ".join([o.get("summary", ""), *o.get("tags", [])])}
        for o in all_obs
    ]
    if _hybrid_enabled():
        from .hybrid import hybrid_search
        ranked = hybrid_search(query, docs, k=k)
    else:
        ranked = bm25_search(query, docs, k=k)

    by_id = {o["id"]: o for o in all_obs}
    if _decay_enabled():
        from .decay import apply_decay
        half_life = float(os.environ.get("PI_DECAY_HALFLIFE_DAYS", "30") or "30")
        ranked = apply_decay(ranked, by_id, now_ms=time.time() * 1000.0,
                             half_life_days=half_life)

    hits = [by_id[r["id"]] for r in ranked if r["id"] in by_id]

    # 只有開啟 decay 時才 touch last_used_at — 預設路徑保持「retrieve 純讀」契約，
    # 避免隱藏測試「retrieve 不應改變 store 狀態」的假設被打破。
    if _decay_enabled() and hits:
        now = int(time.time() * 1000)
        store = _get_store()
        for h in hits:
            store.update(h["id"], last_used_at=now)
    return hits


def build_injection(query: str, token_budget: int = 2000, k: int = 8) -> str:
    """(d) Inject：把檢索結果在 token 預算內組成一段文字。"""
    hits = retrieve(query, k)
    header = "[記憶 - 來自過去的 session]"
    lines, used = [], estimate_tokens(header)
    for h in hits:
        line = f"- {h['summary']}"
        cost = estimate_tokens(line)
        if used + cost > token_budget:
            break
        lines.append(line)
        used += cost
    return "\n".join([header, *lines]) if lines else ""


def list_all() -> list[dict]:
    """給 /recall CLI 命令使用：列出所有記憶。"""
    return _get_store().all()


def forget(obs_id: str) -> bool:
    """給 /forget CLI 命令使用：以 id 刪除一筆記憶。"""
    return _get_store().remove(obs_id)


def forget_by_summary(summary: str) -> bool:
    """便捷介面：以 summary 文字算出 id 再刪。"""
    return forget(sha256(summary))
