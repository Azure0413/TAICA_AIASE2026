## 1. Skill 簡介

`open-semver-Azure0413` 收到同一個 Python 模組的兩個版本（`old_code` / `new_code`），用 AST 比對其
**公開 API surface**，**確定性地**判定該升 `major` / `minor` / `patch`，並產生 changelog 草稿。

## 2. Skill 名稱與目錄

- Skill 名稱：`open-semver-Azure0413`
- 路徑：`skills/open-semver-Azure0413/`
- 主要受評 skill path（合規 gate 用）：`skills/open-semver-Azure0413/`
- 確定性 harness：
  - `scripts/_semver.py` — 共用核心：AST 抽公開 API + 依固定規則判 bump
  - `scripts/advise.py` — **one-shot 入口**：吃原始輸入 → 算 bump + 自動產 changelog → 直接輸出最終契約
    （LLM 只需「轉發輸入、轉述輸出」，不自行判斷，故跨模型極穩）
  - `scripts/classify.py` — 選用：只回 `{bump, breaking, additive}` 原始證據
  - `scripts/evaluate.py` — **grader-facing 確定性評分器**：重算權威 bump 並比對 skill 預測
  - `scripts/run.py` — 純契約封裝（手動組裝 payload 時用）
- 本地自測 scenario：`dev_set/open/semver_001.json` … `semver_003.json`（含 held-out perturbations）

## 3. 呼叫方式

**Slash command:**

```
/open-semver-Azure0413
```

**輸入 JSON 範例：**

```json
{
  "task_id": "semver_001",
  "old_code": "def add(a, b):\n    return a + b\n",
  "new_code": "def add(a, b, c=0):\n    return a + b + c\n"
}
```

- `old_code` (string，必填)：舊版本的完整 Python 原始碼。
- `new_code` (string，必填)：新版本的完整 Python 原始碼。
- `task_id` (string，選填)：若提供，輸出必須回填相同值。

**完整評分環境呼叫（與 grader 同路徑，含 `-Q`，course 2026-06 file-based 更新）：**

```bash
hermes chat --toolsets skills,terminal --yolo -Q -q '/open-semver-Azure0413 {"task_id":"semver_001","old_code":"def add(a, b):\n    return a + b\n","new_code":"def add(a, b, c=0):\n    return a + b + c\n"}'
```

> `terminal` toolset 為**必要**:本 skill 的唯一一步就是讓 agent 用 terminal 執行 `scripts/advise.py`
> (確定性算出 bump + changelog,並**把最終契約寫入結果檔**)。`--yolo` 讓評分環境全自動放行該工具呼叫,
> `-Q` 與 file-based 輸出皆依課程 2026-06 公告之正式評分指令。

**輸出（寫入結果檔的 JSON object,此即輸出 schema）範例：**

```json
{
  "task_id": "semver_001",
  "bump": "minor",
  "changelog": "### Added\n- add() gained an optional `c` parameter (backward compatible).",
  "rationale": "An existing public function gained a new optional parameter; no breaking change.",
  "confidence": 1.0
}
```

Schema（必填欄位）：`task_id` (string)、`bump` (string enum:`major`/`minor`/`patch`)、`changelog`
(string)、`rationale` (string)、`confidence` (number, 0.0–1.0)。**輸出方式為 file-based**:
`scripts/advise.py` 把上述 JSON object **原子寫入結果檔**(路徑取自環境變數 `AIASE_RESULT_PATH`,
未設定則 `./aiase_result.json`);評分器**讀該檔**評分,不再從對話 stdout 擷取 fenced JSON。沒有結果檔 = 該題 0 分。

### 三個可直接執行的 public scenario（照貼即可跑，分別涵蓋 minor / major / patch）

以下三條為完整、可直接複製執行的範例（與 `dev_set/open/semver_00{1,2,3}.json` 同一份輸入；payload 內皆
無單引號，故單引號 shell argv 安全）。期望結果分別為 `minor`、`major`、`patch`：

```bash
# 範例 1 — semver_001 → minor（area() 新增選填參數 unit + 新增公開函式 perimeter()）
hermes chat --toolsets skills,terminal --yolo -Q -q '/open-semver-Azure0413 {"task_id":"semver_001","old_code":"import math\n\ndef area(r):\n    return math.pi * r * r\n","new_code":"import math\n\ndef area(r, unit=\"cm\"):\n    a = math.pi * r * r\n    return a\n\ndef perimeter(r):\n    return 2 * math.pi * r\n"}'

# 範例 2 — semver_002 → major（Client.__init__ 把公開參數 port 改名 address，並移除公開函式 ping()）
hermes chat --toolsets skills,terminal --yolo -Q -q '/open-semver-Azure0413 {"task_id":"semver_002","old_code":"class Client:\n    def __init__(self, host, port):\n        self.host = host\n        self.port = port\n    def send(self, data):\n        return len(data)\n\ndef ping(host):\n    return True\n","new_code":"class Client:\n    def __init__(self, host, address):\n        self.host = host\n        self.address = address\n    def send(self, data):\n        return len(data)\n"}'

# 範例 3 — semver_003 → patch（抽出私有 _accumulate() 的純內部重構，公開簽名不變）
hermes chat --toolsets skills,terminal --yolo -Q -q '/open-semver-Azure0413 {"task_id":"semver_003","old_code":"def total(nums):\n    s = 0\n    for n in nums:\n        s = s + n\n    return s\n","new_code":"def _accumulate(nums):\n    return sum(nums)\n\ndef total(nums):\n    return _accumulate(nums)\n"}'
```

