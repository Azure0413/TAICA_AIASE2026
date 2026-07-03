#!/usr/bin/env python3
"""
render.py — Markdown Rendering Engine (HTML + PDF)
===================================================
Renders content.md into styled HTML and print-ready PDF.

Tool chain:
  1. Python-Markdown  : Markdown -> HTML core
  2. pymdown-extensions: task lists, math, strikethrough, superfences
  3. Pygments         : syntax highlighting
  4. wkhtmltopdf      : HTML -> PDF (CJK support)
  5. KaTeX (CDN)      : math formula rendering (HTML)
  6. Mermaid.js (CDN) : diagrams and charts (HTML)

Usage:
  python render.py                # HTML + PDF
  python render.py --html-only    # HTML only
  python render.py --pdf-only     # PDF only
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import markdown
from markdown.extensions.toc import TocExtension


def find_wkhtmltopdf():
    """Locate wkhtmltopdf binary across platforms."""
    # 1) Already in PATH?
    path = shutil.which('wkhtmltopdf')
    if path:
        return path

    # 2) Common Windows install locations
    if platform.system() == 'Windows':
        candidates = [
            os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                         'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
                         'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                         'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    return 'wkhtmltopdf'  # fallback: hope it's in PATH


# ── CSS ──────────────────────────────────────

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
    --primary: #1e40af;
    --primary-light: #dbeafe;
    --primary-dark: #1e3a8a;
    --accent: #0ea5e9;
    --accent-light: #e0f2fe;
    --success: #059669;
    --success-light: #d1fae5;
    --warning: #d97706;
    --warning-light: #fef3c7;
    --text: #1e293b;
    --text-secondary: #475569;
    --text-muted: #94a3b8;
    --bg: #ffffff;
    --bg-alt: #f8fafc;
    --bg-code: #0f172a;
    --border: #e2e8f0;
    --border-light: #f1f5f9;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
    --shadow-md: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04);
    --radius: 10px;
    --radius-lg: 14px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', 'Noto Sans TC', 'Microsoft JhengHei', 'PingFang TC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.85;
    font-size: 15.5px;
    max-width: 920px;
    margin: 0 auto;
    padding: 48px 56px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* ── Headings ── */
h1 {
    font-size: 2.3em;
    font-weight: 900;
    color: var(--primary);
    border-bottom: 3px solid var(--primary);
    padding-bottom: 16px;
    margin: 56px 0 28px 0;
    letter-spacing: -0.02em;
    line-height: 1.3;
}
h1:first-child { margin-top: 0; }

h2 {
    font-size: 1.5em;
    font-weight: 800;
    color: var(--primary-dark);
    margin: 48px 0 20px 0;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--border);
    letter-spacing: -0.01em;
}

h3 {
    font-size: 1.2em;
    font-weight: 700;
    color: #334155;
    margin: 32px 0 14px 0;
}

h4 {
    font-size: 1.05em;
    font-weight: 600;
    color: var(--text-secondary);
    margin: 24px 0 10px 0;
}

/* ── Text ── */
p { margin: 14px 0; }
strong { color: #0f172a; font-weight: 700; }
em { color: var(--text-secondary); font-style: italic; }
del { color: var(--text-muted); text-decoration: line-through; }

a {
    color: var(--primary);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
}
a:hover { border-bottom-color: var(--primary); }

/* ── Blockquote ── */
blockquote {
    border-left: 4px solid var(--primary);
    background: linear-gradient(135deg, var(--primary-light) 0%, #f0f4ff 100%);
    padding: 18px 24px;
    margin: 20px 0;
    border-radius: 0 var(--radius) var(--radius) 0;
    font-size: 0.95em;
    box-shadow: var(--shadow-sm);
}
blockquote p { margin: 6px 0; }
blockquote strong { color: var(--primary-dark); }

/* ── Tables ── */
table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 24px 0;
    font-size: 0.9em;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
}
thead {
    background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
    color: white;
}
th {
    padding: 13px 18px;
    text-align: left;
    font-weight: 600;
    font-size: 0.88em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
td {
    padding: 11px 18px;
    border-top: 1px solid var(--border);
}
tbody tr:nth-child(even) { background: var(--bg-alt); }
tbody tr:hover { background: #eef2ff; transition: background 0.15s; }
tbody tr:first-child td { border-top: none; }

/* ── Lists ── */
ul, ol { margin: 14px 0; padding-left: 28px; }
li { margin: 7px 0; line-height: 1.7; }
li::marker { color: var(--primary); font-weight: 700; }

/* nested lists */
li > ul, li > ol { margin: 4px 0; }

/* ── Task List ── */
.task-list-item { list-style: none; margin-left: -24px; position: relative; }
.task-list-item input[type="checkbox"] {
    margin-right: 10px;
    accent-color: var(--primary);
    width: 16px;
    height: 16px;
    vertical-align: middle;
}

/* ── Code ── */
code {
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.86em;
    background: #f1f5f9;
    color: #be185d;
    padding: 2px 8px;
    border-radius: 5px;
    border: 1px solid #e2e8f0;
}

pre {
    background: var(--bg-code);
    border-radius: var(--radius-lg);
    padding: 22px 26px;
    margin: 22px 0;
    overflow-x: auto;
    box-shadow: var(--shadow-md);
    position: relative;
}
pre code {
    background: none;
    color: #e2e8f0;
    border: none;
    padding: 0;
    font-size: 0.84em;
    line-height: 1.75;
}

.codehilite {
    background: var(--bg-code);
    border-radius: var(--radius-lg);
    padding: 22px 26px;
    margin: 22px 0;
    overflow-x: auto;
    box-shadow: var(--shadow-md);
}
.codehilite pre { background: transparent; padding: 0; margin: 0; border: none; box-shadow: none; }
.codehilite code { color: #e2e8f0; }

/* ── Horizontal Rule ── */
hr {
    border: none;
    height: 1px;
    background: linear-gradient(to right, transparent, var(--border), var(--primary), var(--border), transparent);
    margin: 40px 0;
}

/* ── Math ── */
.arithmatex { margin: 18px 0; overflow-x: auto; }

/* ── Mermaid ── */
.mermaid {
    text-align: center;
    margin: 28px 0;
    padding: 24px;
    background: linear-gradient(135deg, var(--bg-alt) 0%, #f0f4ff 100%);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
}

/* ── Images ── */
img {
    max-width: 100%;
    border-radius: var(--radius);
    margin: 18px 0;
    box-shadow: var(--shadow);
}

/* ── Pygments Token Colors (Dark Theme) ── */
.codehilite .hll { background-color: #2d3748; }
.codehilite .c, .codehilite .c1, .codehilite .cm, .codehilite .cs { color: #68d391; font-style: italic; }  /* comments */
.codehilite .k, .codehilite .kn, .codehilite .kd, .codehilite .kp { color: #b794f4; font-weight: 600; }  /* keywords */
.codehilite .s, .codehilite .s1, .codehilite .s2, .codehilite .sa, .codehilite .sb, .codehilite .sc, .codehilite .se, .codehilite .sh { color: #fbd38d; }  /* strings */
.codehilite .n, .codehilite .na, .codehilite .nb, .codehilite .nc, .codehilite .nd, .codehilite .ni, .codehilite .ne, .codehilite .nf, .codehilite .nl, .codehilite .nn, .codehilite .no, .codehilite .nt, .codehilite .nv { color: #90cdf4; }  /* names */
.codehilite .m, .codehilite .mi, .codehilite .mf, .codehilite .mh, .codehilite .mo { color: #fc8181; }  /* numbers */
.codehilite .o, .codehilite .ow { color: #cbd5e0; }  /* operators */
.codehilite .p { color: #e2e8f0; }  /* punctuation */
.codehilite .bp { color: #63b3ed; }  /* builtin pseudo */
.codehilite .fm { color: #63b3ed; }  /* function magic */
.codehilite .err { color: #fc8181; }

/* ── Print ── */
@media print {
    body { padding: 20px; font-size: 11.5px; max-width: 100%; }
    h1, h2 { page-break-after: avoid; }
    table, pre, blockquote { page-break-inside: avoid; }
    .mermaid { page-break-inside: avoid; }
    a { color: var(--primary) !important; }
}
"""


