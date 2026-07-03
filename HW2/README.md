# handoff — 程式碼交接避雷小幫手

## 1. 專案簡介

### v1.0 功能描述與設計動機

**handoff** 是一個 Python CLI 工具，源自我實習時接手學長專案的痛苦經驗。那個專案大概十幾支 Python 檔案，沒有 README、沒有 docstring、到處都是 `TODO: fix later` 但從來沒 fix 過。最慘的是學長已經離職了，問不到人。我花了快兩週才搞懂程式碼在做什麼，中間踩了無數地雷。

後來我在想：如果當初有一個工具能在學長離職前就幫我列出「這些地方你應該先問清楚」，也許一天就能搞定。這就是 handoff 的原點——它不是一個 linter（已經有 pylint、flake8 了），而是專注在**交接場景**的「避雷」工具。

handoff 掃描 Python 專案，偵測六種常見的交接地雷（TODO 未完成、缺少 docstring、命名不規範、過長函式、過高複雜度、語法錯誤），並根據 import 依賴關係產生建議閱讀順序。最重要的是，每顆地雷都附帶一句「建議問前手的問題」，彙整成一份交接問題清單，讓接手者可以直接拿去跟前手確認。

v1.0 提供五個核心指令：`scan`（掃描）、`report`（查看歷史報告）、`history`（列出掃描紀錄）、`compare`（比較兩次掃描）、`config`（設定管理）。

### 從 v1.0 到 v2.0 的演化摘要

v1.0 上線後收到四個主要痛點回饋：掃描範圍太死板（無法排除 `venv/` 等目錄）、風險分數缺乏分類洞察、`compare` 只能看數字差異無法追蹤個別地雷、交接問題清單無法標記確認狀態。

v2.0 針對這四個痛點進行精準擴充：
1. `scan --exclude` 支援排除規則，可持久化為預設設定
2. 掃描報告新增地雷類型分布統計區塊
3. `compare` 指令細化到個別地雷層級的差異追蹤
4. 新增 `checklist` 指令，支援逐條標記確認狀態並持久化

整個 v2.0 的修改在 v1.0 的五個模組內完成，零新增模組、零破壞性變更。

---

## 2. v1.0 設計決策（Design Decisions）

以下說明我在設計 v1.0 時，**在尚未看到 v2.0 需求的前提下**，基於對「交接工具未來可能的演化方向」的預判所做的架構選擇。每一條我都會說明：（1）我當時預判了什麼可能的需求方向，（2）基於這個預判選了什麼方案，（3）放棄了哪些替代方案、為什麼。

- **選擇 `click` 而非 `argparse` 或 `typer`**

  **預判**：handoff 以「交接」為核心場景，未來很可能需要新增更多子指令（例如「匯出報告」、「標記已讀」、「產生文件」等），而不只是在現有指令上加旗標。因此 CLI 框架的「新增子指令成本」是我最重視的指標。

  **選擇理由**：`click` 的 `@cli.group()` + `@cli.command()` 裝飾器模式讓新增子指令只需寫一個新函式，不需要碰任何 parser 結構。相比之下，`argparse` 的 subparser 機制在指令增多時需要越來越多的樣板程式碼（`add_subparser`、`set_defaults` 等），維護成本隨指令數線性增長。

  **放棄的方案**：我也考慮過 `typer`，它的 type hint 語法更 Pythonic，但 `typer` 底層仍然依賴 `click`，多一層抽象在 debug 時反而增加複雜度。另外 `typer` 的 `--help` 自動生成比較不容易客製化，而我希望 help 訊息能呈現中文說明。最終選了 `click` 作為直接可控的方案。

  **v2.0 驗證**：事後來看，v2.0 新增 `checklist` 指令時，確實只需加一個 `@cli.command()` 裝飾器和一個函式，完全不影響既有的五個指令。如果用 `argparse`，我還需要回去改 `subparser` 的註冊邏輯。

