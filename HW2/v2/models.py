"""handoff 資料模型。"""
from typing import List, Dict, Any
from dataclasses import dataclass, field, asdict

@dataclass
class Landmine:
    kind: str
    filepath: str
    line: int
    message: str
    severity: str = "medium"
    suggested_question: str = ""
    def to_dict(self):
        return asdict(self)
    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

@dataclass
class FileReport:
    filepath: str
    line_count: int = 0
    function_count: int = 0
    class_count: int = 0
    has_entry_point: bool = False
    landmines: List[Landmine] = field(default_factory=list)
    risk_level: str = "low"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["landmines"] = [m.to_dict() for m in self.landmines]
        return d

    @classmethod
    def from_dict(cls, data):
        raw_mines = data.pop("landmines", [])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        obj = cls(**{k: v for k, v in data.items() if k in known})
        obj.landmines = [Landmine.from_dict(m) for m in raw_mines]
        return obj

@dataclass
class ScanResult:
    id: int
    target_path: str
    timestamp: str
    file_count: int
    total_lines: int
    total_landmines: int
    risk_score: float
    file_reports: List[FileReport] = field(default_factory=list)
    reading_order: List[str] = field(default_factory=list)
    dep_graph: Dict[str, List[str]] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    question_checklist: List[str] = field(default_factory=list)
    # v2.0 新增欄位
    kind_distribution: Dict[str, int] = field(default_factory=dict)
    checklist_status: List[bool] = field(default_factory=list)
    excluded_patterns: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["file_reports"] = [fr.to_dict() for fr in self.file_reports]
        return d

    @classmethod
    def from_dict(cls, data):
        raw = data.pop("file_reports", [])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        obj = cls(**{k: v for k, v in data.items() if k in known})
        obj.file_reports = [FileReport.from_dict(r) for r in raw]
        # v2.0 向下相容：舊資料可能沒有這些欄位，使用預設值
        if not obj.checklist_status and obj.question_checklist:
            obj.checklist_status = [False] * len(obj.question_checklist)
        return obj

@dataclass
class Config:
    thresholds: Dict[str, Any] = field(default_factory=lambda: {
        "max_complexity": 10,
        "max_function_length": 50,
        "naming_convention": "snake_case",
    })
    # v2.0 新增：預設排除清單
    exclude: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
