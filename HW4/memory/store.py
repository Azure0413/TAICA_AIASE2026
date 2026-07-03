"""持久層：把記憶存成 JSON 檔，重啟後讀得回來，並用 id 去重。

設計取捨：
- 純 JSON、純檔案 I/O、無索引、無資料庫 —— 100% 確定性、可手動檢視、跨平台。
- atomic write：先寫 .tmp 再 os.replace()，避免 crash 時留下半截檔。
- 容錯：檔案不存在、壞 JSON、結構不是 list 都視為空 — 不可讓 agent 開機就 crash。
"""
from __future__ import annotations
import json
import os
import tempfile


class JsonStore:
    def __init__(self, path: str):
        self.path = path
        self.items: list[dict] = []
        self.load()

    def load(self) -> None:
        """從硬碟讀回 self.items。
        檔案不存在、解析失敗、或內容不是 list（例如 {}）都一律視為空 list。"""
        self.items = []
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return
        if isinstance(data, list):
            self.items = [d for d in data if isinstance(d, dict)]

    def _persist(self) -> None:
        """把 self.items 寫回硬碟（JSON）。Atomic：先寫 tmp、再 rename。"""
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".pi-memory-", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def add(self, obs: dict) -> bool:
        """新增一筆；id 已存在則跳過，回傳是否真的新增。新增後 _persist()。"""
        if not isinstance(obs, dict) or "id" not in obs:
            return False
        if any(o.get("id") == obs["id"] for o in self.items):
            return False
        self.items.append(obs)
        self._persist()
        return True

    def all(self) -> list[dict]:
        return list(self.items)

    def clear(self) -> None:
        self.items = []
        self._persist()

    def remove(self, obs_id: str) -> bool:
        """以 id 刪除一筆；回傳是否真的刪到。為 /forget CLI 命令使用。"""
        before = len(self.items)
        self.items = [o for o in self.items if o.get("id") != obs_id]
        if len(self.items) != before:
            self._persist()
            return True
        return False

    def update(self, obs_id: str, **fields) -> bool:
        """局部更新一筆（例如 last_used_at）。為 decay 機制與 /recall 使用。"""
        for o in self.items:
            if o.get("id") == obs_id:
                o.update(fields)
                self._persist()
                return True
        return False