- **將資料存取邏輯獨立為 `storage.py`，並定義 `BaseStorage` 抽象介面**

  **預判**：v1.0 用 JSON 存檔是最快的方案，但我預判隨著掃描記錄增多，JSON 的「全量讀寫」模式一定會遇到效能瓶頸。未來換成 SQLite 或其他資料庫幾乎是必然的。另一個可能方向是雲端同步——如果多人同時使用 handoff 追蹤同一個專案的交接狀態，就需要更有彈性的儲存層。

  **選擇理由**：用 `BaseStorage` 定義抽象介面（`save_scan`、`get_scan`、`list_scans`、`get_latest`、`load_config`、`save_config`），讓上層邏輯（`main.py`）完全不知道底層是 JSON、SQLite 還是 REST API。這是經典的 Repository Pattern，代價是 v1.0 多寫了一個其實用不到的抽象類別。

  **放棄的方案**：最簡單的做法是直接在 `main.py` 裡 `json.load` / `json.dump`，省下一整個模組。但這樣未來換儲存方式時，需要改動 `main.py` 裡每一個讀寫資料的地方，散落在多個指令函式中，風險很高。另一個考慮過的方案是用 `shelve` 模組，它提供 dict-like 的持久化介面，但 `shelve` 的跨平台相容性和人類可讀性都不如 JSON。

  **v2.0 驗證**：v2.0 需要新增 `update_checklist_status()` 方法來做局部更新。因為有 `BaseStorage` 介面，我只需在 `JsonStorage` 上加一個方法，`main.py` 裡的 `checklist` 指令直接呼叫 `store.update_checklist_status()`，完全不需要知道底層是怎麼讀寫的。

- **資料模型使用 `dataclass` + `to_dict()` / `from_dict()` 搭配 `known fields` 過濾**

  **預判**：這是我在 v1.0 花最多時間思考的設計。我的核心擔憂是：v2.0 幾乎一定會在 `ScanResult` 或 `Config` 上新增欄位（不管是什麼需求，只要有新功能就需要存新資料）。如果新版程式無法讀取舊版的 JSON 資料，使用者升級後會丟失所有歷史掃描記錄，這在交接工具的場景下是災難性的——你正在追蹤一個專案的改善進度，升級後歷史全部消失。

  **選擇理由**：`from_dict()` 裡用 `{k: v for k, v in data.items() if k in known}` 做過濾，搭配 dataclass 的預設值機制。這確保了雙向相容：（1）舊 JSON 缺少新欄位 → 自動用預設值填充，不崩潰；（2）新 JSON 有 v1 不認識的欄位 → 自動忽略，不崩潰。

  **放棄的方案**：我考慮過用 `pydantic`，它的 `model_validate` 自帶欄位驗證和預設值處理，功能更強。但 `pydantic` 是外部依賴（v1.0 只想依賴 `click` 一個套件），而且 pydantic v1 和 v2 之間的 API 差異本身就是一個相容性地雷。用標準庫的 `dataclass` 雖然要自己寫序列化邏輯，但完全可控且零外部依賴。另一個考慮的方案是直接用 `dict` 而不是 dataclass，更靈活但沒有型別提示，重構時很容易漏改欄位名稱。

  **v2.0 驗證**：v2.0 在 `ScanResult` 新增了 `kind_distribution`、`checklist_status`、`excluded_patterns` 三個欄位，在 `Config` 新增了 `exclude` 欄位。全部只需加 dataclass field 和預設值，`from_dict()` 完全不用改。用手動建立的 v1 格式 JSON 做測試，讀取正常，新欄位自動填入空值。

- **`ScanResult`、`FileReport`、`Config` 都保留 `metadata: Dict[str, Any]` 欄位**

  **預判**：我無法預測 v2.0 會要求存什麼新資訊，但我可以確定「一定會有某些資訊需要存」。如果每次都得改 dataclass 定義才能存新東西，演化成本太高。`metadata` 作為一個萬用口袋，讓快速原型和實驗性功能有地方放資料，不需要正式改動資料結構。

  **放棄的方案**：不放 `metadata`，等 v2.0 需要時再加。但這樣每次加新欄位都是一個「breaking change moment」——雖然 `known fields` 過濾可以處理，但如果 v2.0 的需求來得急，有一個已經存在的 `metadata` 可以先用來存東西、再決定要不要升級為正式欄位，彈性大很多。

  **v2.0 驗證**：v2.0 的 `excluded_patterns` 在開發早期我確實先放在 `metadata` 裡測試，確認邏輯正確後才提升為正式欄位。`metadata` 扮演了「staging area」的角色。

