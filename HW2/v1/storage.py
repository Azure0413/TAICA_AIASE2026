"""儲存層。目前用 JSON，之後要換 SQLite 只要再寫一個 class 就好。"""
from typing import List, Optional
import json, os
from abc import ABC, abstractmethod

from models import ScanResult, Config

class BaseStorage(ABC):
    @abstractmethod
    def save_scan(self, result: ScanResult) -> int: ...
    @abstractmethod
    def get_scan(self, scan_id: int) -> Optional[ScanResult]: ...
    @abstractmethod
    def list_scans(self, limit: int = 10) -> List[ScanResult]: ...
    @abstractmethod
    def get_latest(self) -> Optional[ScanResult]: ...
    @abstractmethod
    def load_config(self) -> Config: ...
    @abstractmethod
    def save_config(self, config: Config) -> None: ...

class JsonStorage(BaseStorage):
    def __init__(self, data_dir=".handoff"):
        self._dir = data_dir
        self._scans = os.path.join(data_dir, "scans.json")
        self._cfg = os.path.join(data_dir, "config.json")
        os.makedirs(data_dir, exist_ok=True)

    def _read(self):
        if not os.path.exists(self._scans):
            return []
        with open(self._scans, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data):
        with open(self._scans, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_scan(self, result):
        recs = self._read()
        new_id = max((r["id"] for r in recs), default=0) + 1
        result.id = new_id
        recs.append(result.to_dict())
        self._write(recs)
        return new_id

    def get_scan(self, scan_id):
        for r in self._read():
            if r["id"] == scan_id:
                return ScanResult.from_dict(r)
        return None

    def list_scans(self, limit=10):
        recs = sorted(self._read(), key=lambda x: x["id"], reverse=True)
        return [ScanResult.from_dict(r) for r in recs[:limit]]

    def get_latest(self):
        recs = self._read()
        return ScanResult.from_dict(max(recs, key=lambda x: x["id"])) if recs else None

    def load_config(self):
        if not os.path.exists(self._cfg):
            return Config()
        with open(self._cfg, "r", encoding="utf-8") as f:
            return Config.from_dict(json.load(f))

    def save_config(self, config):
        with open(self._cfg, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
