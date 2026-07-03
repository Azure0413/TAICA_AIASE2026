"""handoff — 程式碼交接避雷小幫手。"""
import sys, os
import click
from datetime import datetime
from analyzers import ScanEngine
from models import ScanResult
from reporters import get_reporter
from storage import JsonStorage

def _storage():
    return JsonStorage()

def _engine(config=None):
    return ScanEngine(config=config)

def _calc_risk_and_checklist(file_reports, config):
    """算風險等級，彙整交接問題清單。100 分起扣，地雷越多分越低。"""
    if not file_reports:
        return 0.0, []
    wt = {"high": 5, "medium": 3, "low": 1}
    questions, scores = [], []
    for fr in file_reports:
        s = max(100.0 - sum(wt.get(m.severity, 1) for m in fr.landmines) * 2, 0.0)
        scores.append(s)
        fr.risk_level = "high" if s < 50 else ("medium" if s < 80 else "low")
        for m in fr.landmines:
            if m.suggested_question and m.severity in ("high", "medium"):
                questions.append(f"[{os.path.basename(fr.filepath)}] {m.suggested_question}")
    return round(sum(scores) / len(scores), 1), questions

@click.group()
@click.version_option(version="1.0.0", prog_name="handoff")
def cli():
    """handoff — 程式碼交接避雷小幫手。

    掃描 Python 專案，找出交接地雷，產生問題清單和建議閱讀順序。
    """

@cli.command()
@click.argument("path")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--output", "-o", default=None, help="Save report to file.")
def scan(path, fmt, output):
    """Scan Python code at PATH for handover landmines."""
    if not os.path.exists(path):
        click.echo(f"Error: Path not found: {path}", err=True); sys.exit(1)
    store = _storage()
    config = store.load_config()
    engine = _engine(config)
    reports, dep_graph, reading_order, entries = engine.scan_path(path)
    if not reports:
        click.echo(f"Error: No Python files found in: {path}", err=True); sys.exit(1)
    risk_score, checklist = _calc_risk_and_checklist(reports, config)
    total_mines = sum(len(fr.landmines) for fr in reports)
    result = ScanResult(
        id=0, target_path=os.path.normpath(path),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        file_count=len(reports), total_lines=sum(fr.line_count for fr in reports),
        total_landmines=total_mines, risk_score=risk_score,
        file_reports=reports, reading_order=reading_order,
        dep_graph=dep_graph, entry_points=entries, question_checklist=checklist)
    saved_id = store.save_scan(result)
    result.id = saved_id
    text = get_reporter(fmt).format_scan(result)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        click.echo(f"Report saved to: {output}")
    else:
        click.echo(text)

@cli.command()
@click.option("--id", "scan_id", type=int, default=None)
@click.option("--latest", is_flag=True)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def report(scan_id, latest, fmt):
    """Display a previously saved scan report."""
    if not latest and scan_id is None:
        click.echo("Error: Specify --id INT or --latest", err=True); sys.exit(2)
    result = _storage().get_latest() if latest else _storage().get_scan(scan_id)
    if result is None:
        click.echo("Error: Scan not found", err=True); sys.exit(1)
    click.echo(get_reporter(fmt).format_scan(result))

@cli.command()
@click.option("--limit", type=int, default=10)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def history(limit, fmt):
    """List past scan runs."""
    click.echo(get_reporter(fmt).format_history(_storage().list_scans(limit=limit)))

@cli.command()
@click.argument("id1", type=int)
@click.argument("id2", type=int)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def compare(id1, id2, fmt):
    """Compare two scan results side by side."""
    store = _storage()
    r1, r2 = store.get_scan(id1), store.get_scan(id2)
    if r1 is None:
        click.echo(f"Error: Scan #{id1} not found", err=True); sys.exit(1)
    if r2 is None:
        click.echo(f"Error: Scan #{id2} not found", err=True); sys.exit(1)
    click.echo(get_reporter(fmt).format_comparison(r1, r2))

@cli.command()
@click.option("--show", is_flag=True)
@click.option("--set", "set_val", default=None, help="KEY=VALUE")
def config(show, set_val):
    """View or modify handoff configuration."""
    store = _storage()
    cfg = store.load_config()
    if set_val:
        if "=" not in set_val:
            click.echo("Error: Use format KEY=VALUE", err=True); sys.exit(2)
        key, val = set_val.split("=", 1)
        key, val = key.strip(), val.strip()
        for conv in (int, float):
            try: val = conv(val); break
            except ValueError: pass
        cfg.thresholds[key] = val
        store.save_config(cfg)
        click.echo(f"Config updated: {key} = {val}")
    elif show:
        click.echo("Current configuration:")
        for k, v in cfg.thresholds.items():
            click.echo(f"  {k}: {v}")
    else:
        click.echo("Error: Specify --show or --set KEY=VALUE", err=True); sys.exit(2)

if __name__ == "__main__":
    cli()