# ── PDF-specific CSS (for wkhtmltopdf) ────────

PDF_CSS_EXTRA = r"""
/* Remove CDN font import for offline PDF */
@import url('') !important;

/* wkhtmltopdf-specific overrides */
body {
    font-family: 'Noto Sans CJK TC', 'Noto Sans TC', 'Microsoft JhengHei', 'PingFang TC', sans-serif;
    font-size: 12px;
    padding: 24px 32px;
    max-width: 100%;
    line-height: 1.7;
}
h1 { font-size: 2em; margin: 36px 0 20px 0; }
h2 { font-size: 1.4em; margin: 28px 0 14px 0; }
h3 { font-size: 1.15em; margin: 20px 0 10px 0; }
pre, .codehilite { font-size: 0.82em; padding: 14px 18px; }
table { font-size: 0.85em; }
th { padding: 10px 14px; }
td { padding: 8px 14px; }
blockquote { padding: 14px 18px; }

.mermaid {
    display: none !important;  /* Mermaid.js won't run in wkhtmltopdf */
}
.mermaid-fallback {
    display: block;
    text-align: center;
    padding: 20px;
    background: #f8fafc;
    border: 1px dashed #cbd5e0;
    border-radius: 10px;
    margin: 18px 0;
    color: #64748b;
    font-style: italic;
}
"""


