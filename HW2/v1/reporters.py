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
        return "\n".join(out)

class JsonReporter(BaseReporter):

    def format_scan(self, result):
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    def format_history(self, results):
        return json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)

    def format_comparison(self, r1, r2):
        return json.dumps({"scan_1": r1.to_dict(), "scan_2": r2.to_dict(),
                           "score_diff": round(r2.risk_score - r1.risk_score, 2)},
                          indent=2, ensure_ascii=False)

_REPORTERS = {"text": TextReporter, "json": JsonReporter}

def get_reporter(fmt):
    return _REPORTERS.get(fmt, TextReporter)()
