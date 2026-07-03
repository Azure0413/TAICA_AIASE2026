# EHPTS 提案計畫書 — Markdown 創作與渲染實作
資訊所 P76134082 陳冠言
  
## 1. 專案簡介

`content.md` 撰寫了一份**智慧老人醫院病患分流預測系統（EHPTS）**的提案計畫書，內容包含：專案摘要、背景分析、分類規則設計、統計分析成果、系統架構、甘特時程圖、預算規劃、風險評估等完整章節。

本專案使用 **兩套渲染工具** 將 Markdown 渲染為多種輸出格式：

| 工具 | 用途 | 輸出格式 |
|------|------|----------|
| **Python-Markdown + wkhtmltopdf** | 自訂 CSS 樣式渲染 | HTML + PDF |
| **Pandoc + XeLaTeX** | 學術文件格式渲染 | HTML + PDF |

選用理由：Python-Markdown 搭配自訂 CSS 可達成高度客製化的網頁排版效果（含 KaTeX 數學公式、Mermaid 互動式圖表）；Pandoc + XeLaTeX 則提供專業的 LaTeX 排版品質與 CJK 字型支援。

## 2. 環境需求

- **Python**：3.10+
- **系統工具**：`pandoc`、`wkhtmltopdf`、`texlive-xetex`（Pandoc PDF 需要）

### Linux / macOS 安裝系統套件

```bash
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y pandoc wkhtmltopdf \
  texlive-xetex texlive-latex-extra texlive-latex-recommended \
  texlive-fonts-recommended fonts-noto-cjk fonts-noto-cjk-extra
```

### Windows 安裝系統套件

1. **Python 3.10+**：從 [python.org](https://www.python.org/downloads/) 安裝，勾選 "Add to PATH"
2. **Pandoc**：從 [pandoc.org](https://pandoc.org/installing.html) 下載 Windows installer (.msi)
3. **wkhtmltopdf**：從 [wkhtmltopdf.org](https://wkhtmltopdf.org/downloads.html) 下載安裝（預設路徑 `C:\Program Files\wkhtmltopdf`，腳本會自動偵測）
4. **MiKTeX**（Pandoc PDF 需要）：從 [miktex.org](https://miktex.org/download) 安裝，首次編譯會自動下載所需套件
5. **CJK 字型**：Windows 內建微軟正黑體（Microsoft JhengHei），腳本已預設支援。如需更好效果，可安裝 [Noto Sans TC](https://fonts.google.com/noto/specimen/Noto+Sans+TC)

> **提示**：安裝 wkhtmltopdf 後若未加入 PATH，`render.py` 會自動搜尋 `C:\Program Files\wkhtmltopdf\bin\` 等常見路徑。

## 3. Python套件安裝步驟

```bash
# Install Python dependencies
pip install -r requirements.txt
```

## 4. 執行渲染

### 方式一：Python Rendering Engine（HTML + PDF）

```bash
python render.py --input content.md --output-dir output
```

- 產生 `output/output.html`（含 KaTeX 數學公式 + Mermaid 互動圖表）
- 產生 `output/output.pdf`（wkhtmltopdf 轉換，含 CJK 支援）

可單獨產出：

```bash
python render.py --html-only   # 僅產出 HTML
python render.py --pdf-only    # 僅產出 PDF
```

### 方式二：Pandoc（HTML）

```bash
pandoc content.md \
  -o output/pandoc-output.html \
  --standalone \
  --lua-filter=mermaid.lua \
  -H mermaid-header.html \
  --mathjax \
  --metadata title="EHPTS 提案計畫書"
```

## 5. 預期輸出

| 檔案 | 格式 | 說明 |
|------|------|------|
| `output/output.html` | HTML | Python 渲染，含互動式 Mermaid 圖表與 KaTeX 公式 |
| `output/output.pdf` | PDF | wkhtmltopdf 產出 A4 |
| `output/pandoc-output.html` | HTML | Pandoc 渲染，含 Mermaid + MathJax |

### Markdown 語法使用清單

本 `content.md` 使用了以下 Markdown 標籤：

- `#` `##` `###` `####` 多層標題
- **粗體**、*斜體*、~~刪除線~~、`行內程式碼`
- 有序清單、無序清單、巢狀清單
- 表格
- 程式碼區塊（Python、YAML、JSON、Bash）
- 引用區塊 `>`
- 水平線 `---`
- 超連結與圖片語法
- 任務清單 `- [x]` / `- [ ]`
- LaTeX 數學公式（行內 `$...$` 與區塊 `$$...$$`）
- Mermaid 圖表（flowchart、graph、gantt、mindmap、quadrantChart、timeline）

## 6. 參考資料

- [Pandoc User's Guide](https://pandoc.org/MANUAL.html)
- [Python-Markdown Documentation](https://python-markdown.github.io/)
- [pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/)
- [KaTeX — Math Typesetting](https://katex.org/)
- [Mermaid — Diagramming Tool](https://mermaid.js.org/)
- [wkhtmltopdf Documentation](https://wkhtmltopdf.org/)
- [WeasyPrint Documentation](https://weasyprint.org/)
- [XeLaTeX + CJK Fonts](https://www.overleaf.com/learn/latex/XeLaTeX)