- **Reporter 層使用 Strategy Pattern（`BaseReporter` → `TextReporter` / `JsonReporter`）**

  **預判**：v1.0 只有 text 和 JSON 兩種輸出格式，但我預判未來可能需要：（1）Markdown 格式，方便貼到 GitHub Issue 或 Slack；（2）HTML 格式，方便嵌入團隊 wiki；（3）某些指令可能需要獨立的格式化邏輯（例如 checklist 的呈現方式可能跟 scan report 完全不同）。

  **選擇理由**：每個 Reporter 子類封裝自己的格式化邏輯，新增格式只需繼承 `BaseReporter` 並註冊到 `_REPORTERS` dict。用工廠函式 `get_reporter(fmt)` 做路由，呼叫端完全不知道具體是哪個 Reporter。

  **放棄的方案**：最直覺的做法是在每個指令函式裡用 `if fmt == "text": ... elif fmt == "json": ...` 分支。v1.0 只有兩種格式時這樣寫更短，但每新增一種格式就要改所有指令函式裡的 if-else，而且格式化邏輯散落在 `main.py` 各處，很難維護。

  **v2.0 驗證**：v2.0 需要新增 `format_checklist()` 方法。我只需在 `TextReporter` 和 `JsonReporter` 各加一個方法，`get_reporter()` 工廠函式和既有的三個 format 方法完全不受影響。

- **Detector 層同樣使用 Strategy Pattern（`BaseDetector` → `TodoDetector` / `CodeSmellDetector`）**

  **預判**：「偵測什麼類型的地雷」是 handoff 最可能被要求擴充的功能方向。例如：安全漏洞偵測（`eval()`、`exec()`、hardcoded secrets）、dead code 偵測、import 循環偵測、型別註解覆蓋率等。如果偵測邏輯全部寫在一個巨大函式裡，新增偵測類型就是在一團義大利麵裡加更多麵條。

  **選擇理由**：每個 Detector 獨立為一個類別，實作 `detect(source, tree, filepath)` 介面。`ScanEngine` 在初始化時接收 Detector 列表，掃描時依序執行。新增偵測器只需寫一個新類別並注入到 Engine，零耦合。

  **放棄的方案**：把所有偵測邏輯寫在 `ScanEngine.scan_file()` 裡，用多個 private method 分類。這樣寫起來更快、沒有抽象類別的 overhead，但一旦要讓使用者選擇「只跑某些偵測器」或「自定義偵測器」，就必須重構。

  **v2.0 驗證**：雖然 v2.0 沒有新增 Detector，但 v2.0 的需求二（類型分布）之所以能用 `kind` 欄位直接做分類統計，正是因為每個 Detector 產出的 Landmine 有清楚的 `kind` 標識，不需要反過來去分析 message 內容。

- **`_calc_risk_and_checklist()` 獨立為函式而非嵌在 `scan` 指令中**

  **預判**：風險計算邏輯是最可能被要求「改公式」的部分。如果嵌在 `scan` 指令函式裡，改計算邏輯時很容易不小心動到 CLI 路由或檔案寫入的程式碼。獨立出來可以隔離變更範圍，也方便未來寫單元測試。

  **放棄的方案**：直接在 `scan()` 函式裡算。v1.0 的 `scan()` 函式其實不長（約 30 行），再多加 15 行計算邏輯也不算離譜。但我預判計算邏輯會越來越複雜（例如加權公式可能會根據專案規模動態調整），早點拆出來比較安全。

  **v2.0 驗證**：v2.0 在這個函式中加入 `kind_distribution` 統計，把回傳值從 `(risk_score, checklist)` 擴充為 `(risk_score, checklist, kind_dist)`。修改範圍僅限於這一個函式，`scan` 指令只需多接一個回傳值。

- **`ScanEngine._collect()` 的目錄過濾邏輯預留了擴充點**

  **預判**：v1.0 已經在 `_collect()` 中過濾了 `.` 開頭的隱藏目錄和 `__pycache__`。我當時就在想：使用者遲早會抱怨「為什麼 `venv/` 也被掃進去」。但 v1.0 的 scope 不適合處理這個問題（需要設計排除規則的語法和持久化機制），所以我只做了最基本的過濾，但把過濾邏輯集中在 `_collect()` 一個地方，未來擴充時只需改這個方法。

  **放棄的方案**：在 v1.0 就實作完整的 `--exclude` 功能。但這會讓 v1.0 的 scope 膨脹，而且我還不確定排除規則的最佳 UX（用 glob？regex？`.gitignore` 語法？），貿然實作可能做出一個難用的介面，v2.0 又得重做。

  **v2.0 驗證**：v2.0 的排除規則確實只改了 `_collect()` 這個方法，加了大約 20 行 `fnmatch` 匹配邏輯。如果 v1.0 的過濾邏輯散落在多處，這個修改就會痛苦得多。

