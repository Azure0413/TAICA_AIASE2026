# AIASE 2026 期末專案 — AI 評閱回饋

**GitHub ID:** `Azure0413`

## 成績摘要

| 軌道 | 分數 |
|---|---|
| Basic Track(text2sql) | 30.0 / 30 |
| Pairwise Track(角色:Bug Hunter) | 7.71 / 10 |
| Open Track(設計 40% + 執行 60%) | 96.2 / 100 |
| 基礎加分(nano 第二參考) | 29.0 / 30 |
| Pairwise 加分(nano CA) | 5.0 / 10 |
| **Project 總分** | **92.4** |

- 額外榮譽 / 加分:Open 對抗穩健(輸入重排答案不變)
- 評分重試次數:Basic **0 次**(一次到位);Pairwise 採統一重試政策(no-result 重試 1 次、flaky 受害者重評取最佳),未逐人記錄次數。

## Open Track 計分明細(透明拆解)

Open 總分 = **設計審查 × 40% + 實跑驗證(60 分制)** = **96.2 / 100**

**① 設計審查(占 40 分)= 36.2 分**(LLM 閱讀你的 skill 評分:90.5/100)

- **可驗證性:10/10** — 設計具備完整客觀金標準：`evaluate.py` 在 grader 端以同一份 `_semver.py` AST 規則重算權威 bump，與 skill 輸出做 exact match，完全不依賴 LLM 主觀判斷。Held-out perturbations 機制（OPEN_TRACK.md §4）更確保無法硬編答案，bump_correct 為純確定性 binary metric。
- **完整與清晰:9/10** — OPEN_TRACK.md、SKILL.md、四支 scripts（_semver.py、advise.py、classify.py、evaluate.py、run.py）均齊備，涵蓋輸入 schema、輸出 schema、file-based 結果路徑、token budget、三個公開 scenario 及 perturbation 說明。唯獨 `dev_set/open/semver_00{1,2,3}.json` 實際檔案內容未隨素材提供，perturbations 欄位無法直接核驗。
- **方法正確性:9/10** — `_semver.py` 的 `_sig()` 正確處理 posonlyargs / defaults / kw_defaults，`_sig_change()` 的 breaking/additive 邏輯與 SKILL.md「SemVer rule」完全一致；三個 scenario（minor/major/patch）按規則推導均正確。`_safe_parse()` 的 over-escape 修復邏輯合理，唯多重繼承或 `@property` 等 Python 邊界案例未見處理，但對本題範疇影響甚微。
- **失敗模式/穩健:9/10** — `advise.py` 以 `_loads_tolerant()` 處理三層 JSON 容錯（原始、\'修復、double-encoded），`_safe_parse()` 對 over-escaped `\n`/`\t`/`"`均有修復，所有錯誤路徑仍輸出合法契約 JSON 至結果檔（confidence=0.0/0.1）而非 crash。File-based 原子寫入（`.tmp` → `os.replace`）防止部分寫入。略扣分因 `dev_set` 檔案未能確認 perturbation 覆蓋度。
- **工程嚴謹度:9/10** — 規則定義在 `_semver.py` 單一來源，SKILL.md 與 OPEN_TRACK.md 均引用同一規則，無 hidden assumptions（符合規格 §共通原則 #5）。LLM 角色限縮為「執行一條 terminal 指令」，bump 判定完全由 AST 腳本決定，嚴格落實「確定性 shell 包覆概率核心」模式。預期失敗模式（§5）有針對性分析，且已對症下藥。
- **難度與原創:7/10** — 將 SemVer 升版判定轉化為 AST-diff 確定性 skill 的思路清晰且實用，file-based output 與 held-out perturbation 的 anti-gaming 設計有一定巧思。然而 SemVer + AST 分析在業界已有成熟工具（如 `griffe`、`semver-check`），整體構思屬已知手法的良好重新實作，創新度適中。

**② 實跑驗證(占 60 分)= 60 分**
- 可實際執行、輸出合法:✓ +20(滿 20)
- **確定性**(同輸入跑兩次結果一致):✓ +25(滿 25)
- 對自宣告 gold 正確:✓ +15(滿 15)

**執行診斷:** **【複核更正 2026-06-22】執行**:你的 skill 屬「LLM 產生 artifact(regex/程式/測試/查詢)→ 確定性腳本算分」設計;原評分比對的是 artifact 原始字串而非你宣告的 metric,故誤判確定性/對 gold 失敗。經實跑你的 evaluate 確認 metric 一致且達標,已將相應項目判為通過。

> 為何採「設計 + 實跑」雙軌:對齊公告「open in design, strict in verification」——設計分肯定你的構想,實跑分檢驗它**真的可重現、可驗證**(確定性 / 對得上自己的 gold)。

## 評語

**優點：**

- **Basic Track 滿分（100/100）**，30 題全數通過，text2sql 能力扎實。
- Open Track 設計最令人印象深刻：以 `_semver.py` 作為唯一規則來源，grader 端透過 AST 重算 bump 再做 exact-match，徹底消除 LLM 主觀判斷，是「確定性 shell 包覆概率核心」的優秀範例。文件（OPEN_TRACK.md、SKILL.md）、腳本與三層 JSON 容錯機制均完整齊備，設計審查拿到 90.5/100，對抗穩健測試也通過 ✓。

**改進建議：**

1. **補充 `dev_set/` 的擾動內容**：目前 held-out perturbation 素材未附上，導致覆蓋廣度無法完整核驗。下次請將具體樣本一併納入提交，讓評審可端對端重現。
2. **補充 Python 邊界語法說明**：`property`、多重繼承等邊界情境在 `_semver.py` 的處理方式未見說明，建議在 SKILL.md 中明確記錄這些案例的行為或已知限制。
3. **提升 Pairwise Bug Hunter 精準度**：buggy 偵測 F1 為 0.67，仍有漏報空間；可回顧誤判案例，檢視規則閾值或分類邏輯是否需要調整。

---
> 本評閱由 AIASE 2026 自動化評分系統產生,供學習回饋參考。
> 方法對齊課程公告精神「**open in design, strict in verification**」:
> Open Track 以 **LLM 設計審查(40%)+ 確定性實跑驗證(60%)** 評分;Basic 對齊權威 `run_dev.py`;Pairwise 以 sandbox 跑題與 bug 偵測 F1 計分。
> 各軌分數與權重以課程最終公告為準;加分項獨立計算。
