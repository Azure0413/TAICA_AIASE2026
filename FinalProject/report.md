# 期末報告 — AIASE 2026 Final Project

> 學生:`Azure0413`(GitHub) / 聯絡:p76134082@gs.ncku.edu.tw
> 單人組(非兩人組)。Pairwise **兩個 skill(code-author + bug-hunter)皆實作並繳交**;依課程 2026-06
> 公告(Q3),`PAIRWISE_ROLE.md` 以 `roles:` 清單**同時宣告兩個角色**,評分時由課程隨機抽一個角色與他人配對
> (檔尾另保留一組未縮排 `role:`/`skill_path:` 以相容舊版自動評分器)。
>
> **執行指令(2026-06 file-based 更新)**:本專案所有自測與評分皆採課程 2026-06 最新公告之正式指令
> `hermes chat --toolsets skills,terminal --yolo -Q -q '/<skill> {json}'`(`terminal` toolset 為跑
> `scripts/` 確定性 helper 所必需;`--yolo` 全自動放行工具呼叫;**`-Q`** 防止 hermes 美化最終訊息把
> ``` ``` ``` 標記吃掉)。**輸出改為 file-based**:每個 skill 的 `scripts/run.py`(Open Track 為 `advise.py`)
> 把最終結果**原子寫入結果檔**(路徑取自環境變數 `AIASE_RESULT_PATH`,未設定則 `./aiase_result.json`),
> 評分器**讀該檔**評分,不再從對話 stdout 擷取 JSON;沒有結果檔 = 該題 0 分。`run_dev.py` 已同步:設好
> `AIASE_RESULT_PATH`、用含 `-Q` 的正式指令呼叫、再以 `aiase_contract.read_result` 讀檔比對(`aiase_contract.py`
> 為評分器與本地共用的同一份比對核心,置於 repo 根目錄)。單次 skill 呼叫 wall-clock 上限 120s,各 skill 的
> LLM 步驟極短(Open Track 僅「一次 `advise.py` 寫檔」),遠低於上限。

> **本報告中的所有 log 證據如何取得**:課程評分用的 Hermes Agent ↔ LiteLLM Gateway 我在開發環境
> 無法重現,因此我自行寫了一個**忠實但刻意較弱的 mini-agent proxy**(ReAct 迴圈:把 `SKILL.md` 與
> payload 餵給模型,模型以 `EXEC python scripts/...` 呼叫我的確定性 helper,我回灌 stdout;最終結果
> 由 helper **寫入結果檔**,proxy 讀檔判定 —— 與 file-based 評分路徑一致)。它跑在**與正式計分模型池相同的
> 兩顆模型**上 —— 地端 `gemma4`(Ollama,`gemma4:latest`)與 `gemini-2.5-flash`(API)。由於此 proxy 的
> system prompt 與工具能力都比真實 Hermes 弱,**這裡的 pass rate 是真實評分環境的保守下界**。下文標示
> `[gemma4]` / `[gemini-2.5-flash]` 之數字與 transcript 皆由此 proxy 真實跑出,非杜撰;但最終分數仍以課程
> Hermes 上的 log 為準。(早期失敗 log 取自舊的 stdout-擷取 proxy;成因與修正在 file-based 下完全相同,
> 僅「最終如何把答案交給評分器」由印 JSON 改為寫結果檔。)

---

## 1. 設計決策

貫穿三個 Track 的同一原則:**deterministic shell wrapping probabilistic core**。LLM 只負責「想答案」
(機率性),所有「格式合不合法、跑不跑得動、對不對得起契約」一律由 `scripts/` 的確定性 Python 決定。
每個 skill 的最後一個動作都是呼叫該 skill 的 `run.py`(Open Track 為 `advise.py`),由它**單獨**負責把
唯一一份契約 JSON **原子寫入結果檔**(file-based 輸出,course 2026-06 公告),確保輸出契約(規格書 §1.4)
不被 LLM 的自由發揮、也不被 hermes 的訊息美化破壞 —— 評分器只看寫進檔案的內容,不看對話說了什麼。

> **對 2026-06 file-based 公告的調整(本次更新)**:課程把輸出方式由「在對話印 fenced JSON」改為
> 「skill 把結果**寫進結果檔**、評分器讀檔」,並要求評分指令加 `-Q`。我據此做了四件事,且不更動任何
> Track 的任務內容:(1) 在 repo 根目錄加入課程提供的 `aiase_contract.py`(評分器與 `run_dev.py` 共用的
> 比對核心);(2) 把四個 skill 的 `run.py`/`advise.py` 由「印 fenced JSON」改為「自帶 `resolve_result_path()`
> + **原子寫入** `$AIASE_RESULT_PATH`(否則 `./aiase_result.json`)」,且**不 import `aiase_contract`**
> (安裝到 `~/.hermes/skills/` 後找不到 repo 根模組,故寫檔幾行自帶);(3) 每個 `SKILL.md` 的 Procedure 末步
> 由「輸出 JSON 區塊」改為「用 `terminal` 工具執行 `scripts/run.py` 寫結果檔,不必再在對話輸出 JSON」,
> 並加 `requires_toolsets: [terminal]`;(4) `run_dev.py` 改為設 `AIASE_RESULT_PATH`、用含 `-Q` 的正式指令
> 呼叫、再用 `aiase_contract` 讀檔比對。`python run_dev.py --skill text2sql-Azure0413 --track basic` 顯示
> 讀到結果檔並有比對結果,即確認已接上 file-based。原本的確定性驗證、retry、防禦性 parsing 一律保留,
> 只是「最終如何把答案交給評分器」從「說」變成「寫」。

### 1.1 Basic — Text2SQL Skill

- **`SKILL.md` 寫法**:把 procedure 切成 parse → plan → draft → **validate(retry)** → emit 五步,
  並在 Pitfalls 明列本題型最常見的語意陷阱(多對多 JOIN 漏 `DISTINCT`、引用不存在欄位、誤用 window/CTE、
  多 statement、非唯讀)。因為評分採 **bag(multiset)equality**(規格書 §4.1),我特別強調「語意要求去重時
  必須自己加 `DISTINCT`」——這是 bag equality 下最容易掉分的點。
- **harness 放什麼**:`scripts/validate_sql.py` 在 in-memory SQLite 上 `executescript(schema)` 後對
  draft 跑 `EXPLAIN`,做到三件確定性的事:(1) 擋 DDL/DML/PRAGMA 與多 statement;(2) 用 `EXPLAIN` 驗
  SQL 能否在該 schema 上 compile(抓出不存在的欄位/表);(3) 失敗時把 SQLite 的 error message 原樣回灌
  給 LLM 重試。`scripts/run.py` 做契約封裝(clamp confidence 到 [0,1]、強制 `task_id`、忽略 extra fields)並把結果**原子寫入結果檔**(`$AIASE_RESULT_PATH`,否則 `./aiase_result.json`)。
- **為何這樣設計**:正確答案不在手上(ground truth 只存在評分環境),所以 harness 能驗的是「合法性」
  而非「正確性」。我把能確定性驗證的部分(語法、欄位存在性)全部前置,把不可驗的部分(語意對不對)留給
  LLM + schema-grounded prompting。這正是「用確定性外殼縮小機率性核心的出錯面積」。

### 1.2 Pairwise — Code Author + Bug Hunter(兩個 skill 皆繳交)

依課程公告(2026-06 Q3),Pairwise 的**兩個 skill 都必須實作並繳交**,評分時課程**隨機抽其中一個角色**再與另一位
同學/staff 的對向 skill 配對;只繳一個會被扣分。故 `code-author-Azure0413/` 與 `bug-hunter-Azure0413/` **皆完整
實作並通過自測**。`PAIRWISE_ROLE.md` 以 `roles:` 清單同時宣告兩個角色與其 `skill_path`(兩者皆可被
`hermes skills list` 看到),並保留一組相容舊版自動評分器的未縮排 `role:`/`skill_path:`。

- **Code Author**:procedure 為 parse → draft → **self-test(retry)** → emit。`scripts/selftest.py` 是核心 ——
  (1) 用 `radon raw --json` 的 `sloc` 欄位算 S-LOC(與評分器同一把尺,規格書 §2.3),無 radon 時 fallback;
  (2) 用 `ast` 靜態掃描 `imports_forbidden`;(3) 在隔離 namespace `exec` 候選 code、對邊界輸入(空、單一、極值)
  自測。`run.py` 封裝契約並保證 `self_test_results` 一定含 `passed`/`failed`。
- **Bug Hunter**:procedure 為 parse → **probe(`scripts/analyze.py`)** → review → verdict → emit。`analyze.py`
  以 `ast` 抽 entry 函式 + 在 SIGALRM 逾時保護下對一組邊界輸入(空、單一、重複、極值、`None`)實跑候選 code,
  把 crash 的 traceback **對應回 `<candidate>` 的行號**當 suspicious line,讓 LLM 有確定性證據再下 bug 判斷。
  `run.py` 強制 enum(type/severity)、強制「verdict=clean ⇒ bugs=[]」,並過濾非法 bug。設計上**雙向防呆**:
  亂報 → clean code 的 false-positive 懲罰;都報 clean → recall 歸零。
- **設計取捨**:兩個角色都是 stateless、固定 schema 的工作,用兩個獨立 skill 最貼切(對應課程「Skill vs.
  Sub-Agent」原則,subagent 留給 Open Track 真正需要多步推理時)。

### 1.3 Open Track — `open-semver-Azure0413`(SemVer Advisor)

- **題目**:收到同一 Python 模組的兩個版本(`old_code` / `new_code`),判定該升 `major` / `minor` /
  `patch` 並產生 changelog 草稿。這是「open in design, strict in verification」的理想題型 —— 對每個維護套件
  的工程師都是真實痛點,而 SemVer 對「公開 API 變動 → 版本級別」是**有限、確定性**的映射,可逐條核對。
- **deterministic shell vs probabilistic core 的切分**:`scripts/_semver.py` 用 `ast` 抽「公開 API surface」
  (非 `_` 開頭的 module-level 函式/類別 + 公開方法 + `__init__`)與其簽名,依固定規則判 bump:刪符號/不相容
  簽名→major、向後相容新增→minor、僅內部改動→patch。`classify.py`(選用證據)與 `evaluate.py`(grader-facing)
  **共用** `_semver.py`,確保「驗的=評的」,無 hidden assumptions(規格 §共通原則 #5)。
- **跨模型穩健性是本 skill 的核心設計(關鍵能力)**:這題的答案(bump 與 symbol-complete changelog)**完全可由
  程式確定性算出**,所以我把機率性核心壓到最小 —— `scripts/advise.py` 是 **one-shot 入口**:吃使用者原始輸入 →
  算 bump + 自動產 changelog → **把最終契約原子寫入結果檔**。SKILL.md 的 Procedure 因此只有一步:「用 terminal
  把輸入原樣丟給 `advise.py`,它就寫好結果檔」。LLM **不自行判斷、不多步、不改欄位、不必轉述輸出**,把跨模型
  隨機性降到最低。`advise.py` 並對 LLM 最常見的
  argv 跳脫錯誤(過度跳脫 `\\n`、非法 `\'`、整包 double-encoded 的 `\"`)做確定性復原。
  **實測(§2.x):8 顆模型中 7 顆三題全對,含正式計分池的 gemma4 與 gemini-2.5-flash;唯一失敗的 llama2(2023 年舊模型)
  連模板變數都不會代入,屬能力下限,遠低於計分池。**
- **metric 與不可 gameable 的設計(關鍵)**:`evaluate.py` **自己用 AST 重算權威 bump**,再與 skill 預測做 exact
  比對(`bump_correct`,主指標)+ changelog 覆蓋率(次指標);grader 在**held-out perturbations**(同類別、不同
  diff,見每個 scenario 檔的 `perturbations`)上評分。因為「正確答案」是評分器算的、不是 skill 給的,且 diff 是
  未見過的,**對固定 task_id 硬編答案必失敗** —— 我用 `tests/test_semver.py` 的 20 個案例與三個 scenario 的
  held-out 變體驗證了規則的正確性(全綠)。

---

## 2. 實際遭遇之失敗與分析

> 以下 log 皆由 §開頭描述的 mini-agent proxy 在真實模型上跑出:計分池的 `gemma4` / `gemini-2.5-flash`,
> Open Track 另加 6 顆模型做跨模型壓測。

### 失敗 1 — Open Track 跨模型穩健性:三類隨機性失敗,以「one-shot + 容錯解析」逐一根治(真實 log,8 顆模型壓測)

這是本專案最核心的 harness 工程:我把 Open Track 在 **8 顆模型**(計分池的 gemma4 / gemini-2.5-flash,加上
llama3:8b、qwen2.5:7b、qwen2.5-coder:7b、gemma3:12b、phi4:14b,以及刻意找最弱的 llama2)上壓測,逐一找出
隨機性失敗並修掉。三類真實失敗:

- **(A) 多步協定中弱模型「自行覆蓋」確定性結果**:初版 procedure 是兩步(先 `classify.py` 取 bump、再 `run.py`
  輸出)。`gemma3:12b` 在 `semver_003` 無視 classify 的 `patch`、憑直覺報 `minor`(加了選填參數的直覺陷阱);`llama2`
  亦自行報 `major`。
- **(B) 弱模型走不完多步**:`phi4:14b`、`llama2` 在兩步協定下產不出最終契約(`bump=""` / 無 JSON)。
- **(C) argv 跳脫各種花樣**:`gemini` 把換行過度跳脫成 `\\n`(→ `ast.parse` 報 syntax error);`gemma3` 把整包
  payload **double-encode**(內層 `\"` + `\\n`),一度被誤復原成錯誤的 `minor`。

- **成因**:(A)(B) 共同根因是「多步協定給了機率性核心太多介入空間」;(C) 是 LLM 對 JSON/shell 跳脫的穩定度因模型而異。
- **修正方式(關鍵設計)**:
  1. **collapse 成 one-shot**:新增 `scripts/advise.py` —— 吃原始輸入、確定性算出 bump + symbol-complete changelog、
     直接輸出最終契約。SKILL.md Procedure 改成單一步「轉發輸入 → 轉述輸出」,LLM 不再判斷/多步/改欄位 →(A)(B) 消失。
  2. **容錯解析**:`advise.py` / `_semver._safe_parse` 對 `\\n`/`\\t`/`\\r` 過度跳脫、非法 `\'`、整包 double-encoded
     `\"`、以及**同時**過度跳脫換行與引號(`unit=\"cm\"`,實測於 `llama3.1:8b` 觀察到)做確定性復原(只在標準 parse
     失敗時才嘗試,正常輸入零影響,真壞掉的 code 仍回報 error)→(C) 消失。
  3. 回歸測試:`tests/test_semver.py` 含 `test_recovers_over_escaped_newlines`、`test_recovers_over_escaped_quotes`、
     `test_advise_recovers_double_encoded_payload` 等(共 20 個 semver 案例,全綠)。
- **結果**:修正後 **8 顆模型中 7 顆三題全對**(gemma3 2/3→3/3、phi4 1/3→3/3,計分池 gemma4/gemini 維持 3/3);
  僅 `llama2`(2023 舊模型)仍 0/3 —— 它連 SKILL.md 的模板變數 `<...>` 都原樣輸出、不會代入,屬模型能力下限,遠低於計分池,
  非 harness 可救。**這就是「用確定性外殼把機率性核心框到最小」的具體成果。**
- **MAST 分類**:(1) 規格與角色(協定設計 + 輸入跳脫)+ (3) 驗證與品質(以確定性 one-shot 根治)。

### 失敗 2 — Basic:輸入用 `db_schema`、harness 只讀 `schema_ddl`,validator 永遠回「no such table」(真實 log,已修)

- **觸發場景**:`task_nl2sql_006`(以及 gemini 的 `task_nl2sql_008`)。輸入契約的 schema 欄位叫
  `db_schema`,但 `validate_sql.py` 初版只讀 `schema_ddl`。模型很自然地沿用輸入欄位名 `db_schema` 去呼叫
  validator,於是 validator 拿到空 schema、建不出表。
- **log 片段**(`_e2e/logs/real_gemma4_latest_basic.json`,逐字):

  ```
  assistant: EXEC python scripts/validate_sql.py '{"db_schema":"CREATE TABLE Customers (...); ...","sql":"SELECT DISTINCT ... FROM Customers ..."}'
  stdout:    {"ok": false, "error": "SQL did not compile: no such table: Customers"}
  ... (模型相信「真的沒這張表」,反覆改 SQL,連 4 次都拿到同一個 no-such-table,耗盡步數) ...
  ```

- **成因分析**:**介面契約不一致** —— validator 的參數名與任務輸入的欄位名不同,而 SKILL.md 沒把這個
  對應寫死。確定性 harness 此時反而「確定性地誤導」LLM:它給了一個語法正確、但語意完全錯誤的訊號
  (「表不存在」),把模型推向錯誤的修補方向。這比沒有 harness 更糟,凸顯 harness 的**介面**本身也要被驗證。
- **修正方式**:`validate_sql.py` 改為同時接受 `schema_ddl` 與 `db_schema`(`schema or db_schema`),
  並在 SKILL.md procedure 第 4 步把呼叫範例寫成 `'{"db_schema": <verbatim>, "sql": <draft>}'`。修正後同樣的
  schema 直接回 `{"ok": true}`(已在 commit 中驗證)。
- **MAST 分類**:(1) 規格與角色(skill 內部介面契約未對齊輸入契約)。

### 失敗 3 — Basic:SQL 單引號字面值與 shell 單引號 argv 衝突,指令在 bash 層就崩(真實 log,3/8→8/8 已根治)

- **觸發場景**:在計分池模型 `gemma4` 上實跑 8 題 dev set。**任何 `WHERE x = '字面值'` 的題目都失敗**:
  SQLite 字串字面值依標準用**單引號**,但 agent 把整包 payload 用**單引號**包成 shell argv
  (`python scripts/run.py '{...}'`),內外單引號相撞,**bash 在 script 執行前就報 `unexpected EOF`**——
  確定性外殼根本沒被呼叫到,談不上容錯。
- **log 片段**(`gemma4:latest`,逐字):

  ```
  assistant: python scripts/run.py '{"task_id":"task_nl2sql_001","sql":"... WHERE T3.title = 'AI Foundations';", ...}'
  terminal:  /bin/bash: -c: line 1: unexpected EOF while looking for matching `"'
  → 模型反覆改用 \'…\' / \"…\" 跳脫均失敗,耗盡步數,`run.py` 從未被叫到、**結果檔從未被寫出**(該題 0 分)
  ```

- **成因分析**:根因**不在模型端、也不在 JSON 解析端**,而在「把含單引號的 payload 經 shell 單引號 argv 傳遞」
  這條路徑本身 —— 這是 shell 引號相撞,任何模型都救不了。先前版本只在 SKILL.md Pitfalls 提醒「SQL 用單引號」,
  屬 prompt 級緩解,治標不治本(實測 gemma4 仍 **3/8**)。
- **修正方式(根治,harness 工程)**:讓 `run.py` / `validate_sql.py`(以及 code-author/bug-hunter/open-semver 的
  對應 script)**同時接受 stdin**,並在 SKILL.md Procedure 改用 **quoted heredoc**(`python scripts/run.py <<'JSON' … JSON`)
  —— heredoc body 完全 literal,SQL 內的單引號零跳脫即可安全傳入。stdin 讀取以 `isatty()` 防呆(無 argv、無 pipe
  時立即回空契約,不會卡住等輸入)。**effect:同一 8 題、同一 gemma4,3/8 → 8/8(全部 bag-equal 對到 gold)。**
- **契約韌性(不變)**:即便輸入仍壞掉,所有 wrapper 依規格書 §1.4 #7 仍輸出合法契約 JSON(`task_id` 空、
  `confidence=0`)**並寫進結果檔**,不噴 traceback —— 壞輸入退化成「合法但低分」,而非評分器讀不到結果檔。
- **MAST 分類**:(1) 規格與角色(skill 呼叫介面 / 跳脫路徑設計)+ (3) 驗證與品質(以確定性 stdin 路徑根治)。

### 2.x 端到端實測結果

> 由 mini-agent proxy(刻意較弱)在正式計分模型池上實跑;確定性部分為精確值,LLM 端 Basic/Pairwise 仍受
> 模型當下發揮影響。

**Open Track 跨模型穩健性(8 顆模型 × 3 scenario,one-shot 設計後)：**

| 模型 | 屬性 | 通過 |
|---|---|---:|
| gemma4 | **正式計分池** | **3 / 3** |
| gemini-2.5-flash | **正式計分池** | **3 / 3** |
| llama3:8b | 旁證 | 3 / 3 |
| qwen2.5:7b | 旁證 | 3 / 3 |
| qwen2.5-coder:7b | 旁證 | 3 / 3 |
| gemma3:12b | 旁證(修正前 2/3) | 3 / 3 |
| phi4:14b | 旁證(修正前 1/3) | 3 / 3 |
| llama2:latest | 2023 舊模型,遠低於計分池 | 0 / 3（能力下限,見 §失敗1） |

→ **8 顆中 7 顆三題全對,含兩顆正式計分模型**;bump_correct 與 changelog 覆蓋率皆 1.0。

**其餘 Track（LLM 機率性核心,Basic/Pairwise）：**

| Track | 模型 | 通過 | 備註 |
|---|---|---:|---|
| Pairwise (Code Author) | gemma4 | 4 / 5 | reference_tasks 的 hidden-style test cases 全綠才算過 |
| Pairwise (Bug Hunter) | gemma4 | recall 4/5, FP 0/5 | clean code **零誤報**(雙向平衡) |
| Basic (Text2SQL) | gemma4(**heredoc 修正前**) | 3 / 8 | 失分全為 §失敗3 的 shell 引號相撞(`WHERE x='…'`) |
| **Basic (Text2SQL)** | **gemma4(heredoc 修正後)** | **8 / 8** | 同題同模型,改走 stdin/heredoc 後全部 bag-equal 對到 gold |

**不可 gameable 證據**:bump 一律由 `evaluate.py` 用 AST **重算**,skill 報什麼都不影響「正確答案」;grader 另以
每個 scenario 檔的 held-out `perturbations`(同類別不同 diff)評分 —— 換 diff、換符號名,答案仍是程式算的,背不了。

確定性元件本身的測試:`python -m pytest -q` → **199 passed**(含新增的 `tests/test_filebased_contract.py`:
驗 `aiase_contract.read_result`/`validate_basic_schema` 與四個 skill 的 `run.py`/`advise.py` 確實寫出合法結果檔);
`python verify_repo.py --github-id Azure0413` → **28/28 passed**。

> 註:Open Track(我可完全掌控、確定性評分)在兩顆計分模型上皆 3/3。Basic 的失分原本集中在「SQL 單引號 vs
> shell 單引號 argv 相撞」這條**與模型無關**的路徑(§失敗3);改為 stdin/heredoc 後,**同一最小計分模型 gemma4
> 由 3/8 升到 8/8**。這再次印證本專案主軸:把不可靠的傳遞路徑換成確定性外殼,LLM 端的機率性就被框到最小。

---

## 3. 改進方向

1. **Basic**:在 `validate_sql.py` 之外加一層「self-consistency / 結果形狀檢查」—— 例如以隨機小資料填入
   schema、實跑 candidate SQL,檢查回傳欄位數是否與題意一致(問「名字」卻回多欄),雖仍驗不到語意對錯,
   但能再砍掉一批形狀錯誤。也可在 prompt 注入「依 schema 推斷的 JOIN 路徑」做 schema grounding。
2. **Open / 最後的能力下限(llama2 類)**:目前 one-shot + 容錯解析已讓 7/8 模型滿分;唯一失敗的 llama2 連模板
   變數都不代入。若要連這種模型都救,可在 SKILL.md 提供「先用 agent 的 file-write 把 payload 寫成檔、再 `advise.py
   <file>`」的零跳脫路徑,或讓 skill 接受 base64 輸入 —— 徹底移除「把多行字串塞進 argv」這個唯一的脆弱點。
3. **Pairwise**:讓 `selftest.py` 自動「依 task_description 生成邊界 case」(空、單一、極大、負數、重複),
   而非只跑呼叫端給的 sample,提升 Code Author 對 hidden test 的覆蓋。
4. **harness 統一**:2026-06 file-based 更新後,比對核心已集中在課程提供的 `aiase_contract.py`(評分器與
   `run_dev.py` 共用),寫檔邏輯則因「skill 安裝後找不到 repo 根模組」而**刻意**由各 `run.py` 自帶
   `resolve_result_path()` 副本。後續可加一支 repo 內的 lint,檢查四個 skill 的 `resolve_result_path()` 與
   `aiase_contract.resolve_result_path` **逐字一致**,自動防止寫檔路徑規則漂移。
5. **測試流程**:把這次自製的 mini-agent proxy 正式化成 repo 內的 `--e2e` 自測模式(不含任何 key),
   讓任何人都能在自己的 gateway 上一鍵跑端到端回歸,而非只跑確定性單元測試。

---

## 4. 分工(僅兩人組需填)

單人組,不適用。

---

## 5. 引用說明

- **Starter repo**(課程提供):`Netdb-NCKU/aiase2026-final-project`。本 repo 的目錄結構、`run_dev.py`、
  `verify_repo.py`、`dev_set/`、reference skills、以及 `text2sql` / `code-author` / `bug-hunter` 三個
  **skeleton**(`SKILL.md` 骨架與 `scripts/run.py`、`validate_sql.py`、`selftest.py`、`analyze.py` 的初版)
  均來自 starter。
- **課程 2026-06 file-based 更新包**(課程提供):`aiase_contract.py`(評分器與本地共用的比對核心)直接採用
  課程版本(verbatim);`run_dev.py` 的 file-based 驅動骨架與四個 skill `run.py` 的「`resolve_result_path()` +
  原子寫入」寫法,依課程 `README_UPDATE.md` 的範例改寫到本人既有的 wrapper 上(保留本人原有的契約校驗、retry、
  防禦性 parsing)。我的工作為:完成 github_id 命名、清理 skeleton 的 TODO 註記與版本號、修正 `validate_sql.py`
  的 `db_schema` 鍵 bug 與四個 `run.py` 的 NaN/Infinity 漏洞、撰寫 **Open Track 全部內容**(`SKILL.md`、
  `scripts/_semver.py`、`advise.py`、`classify.py`、`evaluate.py`、`run.py`、`dev_set/open/` 三個 scenario、`tests/test_semver.py`)、
  填寫 `OPEN_TRACK.md` / `PAIRWISE_ROLE.md` / 本報告,並自建端到端測試。
- **未借用任何外部第三方 skill / repo 的實作**:Open Track 的 SemVer-Advisor 構想(以 AST 比對公開 API surface
  判 bump)與全部程式為自行撰寫;`ast` / `re` / `sqlite3` / `radon` 皆為標準用法。SemVer 規則依
  [semver.org](https://semver.org) 的公開定義實作。
- **AI 輔助**:本專案在開發與除錯過程使用了 AI coding assistant(依規格書 §6.1 允許),用於草擬程式、
  撰寫測試與潤飾本報告文字;最終提交內容之 correctness、security、引用由本人負責。未自任何特定 public
  repo 大段改寫程式碼;若日後 similarity 比對標出疑似來源,以本節說明與 commit history 為準。