每條執行後,`advise.py` 會把契約 JSON 寫入結果檔(`$AIASE_RESULT_PATH`,否則 `./aiase_result.json`),
其中 `bump` 分別為 `minor` / `major` / `patch`。grader 另以每個 scenario 檔的 held-out `perturbations`
(同類別、不同 diff)重評,驗證並非背特定 diff（見 §4）。

## 4. 自定 Verifiable Scenario

**Scenarios（3 個公開可執行範例，完整 `old_code`/`new_code` 存於 `dev_set/open/`）：**

- **Scenario 1 — `semver_001`（→ minor）**：`area()` 新增選填參數 `unit` + 新增公開函式 `perimeter()`。向後相容的新增 → minor。
- **Scenario 2 — `semver_002`（→ major）**：`Client.__init__` 把公開參數 `port` 改名為 `address`，並移除公開函式 `ping()`。破壞既有呼叫 → major。
- **Scenario 3 — `semver_003`（→ patch）**：把迴圈抽成私有 `_accumulate()` 的純內部重構，公開簽名不變 → patch。

每個 scenario 檔另含 `perturbations`：**同一升級類別、但不同 diff** 的 held-out 變體（**不**餵給 skill），
供 grader 驗證 skill 是否真的依規則判斷,而非背特定 diff。

**Metric（可程式化，由 `scripts/evaluate.py` 計算）：**

- **主要（不可 gameable）**：`bump_correct` —— evaluator 用 `_semver.py` 的 AST 規則**重新計算**權威 bump，
  與 skill 輸出的 `bump` 做 exact 字串比對；對 ⇒ accuracy 1.0，錯 ⇒ 0.0。
- **次要**：`changelog_coverage` —— 變更到的每個公開符號名稱是否出現在 changelog 文字裡（無變更時為 1.0）。
  僅作品質參考，scenario 通過與否由 `bump_correct` 決定。

bump 規則寫死在 `_semver.py`（公開符號集合、簽名相容性、major/minor/patch 判定），SKILL.md「## SemVer rule」
與本節完全一致 —— 無 hidden assumptions（規格 §共通原則 #5）。

**為何不可 gameable：**

1. **答案是 evaluator 算的、不是 skill 給的**：bump 由 AST 在 grader 端重算，skill 報什麼不影響「正確答案」。
2. **Held-out perturbation**：grader 用 `perturbations`（及等價變體：換符號名、改參數順序、加無關內部改動）餵入；
   只對固定 task_id 硬編答案者必失敗。
3. **規則是死的、有限的**：SemVer 對「公開 API 變動 → 版本級別」是確定性映射,逐條可核對,無模糊空間。
4. **亂猜期望值低**：三類各 1/3,且實際分布不均,猜不會穩定得分；唯有真的做 AST 比對才能在 held-out 上達 1.0。
5. **關鍵字/固定輸出/人工主觀無法取分**：唯一被計分的是「bump 在未見 diff 上是否等於 AST 算出的權威值」。

## 5. 預期失敗模式

- 失敗 1（MAST (3) 驗證與品質 — 直覺凌駕規則）：LLM 把「新增選填參數」直覺判成 patch、或把「改參數名」判成 minor。
  觸發點：未照 `classify.py` 的結果。處理：Procedure 強制「**bump 一律取自 `classify.py`**」,SKILL.md Pitfalls 點名
  這兩個反直覺案例（optional param→minor、rename→major）。
- 失敗 2（MAST (1) 規格與角色 — 語法/邊界）：`old_code` 或 `new_code` 有 syntax error,AST 無法 parse。
  觸發點：截斷或非法輸入。處理：`_semver.public_api` 捕捉 `SyntaxError`,`classify.py` 回 `bump=""` + `error`,
  `advise.py` 此時降低 confidence、不亂猜,並仍**寫出合法契約 JSON 結果檔**（不噴 traceback）。
- 失敗 3（MAST (1) 規格與角色 — JSON-argv 跳脫）：把含引號的原始碼塞進 JSON argv 時跳脫錯誤。
  觸發點：弱模型對 `"`/`\n` 跳脫不穩。處理：SKILL.md 建議用 stdin quoted-heredoc 傳 payload(零跳脫);即便壞掉,
  `advise.py` 也只會退化成 `bump=""` 的合法契約**結果檔**,不會破壞評分器讀檔。

## 6. 互動對象

本 skill 為**單一 skill、無跨 skill 協作、無 subagent**。互動對象是自帶的確定性 harness
（`scripts/advise.py` ↔ Hermes 內建 terminal 工具）：Hermes 載入 skill → LLM 用 terminal 把使用者輸入
原樣轉發給 `advise.py` → `advise.py` 確定性算出 bump + changelog 並**把最終契約原子寫入結果檔**
（`$AIASE_RESULT_PATH`，否則 `./aiase_result.json`）。互動 log 即「forward input → advise 寫結果檔」
這條極短資料流,可由 Hermes 執行紀錄(terminal 呼叫 + `written ok` 行)獨立驗證,不依賴任何外部或他人 skill。
（不需多步自主推理,故不使用 subagent;LLM 不需轉述輸出,評分器只讀結果檔。）

## 7. Token Budget 估算

input 為兩段小型 Python 原始碼 + 短描述,output 為一個 bump 字串 + 簡短 changelog；`classify.py` 的回傳
是精簡的符號變更清單。均遠低於 50k tokens/scenario。

| Scenario | 預估 input tokens | 預估 output tokens | 預估 total |
|---|---:|---:|---:|
| Scenario 1 (minor) | ~500 | ~300 | ~800 |
| Scenario 2 (major) | ~600 | ~350 | ~950 |
| Scenario 3 (patch) | ~450 | ~250 | ~700 |

（即使較大的真實模組 diff,單一 scenario 亦預估 < 8k tokens,遠低於 50k 門檻。）
