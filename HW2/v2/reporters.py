"""輸出格式化。重點是交接問題清單的呈現。"""
import json, os
from abc import ABC, abstractmethod

class BaseReporter(ABC):
    @abstractmethod
    def format_scan(self, result): ...
    @abstractmethod
    def format_history(self, results): ...
    @abstractmethod
    def format_comparison(self, r1, r2): ...

def _mine_identity(m):
    """產生地雷的識別鍵，用於比較兩次掃描的地雷差異。

    判斷「同一顆地雷」的策略：以 (kind, basename, message) 為主鍵。
    - 使用 basename 而非完整路徑，以容忍目錄結構小幅變動。
    - 不使用行號，因為程式碼編輯後行號容易偏移。
    - message 包含函式名稱等資訊，能區分同檔案中不同函式的同類問題。
    """
    return (m.kind, os.path.basename(m.filepath), m.message)

def _diff_landmines(r1, r2):
    """比較兩次掃描的地雷，回傳 (新增, 消失, 持續存在)。"""
    all_m1 = [m for fr in r1.file_reports for m in fr.landmines]
    all_m2 = [m for fr in r2.file_reports for m in fr.landmines]

    set1 = {}
    for m in all_m1:
        key = _mine_identity(m)
        set1.setdefault(key, []).append(m)

    set2 = {}
    for m in all_m2:
        key = _mine_identity(m)
        set2.setdefault(key, []).append(m)

    keys1, keys2 = set(set1.keys()), set(set2.keys())
    added = []      # 在 r2 出現、r1 沒有
    removed = []    # 在 r1 出現、r2 沒有（已修復）
    kept = []       # 兩次都有

    for k in keys2 - keys1:
        added.extend(set2[k])
    for k in keys1 - keys2:
        removed.extend(set1[k])
    for k in keys1 & keys2:
        kept.extend(set2[k])

    return added, removed, kept