- **指令介面使用「位置參數 + 可選旗標」的設計模式**

  **預判**：`scan PATH` 的 `PATH` 是位置參數（必填），`--format`、`--output` 是可選旗標。這種設計讓未來新增旗標時，只要是可選的，就不會破壞既有的調用方式。我特別避免把任何可能擴充的選項做成位置參數（例如沒有設計成 `scan PATH FORMAT`），因為位置參數的順序一旦定了就不能改。

  **v2.0 驗證**：`--exclude` 作為可選旗標加入，不影響任何現有的 `scan` 調用方式。如果 v1.0 的 format 是位置參數而非旗標，v2.0 想在 format 和 path 之間插入 exclude 就會非常尷尬。

---

## 3. v2.0 實作說明

### 閱讀與理解 v2.0 需求的過程

收到 `requirements_v2.md` 後，我做了以下幾件事：

1. **第一遍通讀，標記需求類型**：我把四個需求分成「修改既有模組」（需求一到三）和「全新功能」（需求四），這個分類影響了我的實作順序——先改既有模組確保不破壞 v1 功能，最後才加新指令。

2. **第二遍精讀，列出「模糊地帶」**：PRD 刻意留了幾個設計空間讓學生自行決定。我標記出來的模糊地帶包括：
   - 需求一：「臨時指定的 `--exclude` 與設定檔裡的預設排除清單，兩者的合併邏輯由學生自行決定」——要做聯集還是覆蓋？
   - 需求三：「同一顆地雷的判斷標準由學生自行定義」——用什麼當 identity key？
   - 需求四：「確認狀態的儲存方式由學生自行設計」——附在 ScanResult 上還是另開檔案？

3. **第三遍對照程式碼，畫影響範圍圖**：我把每個需求會動到哪些模組、哪些函式寫出來，這幫助我判斷有沒有需求之間的衝突或依賴。結果發現需求二（分布統計）和需求一（排除規則）都會改 `main.py` 的 `scan` 指令，需要注意合併時不要互相覆蓋。

### 需求到 SDD 的映射

| 需求 | 影響模組 | SDD 更新範圍 |
|---|---|---|
| 需求一：排除規則 | `main.py`、`analyzers.py`、`models.py` | CLI 介面規格（新增 `--exclude`）、Config 資料模型（新增 `exclude`）、模組職責表、新增§11 排除規則設計 |
| 需求二：類型分布 | `main.py`、`reporters.py`、`models.py` | ScanResult 資料模型（新增 `kind_distribution`）、§7 計分邏輯章節擴充、Reporter 職責 |
| 需求三：地雷差異 | `reporters.py` | 新增§10 地雷差異追蹤設計，說明比對演算法、identity key 選擇與邊界情況 |
| 需求四：checklist | `main.py`、`reporters.py`、`storage.py`、`models.py` | CLI 介面規格（新增 `checklist` 指令）、ScanResult 資料模型（新增 `checklist_status`）、§9 儲存格式章節、錯誤處理規格 |

### 實作順序與踩過的坑

我選擇的實作順序是：models → analyzers → storage → reporters → main。原因是先改底層資料結構，再改中間邏輯，最後改上層入口，這樣每改完一層就可以測試，避免多層同時改動時 debug 困難。

**踩坑 1：`Config.from_dict()` 的向下相容問題**

v1.0 的 `Config.from_dict()` 寫的是 `return cls(**data)`，直接把整個 dict 展開傳入建構式。但 v2.0 新增了 `exclude` 欄位，如果舊的 config.json 沒有這個 key，`cls(**data)` 不會出錯（因為 `exclude` 有預設值）。可是如果舊 config.json 裡多了什麼 v2 不認識的 key（例如手動編輯加的），`cls(**data)` 就會爆 `TypeError: unexpected keyword argument`。

所以我把 `Config.from_dict()` 也改成跟 `ScanResult.from_dict()` 一樣的 `known fields` 過濾模式。這是 v1.0 的一個小疏忽——`ScanResult` 和 `FileReport` 都有過濾，但 `Config` 沒有，因為 v1.0 時 Config 的欄位很簡單，沒想到會出問題。

**踩坑 2：`_calc_risk_and_checklist` 回傳值擴充的連鎖反應**

