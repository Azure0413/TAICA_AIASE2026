"""隱私過濾：在 observation 進入存儲前，把常見密文型 token 改為 [REDACTED]。

設計取捨：
- 純 regex、純 Python、無外部呼叫 → 100% 確定性，可被單元測試覆蓋。
- 寧可「過度遮蔽」也不要「漏掉」：模式偏寬，但保留前 4 碼方便人工辨識。
- 不直接刪整段，這樣使用者仍可看到「這裡曾有金鑰」，便於除錯。

支援模式（皆可加在 _PATTERNS 列表中擴充）：
- OpenAI sk- 金鑰         e.g. sk-abcd1234...
- Anthropic / Claude key   e.g. sk-ant-...
- GitHub personal token   e.g. ghp_..., gho_..., ghs_...
- AWS access key id       e.g. AKIA....
- Generic password=...    遮整段值
- Generic api_key=...     遮整段值
- Bearer JWT-ish blobs
- 12+ 位連續 high-entropy hex / base64-ish 字串（可選，預設不啟用避免誤殺）
"""
from __future__ import annotations
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"), r"sk-ant-[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{4}[A-Za-z0-9_\-]{4,}"),
     lambda m: m.group(0)[:7] + "[REDACTED]"),
    (re.compile(r"\b(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{6,}"),
     lambda m: m.group(1) + "_[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}"),
     lambda m: m.group(0)[:6] + "[REDACTED]"),
    (re.compile(
        r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token|access[_-]?key)\s*[:=]\s*['\"]?([^\s'\"\,;]+)",
    ), lambda m: f"{m.group(1)}=[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{16,}"),
     r"Bearer [REDACTED]"),
]


def redact(text: str) -> str:
    """把已知敏感樣式遮成 [REDACTED]。"""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact_observation(obs: dict) -> dict:
    """非破壞性地回傳一份遮蔽過的 observation。
    只動 summary 與 tags（id 不能動，否則去重會壞掉）。"""
    if not isinstance(obs, dict):
        return obs
    new = dict(obs)
    if "summary" in new and isinstance(new["summary"], str):
        new["summary"] = redact(new["summary"])
    if "tags" in new and isinstance(new["tags"], list):
        new["tags"] = [redact(t) if isinstance(t, str) else t for t in new["tags"]]
    return new


def contains_secret(text: str) -> bool:
    """純判斷用，不修改文字。給 /recall 顯示「⚠️ 含敏感欄位」標記。"""
    if not isinstance(text, str) or not text:
        return False
    return redact(text) != text