class TextReporter(BaseReporter):

    def format_scan(self, result):
        sep, thin = "=" * 62, "─" * 62
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        out = [sep, f"  Handoff Report #{result.id}", f"  Target: {result.target_path}",
               f"  Time:   {result.timestamp}", sep,
               f"  Files scanned   : {result.file_count}",
               f"  Total lines     : {result.total_lines}",
               f"  Landmines found : {result.total_landmines}",
               f"  Risk Score      : {result.risk_score}/100", thin]
        # v2.0：顯示本次排除的路徑模式
        if getattr(result, "excluded_patterns", None):
            out.append(f"  Excluded patterns: {', '.join(result.excluded_patterns)}")
            out.append(thin)
        if result.entry_points:
            out.append("  Entry Points:")
            out.extend(f"    -> {ep}" for ep in result.entry_points)
            out.append(thin)
        if result.reading_order:
            out.append("  Suggested Reading Order:")
            for i, fp in enumerate(result.reading_order, 1):
                deps = result.dep_graph.get(fp, [])
                tag = f"  (deps: {', '.join(os.path.basename(d) for d in deps)})" if deps else ""
                out.append(f"    {i}. {fp}{tag}")
            out.append(thin)
        # v2.0：地雷類型分布區塊
        dist = getattr(result, "kind_distribution", None) or {}
        if dist:
            out.append("  Landmine Distribution:")
            total = sum(dist.values()) or 1
            max_kind = max(dist, key=dist.get)
            for kind in sorted(dist, key=dist.get, reverse=True):
                count = dist[kind]
                pct = count / total * 100
                bar = "█" * int(pct / 5)
                marker = " ◀ MOST COMMON" if kind == max_kind else ""
                out.append(f"    {kind:<22} {count:>3} ({pct:5.1f}%) {bar}{marker}")
            out.append(thin)
        for fr in result.file_reports:
            entry = " [ENTRY]" if fr.has_entry_point else ""
            out.append(f"  {icon.get(fr.risk_level, '')} {fr.filepath}{entry}  (risk: {fr.risk_level})")
            out.append(f"    Lines: {fr.line_count} | Funcs: {fr.function_count} | Classes: {fr.class_count}")
            if fr.landmines:
                out.append(f"    Landmines ({len(fr.landmines)}):")
                for m in fr.landmines:
                    out.append(f"      {icon.get(m.severity, '')} L{m.line} [{m.kind}] {m.message}")
            out.append(thin)
        if result.question_checklist:
            out.extend(["  交接問題清單 — 拿去找學長姊問，趁他們還在的時候排雷：", thin])
            for i, q in enumerate(result.question_checklist, 1):
                out.append(f"    {i}. {q}")
            out.append(thin)
        return "\n".join(out)

    def format_history(self, results):
        if not results:
            return "No scan records found."
        out = [f"{'ID':<6}{'Target':<28}{'Risk':<10}{'Mines':<8}{'Files':<8}{'Time'}", "─" * 74]
        for r in results:
            t = r.target_path if len(r.target_path) <= 26 else "..." + r.target_path[-23:]
            out.append(f"{r.id:<6}{t:<28}{r.risk_score:<10}{r.total_landmines:<8}{r.file_count:<8}{r.timestamp}")
        return "\n".join(out)

    def format_comparison(self, r1, r2):
        thin = "─" * 58
        diff = round(r2.risk_score - r1.risk_score, 1)
        trend = "improved" if diff > 0 else ("degraded" if diff < 0 else "unchanged")
        h1, h2 = f"#{r1.id}", f"#{r2.id}"
        out = [f"Comparison: {h1} vs {h2}", thin,
               f"  {'Metric':<28}{h1:<15}{h2:<15}", thin,
               f"  {'Risk Score':<28}{r1.risk_score:<15}{r2.risk_score:<15}",
               f"  {'Landmines':<28}{r1.total_landmines:<15}{r2.total_landmines:<15}",
               f"  {'Files':<28}{r1.file_count:<15}{r2.file_count:<15}",
               thin, f"  Score Change: {diff:+.1f} ({trend})"]
        # v2.0：地雷差異追蹤
        added, removed, kept = _diff_landmines(r1, r2)
        out.append(thin)
        if not added and not removed:
            out.append("  No new or fixed landmines — 無新增或修復的地雷。")
        else:
            if removed:
                out.append(f"  [FIXED] Resolved landmines ({len(removed)}):")
                for m in removed:
                    out.append(f"    [FIXED] {os.path.basename(m.filepath)} L{m.line} [{m.kind}] {m.message}")
            if added:
                out.append(f"  [NEW] New landmines ({len(added)}):")
                for m in added:
                    out.append(f"    [NEW]   {os.path.basename(m.filepath)} L{m.line} [{m.kind}] {m.message}")
            out.append(f"  Unchanged: {len(kept)} landmine(s) still present")
        out.append(thin)
        return "\n".join(out)

    def format_checklist(self, result):
        """v2.0：格式化交接問題清單含確認狀態。"""
        thin = "─" * 62
        out = [f"Checklist for Scan #{result.id}", thin]
        if not result.question_checklist:
            out.append("  (No checklist items)")
            return "\n".join(out)
        statuses = result.checklist_status or [False] * len(result.question_checklist)
        for i, q in enumerate(result.question_checklist, 1):
            idx = i - 1
            resolved = statuses[idx] if idx < len(statuses) else False
            mark = "✅" if resolved else "⬜"
            status_text = "已確認" if resolved else "未確認"
            out.append(f"  {mark} {i}. [{status_text}] {q}")
        out.append(thin)
        total = len(result.question_checklist)
        done = sum(1 for s in statuses[:total] if s)
        out.append(f"  Progress: {done}/{total} confirmed")
        return "\n".join(out)

class JsonReporter(BaseReporter):

    def format_scan(self, result):
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    def format_history(self, results):
        return json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)

    def format_comparison(self, r1, r2):
        added, removed, kept = _diff_landmines(r1, r2)
        return json.dumps({
            "scan_1": r1.to_dict(), "scan_2": r2.to_dict(),
            "score_diff": round(r2.risk_score - r1.risk_score, 2),
            "diff": {
                "added": [m.to_dict() for m in added],
                "fixed": [m.to_dict() for m in removed],
                "unchanged_count": len(kept),
            }
        }, indent=2, ensure_ascii=False)

    def format_checklist(self, result):
        """v2.0：JSON 格式的清單狀態。"""
        statuses = result.checklist_status or [False] * len(result.question_checklist)
        items = []
        for i, q in enumerate(result.question_checklist):
            items.append({
                "index": i + 1,
                "question": q,
                "resolved": statuses[i] if i < len(statuses) else False,
            })
        return json.dumps({"scan_id": result.id, "checklist": items}, indent=2, ensure_ascii=False)

_REPORTERS = {"text": TextReporter, "json": JsonReporter}

def get_reporter(fmt):
    return _REPORTERS.get(fmt, TextReporter)()