原本打算在這個函式裡把 `kind_distribution` 塞進 `ScanResult` 物件，但後來發現這個函式是在建立 `ScanResult` 之前呼叫的——它算出 `risk_score` 和 `checklist`，這兩個值才會被用來建構 `ScanResult`。所以 `kind_dist` 必須跟 `risk_score` 一樣作為回傳值傳出去。

我考慮過把函式改成直接修改一個已建立的 `ScanResult` 物件（pass-by-reference），但這會改變函式的語義（從「計算並回傳結果」變成「修改傳入物件的副作用」），不利閱讀。最終選擇增加回傳值，代價是 `scan` 指令裡的解包從 `risk_score, checklist = ...` 變成 `risk_score, checklist, kind_dist = ...`，影響範圍極小。

**踩坑 3：checklist 的 index 要不要從 0 開始**

PRD 寫的是 `--resolve <item_index>`，沒有明確說 index 從 0 還是 1 開始。我一開始用 0-based（程式設計師直覺），但自己測試時覺得 `checklist --id 1 --resolve 0` 看起來很怪——使用者看到的清單是從 1 開始編號的，卻要輸入 0 來操作第一項。最後改成 1-based，內部轉換為 0-based。

### 非顯而易見的實作選擇（含被放棄的替代方案）

**1. 地雷身份比對：選擇 `(kind, basename, message)` 三元組**

這是 v2.0 最核心的設計決策，我前後考慮了四種方案：

| 方案 | 優點 | 缺點 |
|---|---|---|
| `(kind, filepath, line)` | 簡單，精確到行 | 行號在編輯後極易偏移，加一行空行就變了 |
| `(kind, filepath, message)` | 不受行號影響 | filepath 在目錄重構後會改變 |
| `(kind, basename, message)` ✅ | 容忍行號偏移和目錄搬移 | 同名不同目錄的檔案會誤判為同一顆 |
| 內容指紋（hash 周圍程式碼） | 最精確，抗重構 | 實作複雜度高，需要存儲原始碼片段 |

我選方案三的關鍵推理是：handoff 的使用場景是「掃描 → 修復 → 再掃描 → 比較」，在這個週期內，檔案被搬到完全不同目錄的機率很低，但修改程式碼導致行號偏移幾乎是必然的。方案三在最常見的情境下準確度最高。

**已知限制**：如果專案有 `src/utils.py` 和 `tests/utils.py` 兩個同名檔案，各有一個缺 docstring 的 `parse()` 函式，它們的 identity key 會相同 `(missing_docstring, utils.py, "Function 'parse' 沒有 docstring")`，被誤判為同一顆地雷。我在 SDD §10 中明確記載了這個限制。

**2. checklist_status 的儲存位置：選擇附加在 ScanResult 上**

考慮過三種方案：

| 方案 | 優點 | 缺點 |
|---|---|---|
| 附加在 ScanResult 上 ✅ | 語義一致，刪除掃描記錄時自動清除 | 更新一條 checklist 需重寫整個 scans.json |
| 另開 `.handoff/checklist_{id}.json` | 局部更新效能好 | 檔案同步問題（刪掃描記錄忘刪 checklist）|
| 統一放 `.handoff/checklists.json` | 單一檔案好管理 | 與 scans.json 分離，需要維護跨檔案一致性 |

我選方案一的理由是 **data locality**——checklist_status 和 question_checklist 是一一對應的，放在同一筆 ScanResult 記錄裡最符合資料的語義關係。方案二效能最好，但引入了「孤兒檔案」問題（scans.json 裡的記錄被刪掉了，checklist 檔案還在）。在 handoff 的使用規模下（通常不超過數百筆掃描記錄），重寫 scans.json 的效能成本可忽略。

**3. 排除規則的匹配引擎：選擇 `fnmatch` 而非 regex 或 `.gitignore` 語法**

| 方案 | 語法範例 | 優點 | 缺點 |
|---|---|---|---|
| `fnmatch` ✅ | `test_*`, `*.pyc` | 語法直覺，標準庫 | 不支援路徑分隔符匹配 |
| `re`（正規表達式） | `test_.*\.py$` | 最強大 | 對非技術使用者不友善 |
| `pathspec`（.gitignore 語法） | `venv/`, `*.pyc` | 使用者最熟悉 | 外部依賴（pathspec） |