# ── HTML Template ────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

    <!-- KaTeX -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
            onload="renderMathInElement(document.body, {{
                delimiters: [
                    {{left: '\\\\[', right: '\\\\]', display: true}},
                    {{left: '\\\\(', right: '\\\\)', display: false}},
                    {{left: '$$', right: '$$', display: true}},
                    {{left: '$', right: '$', display: false}}
                ]
            }});"></script>

    <!-- Mermaid -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'base',
            themeVariables: {{
                primaryColor: '#dbeafe',
                primaryBorderColor: '#1e40af',
                primaryTextColor: '#1e293b',
                secondaryColor: '#f0f4ff',
                tertiaryColor: '#f8fafc',
                lineColor: '#64748b',
                textColor: '#1e293b',
                fontSize: '14px',
                fontFamily: 'Inter, Noto Sans TC, sans-serif'
            }},
            flowchart: {{ htmlLabels: true, curve: 'basis', padding: 16 }},
            gantt: {{ useWidth: 860 }}
        }});
    </script>

    <style>{css}</style>
</head>
<body>
{body}
</body>
</html>"""


PDF_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{css}</style>
    <style>{pdf_css}</style>
</head>
<body>
{body}
</body>
</html>"""


# ── Preprocessing ────────────────────────────

def strip_yaml_front_matter(text):
    """Remove YAML front matter that Python-Markdown cannot parse."""
    if text.startswith('---'):
        end = text.find('---', 3)
        if end != -1:
            return text[end + 3:].lstrip('\n')
    return text


def preprocess_mermaid(text):
    """Convert ```mermaid blocks to <div class="mermaid">."""
    pattern = r'```mermaid\s*\n(.*?)```'
    def repl(m):
        return f'\n<div class="mermaid">\n{m.group(1).strip()}\n</div>\n'
    return re.sub(pattern, repl, text, flags=re.DOTALL)


def preprocess_mermaid_for_pdf(text):
    """Convert ```mermaid blocks to fallback text for PDF."""
    pattern = r'```mermaid\s*\n(.*?)```'
    def repl(m):
        content = m.group(1).strip()
        # Extract diagram type from first line
        first_line = content.split('\n')[0].strip()
        dtype = first_line.split()[0] if first_line else 'diagram'
        return f'\n<div class="mermaid-fallback">[Mermaid {dtype} — 請參閱 HTML 版本以檢視互動式圖表]</div>\n'
    return re.sub(pattern, repl, text, flags=re.DOTALL)


# ── Conversion ───────────────────────────────