PRD 原文寫「支援簡單的萬用字元匹配」，`fnmatch` 完全符合這個要求。我認真考慮過 `pathspec`（解析 `.gitignore` 語法的 library），因為幾乎所有開發者都熟悉 `.gitignore`。但 `pathspec` 是外部依賴，而 v1.0 的設計原則是「只依賴 `click`」，我不想為了一個小功能打破這個原則。如果未來需求更複雜，再引入 `pathspec` 也不遲。

**已知限制**：`fnmatch` 是逐層匹配目錄名和檔名的，不支援 `src/utils` 這種帶路徑分隔符的模式。這是一個刻意的取捨，記錄在 SDD §11 中。

**4. 排除規則的合併策略：選擇「聯集去重」而非「CLI 覆蓋」**

我考慮了兩種策略：

- **策略 A：聯集去重（選用）**：`config.exclude` 和 `--exclude` 的結果取聯集。使用者可以在 config 裡設定「永遠排除 venv」，同時臨時加 `--exclude tests`，兩者並存。
- **策略 B：CLI 覆蓋**：如果指定了 `--exclude`，則完全忽略 `config.exclude`。語義更明確（「我指定了就用我指定的」），但使用者想臨時加一個排除項時，得把 config 裡已有的也全部重新輸入一遍。

我選策略 A 是因為在交接場景中，「永遠排除 venv 和 __pycache__」是一種很自然的預設，使用者不應該因為臨時想排除 tests 就失去這些預設。報告開頭會列出「Excluded patterns: venv, tests」，讓使用者清楚本次實際排除了什麼，維持透明度。

**5. `_calc_risk_and_checklist` 的回傳值擴充方式**

原本回傳 `(risk_score, checklist)`，v2.0 需要加 `kind_distribution`。考慮了三種方式：

- **方案 A：增加回傳值（選用）**：改為 `(risk_score, checklist, kind_dist)`。最小修改，但 tuple 回傳超過 3 個值就開始不好讀了。
- **方案 B：回傳 dataclass / namedtuple**：定義一個 `RiskResult` 資料結構包裝回傳值。更結構化，但為了一個內部函式多一個類別有點 over-engineering。
- **方案 C：直接修改 `ScanResult` 物件**：在函式內直接把 `kind_dist` 寫入已建立的 `ScanResult`。但如前所述，這會改變函式語義。

目前選方案 A，因為 3 個回傳值還在可讀範圍內。如果 v3.0 需要加更多東西，會考慮升級為方案 B。

---

## 4. 向下相容性實作細節

### 資料層向下相容

v2.0 的 `ScanResult` 新增了三個欄位（`kind_distribution`、`checklist_status`、`excluded_patterns`），全部都有 dataclass 預設值（空 dict、空 list、空 list）。向下相容的具體機制：

**場景一：v2 程式讀取 v1 的 scans.json**

`ScanResult.from_dict()` 使用 `known fields` 過濾，舊記錄缺少的 v2 欄位自動使用 dataclass 預設值。但 `checklist_status` 需要額外處理：如果 `checklist_status` 為空但 `question_checklist` 有值，代表這是一筆 v1 的記錄，需要自動初始化為 `[False] * len(question_checklist)`（全部未確認），這樣使用者對舊記錄執行 `checklist --id <舊ID>` 時能正常顯示。

我特別在 `from_dict()` 裡加了這段邏輯，而不是在 `checklist` 指令裡處理，因為不管是 `checklist`、`report` 還是 `compare`，只要讀到舊記錄就應該有一致的行為。

**場景二：v2 程式讀取 v1 的 config.json**

v1 的 `Config.from_dict()` 原本是 `return cls(**data)`，直接展開 dict。v2 改成了跟其他 dataclass 一樣的 `known fields` 過濾模式，確保：
- 舊 config 沒有 `exclude` key → 自動用預設值（空 list）
- 舊 config 裡如果有被手動加入的未知 key → 安全忽略，不會 crash

**場景三：`from_dict` 遇到意料之外的資料格式**

我手動測試了幾種邊界情況：
- v1 記錄中 `metadata` 放了自定義資料 → ✅ 正常讀取（`metadata` 是 v1 就有的欄位）
- v1 記錄中缺少 `metadata` key → ✅ 自動使用空 dict 預設值
- JSON 中有拼錯的 key（例如 `"knd_distribution"`）→ ✅ 被 `known fields` 過濾掉，不影響其他欄位

### CLI 層向下相容

所有 v1.0 的 CLI 行為完全不受 v2.0 影響：

- `scan PATH`：不帶 `--exclude` 時，排除規則為空（如果 config 也沒設 exclude），行為與 v1 完全一致
- `scan PATH --format json`：JSON 輸出多了 `kind_distribution`、`checklist_status`、`excluded_patterns` 三個 key，但這是「新增」而非「修改」，不影響只讀取 v1 欄位的消費端
- `compare ID1 ID2`：在原有的整體比較表格（Risk Score、Landmines、Files）之後附加地雷差異區塊，原有表格格式和數字完全不變
- `config --show`：在原有的 thresholds 列表之後顯示 exclude 清單。如果 exclude 為空，顯示 `exclude: []`
- `--version`：仍然輸出 `1.0.0`，沒有改版本號

### 不需要 Adapter Pattern 或 Workaround

由於 v1.0 的架構設計已經預留了足夠的擴充空間（Strategy Pattern、`known fields` 過濾、`metadata` 欄位、集中式的 `_collect()` 過濾邏輯），v2.0 的所有需求都能通過「新增方法/欄位」的方式完成，不需要引入額外的適配層或 workaround。這一點我認為是 v1.0 設計中最成功的部分。

唯一接近 workaround 的地方是 `Config.from_dict()` 的修改——把 v1 的 `cls(**data)` 改成 `known fields` 過濾模式。嚴格來說這是修了 v1.0 的一個潛在 bug，而不是 v2.0 的 workaround。

---

## 5. 架構演化比較

| 面向 | v1.0 | v2.0 | 變更說明 |
|---|---|---|---|
| 模組數量 | 5（main, models, analyzers, reporters, storage） | 5（相同） | 無新增模組 |
| CLI Library | click | click（相同） | 無變更 |
| 儲存層 | JSON 檔案 | JSON 檔案（相同） | 無變更，新增 `update_checklist_status` 方法 |
| 指令數量 | 5（scan, report, history, compare, config） | 6（+checklist） | 新增 1 個指令 |
| `models.py` | 4 dataclass | 4 dataclass + 新欄位 | ScanResult +3 欄位, Config +1 欄位 |
| `analyzers.py` | ScanEngine._collect() 無排除 | ScanEngine._collect() 支援排除 | 新增 ~20 行排除邏輯 |
| `reporters.py` | format_scan, format_history, format_comparison | +format_checklist, +_diff_landmines | 新增 2 個方法 + 1 個輔助函式 |
| `storage.py` | 6 個方法 | 7 個方法（+update_checklist_status） | 新增 1 個方法 |
| `main.py` | 5 個指令函式 + 1 輔助函式 | 6 個指令函式 + 1 輔助函式（回傳值擴充） | 新增 1 個指令函式，修改 1 個輔助函式的回傳值 |

### 每個模組的 diff 量化

| 模組 | v1 行數 | v2 行數 | 新增行 | 刪除行 | 淨增 | 說明 |
|---|---|---|---|---|---|---|
| `models.py` | 77 | 87 | +11 | -1 | +10 | 新增 4 個欄位 + Config.from_dict 改為 known fields |
| `storage.py` | 58 | 80 | +24 | 0 | +22 | 新增 update_checklist_status |
| `analyzers.py` | 166 | 189 | +30 | -5 | +23 | _collect 加排除 + scan_path 簽名擴充 |
| `main.py` | 121 | 185 | +78 | -12 | +64 | 新增 checklist 指令 + exclude 合併邏輯 |
| `reporters.py` | 78 | 179 | +114 | -3 | +101 | format_checklist + _diff_landmines + 分布區塊 |
| **合計** | **500** | **720** | **+257** | **-21** | **+220** | 4 項需求，淨增 220 行 |

### 架構差異視覺化

```
v1.0                              v2.0
─────────                         ─────────
main.py (scan/report/             main.py (scan/report/
  history/compare/config)           history/compare/config/
                                    +checklist)           ← 新增 1 指令

models.py (Landmine/              models.py (Landmine/
  FileReport/ScanResult/Config)     FileReport/ScanResult*/Config*)
                                                          ← *新增欄位

analyzers.py (ScanEngine/         analyzers.py (ScanEngine*/
  TodoDetector/CodeSmellDetector/   TodoDetector/CodeSmellDetector/
  DependencyMapper)                 DependencyMapper)
                                                          ← *_collect 加排除

reporters.py (TextReporter/       reporters.py (TextReporter*/
  JsonReporter)                     JsonReporter*/
                                    +_diff_landmines)     ← *新增方法

storage.py (JsonStorage)          storage.py (JsonStorage*)
                                                          ← *新增 1 方法
```