def md_to_html(md_text):
    """Convert Markdown to HTML body."""
    extensions = [
        'markdown.extensions.tables',
        'markdown.extensions.fenced_code',
        'markdown.extensions.codehilite',
        TocExtension(permalink=False, toc_depth=3),
        'markdown.extensions.attr_list',
        'markdown.extensions.def_list',
        'markdown.extensions.footnotes',
        'markdown.extensions.md_in_html',
        'pymdownx.tasklist',
        'pymdownx.arithmatex',
        'pymdownx.mark',
        'pymdownx.tilde',
        'pymdownx.superfences',
    ]
    cfg = {
        'markdown.extensions.codehilite': {
            'css_class': 'codehilite', 'linenums': False, 'guess_lang': True,
        },
        'pymdownx.tasklist': {'custom_checkbox': False},
        'pymdownx.arithmatex': {'generic': True},
        'pymdownx.tilde': {'delete': True},
    }
    return markdown.Markdown(extensions=extensions, extension_configs=cfg).convert(md_text)


# ── Renderers ────────────────────────────────

def render_html(src, dst):
    """Render Markdown to styled HTML with KaTeX + Mermaid CDN."""
    print(f"  Reading: {src}")
    with open(src, 'r', encoding='utf-8') as f:
        text = f.read()
    text = strip_yaml_front_matter(text)
    text = preprocess_mermaid(text)
    print("  Markdown -> HTML ...")
    body = md_to_html(text)
    html = HTML_TEMPLATE.format(
        title="EHPTS 提案計畫書",
        css=CSS,
        body=body
    )
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✓ {dst}")


def render_pdf_html(src, dst):
    """Render Markdown to a PDF-optimised HTML (no CDN deps)."""
    print(f"  Reading: {src}")
    with open(src, 'r', encoding='utf-8') as f:
        text = f.read()
    text = strip_yaml_front_matter(text)
    text = preprocess_mermaid_for_pdf(text)
    print("  Markdown -> PDF-optimised HTML ...")
    body = md_to_html(text)
    css_for_pdf = re.sub(r"@import url\([^)]+\);", "", CSS)
    html = PDF_HTML_TEMPLATE.format(
        title="EHPTS 提案計畫書",
        css=css_for_pdf,
        pdf_css=PDF_CSS_EXTRA,
        body=body
    )
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  ✓ {dst}")


def render_pdf(html_path, pdf_path):
    """Convert HTML to PDF using wkhtmltopdf."""
    print("  HTML -> PDF (wkhtmltopdf) ...")
    try:
        wk = find_wkhtmltopdf()
        cmd = [
            wk,
            '--quiet',
            '--enable-local-file-access',
            '--disable-javascript',
            '--load-error-handling', 'ignore',
            '--load-media-error-handling', 'ignore',
            '--encoding', 'UTF-8',
            '--page-size', 'A4',
            '--margin-top', '18mm',
            '--margin-bottom', '18mm',
            '--margin-left', '20mm',
            '--margin-right', '20mm',
            '--footer-center', '[page] / [topage]',
            '--footer-font-size', '9',
            '--footer-spacing', '6',
            html_path,
            pdf_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ {pdf_path}")
        else:
            print(f"  [!] wkhtmltopdf warning (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split('\n')[-3:]:
                    print(f"      {line}")
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"  ✓ {pdf_path} (generated despite warnings)")
    except FileNotFoundError:
        print("  [!] wkhtmltopdf not found.")
        if platform.system() == 'Windows':
            print("      Download from: https://wkhtmltopdf.org/downloads.html")
        else:
            print("      Run: sudo apt-get install wkhtmltopdf")
    except Exception as e:
        print(f"  [!] PDF failed: {e}")


# ── Main ─────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Render content.md to HTML/PDF')
    ap.add_argument('--input', default='content.md')
    ap.add_argument('--output-dir', default='output')
    ap.add_argument('--html-only', action='store_true')
    ap.add_argument('--pdf-only', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    html_out = os.path.join(args.output_dir, 'output.html')
    pdf_html = os.path.join(args.output_dir, '_pdf_temp.html')
    pdf_out = os.path.join(args.output_dir, 'output.pdf')

    print("=" * 56)
    print("  Markdown Rendering Engine  (HTML + PDF)")
    print("=" * 56)

    if not args.pdf_only:
        render_html(args.input, html_out)

    if not args.html_only:
        render_pdf_html(args.input, pdf_html)
        render_pdf(pdf_html, pdf_out)
        # Clean up temp file
        if os.path.exists(pdf_html):
            os.remove(pdf_html)

    print("=" * 56)
    print("  Done. Output in", args.output_dir + "/")
    print("=" * 56)


if __name__ == '__main__':
    main()