---

## 6. 環境需求與執行方式

### 環境需求
- Python 3.10+
- 依賴套件：`click>=8.0`（v1.0 和 v2.0 相同，無新增依賴）

### v1.0

```bash
cd v1/
pip install -r requirements.txt
python main.py --help
python main.py scan .              # 掃描當前目錄
python main.py scan main.py       # 掃描單一檔案
```

### v2.0

```bash
cd v2/
pip install -r requirements.txt
python main.py --help

# 基本掃描（與 v1.0 相同）
python main.py scan .

# 帶排除規則的掃描
python main.py scan ./src --exclude venv --exclude tests

# 設定預設排除清單
python main.py config --set exclude=venv
python main.py config --show

# 地雷差異追蹤
python main.py compare 1 2

# 交接問題確認追蹤
python main.py checklist --id 1
python main.py checklist --id 1 --resolve 2
python main.py checklist --id 1 --reset 2

# JSON 格式輸出
python main.py scan . --format json
python main.py checklist --id 1 --format json
```

---

## 7. 已知限制與未來改進方向

### 已知限制

1. **地雷差異比對的精確度**：使用 `(kind, basename, message)` 作為身份鍵，無法處理同名但位於不同目錄的檔案中的相同問題被誤判為同一顆地雷的情況。例如 `src/utils.py` 和 `tests/utils.py` 各有一個缺 docstring 的 `parse()` 函式，會被判定為「同一顆地雷」。

2. **checklist 不支援多人同步**：採用 last-write-wins 策略，兩人同時執行 `--resolve` 時後者會覆蓋前者的修改。這是因為 `update_checklist_status()` 的實作是「讀取 → 修改 → 全量寫回」，沒有鎖機制。在 handoff 的主要場景（一對一交接對帳）下，這個限制影響不大。

3. **排除規則不支援路徑前綴匹配**：`--exclude src/utils` 這種帶路徑分隔符的模式無法正常運作，因為 `fnmatch` 是逐層匹配目錄名和檔名的，不是匹配完整路徑。目前只支援目錄名或檔名層級的匹配（如 `venv`、`test_*`）。

4. **效能瓶頸**：每次更新 checklist 需要重寫整個 `scans.json`，當掃描記錄非常多時可能變慢。根據我的實測，1000 筆掃描記錄的 JSON 大約 5MB，重寫一次約 50ms，在 CLI 場景下使用者感知不到，但不適合高頻操作。

5. **compare 的 diff 不支援跨版本的結構變動**：如果兩次掃描之間大幅重構了程式碼（例如把 `utils.py` 拆成 `string_utils.py` 和 `file_utils.py`），diff 會產生大量「假的新增/消失」，因為 basename 變了。

### v3.0 改進方向

1. **儲存層升級為 SQLite**：解決效能瓶頸和多人同步問題。`BaseStorage` 抽象類別已經預留了這個擴充點，只需實作一個 `SqliteStorage` 類別。SQLite 的行級鎖定可以避免 last-write-wins 問題，WAL 模式還能支援讀寫並行。

2. **差異比對改用內容指紋**：對每顆地雷的周圍程式碼（例如上下 3 行）取 hash，作為更精確的身份識別。這樣即使檔案被重命名，只要程式碼內容沒變，仍然能正確追蹤同一顆地雷。代價是 `ScanResult` 需要額外儲存每顆地雷的 context hash。

3. **支援自定義 Detector 插件**：讓使用者可以編寫自己的偵測器，透過設定檔指定模組路徑載入。`BaseDetector` 的 Strategy Pattern 已經預留了這個擴充點，只需在 `ScanEngine.__init__` 中加上動態載入邏輯。

4. **TUI 互動介面**：使用 `rich` 或 `textual` 提供即時的掃描進度顯示和互動式 checklist 操作（用鍵盤上下選取、空白鍵 toggle 確認狀態）。這會需要把 Reporter 層擴充為支援互動式輸出，但 Strategy Pattern 讓這個擴充只需新增一個 `TuiReporter` 類別。

5. **排除規則升級為 `.gitignore` 語法**：引入 `pathspec` library，支援完整的 `.gitignore` 語法（包括路徑前綴、否定規則 `!`）。同時可以自動讀取專案根目錄的 `.gitignore` 作為預設排除清單。
