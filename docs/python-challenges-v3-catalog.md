# Sixty-question repair catalog V3 (60 題分級修復題庫)

The V3 catalog contains 60 distinct tasks: 20 easy, 20 medium and 20 hard. It retains the twelve V2 task IDs and adds 48 original tasks. Difficulty is a design estimate, not an empirical ranking of the user’s model. Every task includes an independently authored expected-case set, a passing reference and a genuinely faulty starting program.

| Difficulty (難度) | Design criteria (設計依據) | Training | Validation | Held-out | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| Easy (初階) | Local conditions, boundaries and one-pass data transformations | 10 | 5 | 5 | 20 |
| Medium (中階) | Multiple invariants, ordering, state and input preservation | 10 | 5 | 5 | 20 |
| Hard (進階) | Graphs, dynamic programming, parsers and interacting constraints | 10 | 5 | 5 | 20 |

These labels support filtering and balanced sampling. A task with a short reference may still require identifying a global invariant. Actual difficulty must be calibrated with a fixed provider, model, Skill and budgets.

## Installation and batches (載入與分批)

Open **多難度 Python 題庫**, choose **均衡批次 1–5**, and click **載入 60 題並啟用所選批次**. A first import adds missing questions and preserves existing IDs and operator edits. Existing V1-only or V1+V2 stores normally contain 72 total questions afterward: the 60 catalog tasks plus twelve disabled V1 questions. Custom questions remain additional entries within the existing 100-question storage cap.

Each batch selects 12 tasks: six training, three validation and three held-out. Each difficulty contributes two training, one validation and one held-out task. Five batches are disjoint and collectively cover all 60 tasks. Changing the selected dropdown alone makes no request. Explicit batch application changes only future enablement/version/revision; frozen Runs retain their original dataset.

All related groups retain a fixed split across the entire catalog. Related graph and expression tasks share declared training groups; glob/regex variants stay in validation, bounded change/knapsack stay held-out, and sparse/polynomial aggregation stays in training. There are 53 declared groups. This check does not prove the absence of every semantic similarity.

The per-run limit remains 50 enabled tasks. The supported operating path uses 12 at a time; it does not increase workload or deadlines to evaluate all 60 together. Per balanced batch the existing exploration defaults remain six proposals, 45 search evaluations, 57 total rollout slots, 576 model request slots and 171 verifier batches under a 7200-second workflow cap. These ceilings do not guarantee completion on a particular model or host.

## Catalog (題目清單)

### Easy (初階)

| ID | Task (題目) | Fixed split (固定分割) | Public / retained cases |
| --- | --- | --- | ---: |
| `CH-v3-clamp-array` | 陣列截限 / Array clamping | Training (訓練) | 2 / 4 |
| `CH-v3-positive-total` | 正值加總 / Positive total | Training (訓練) | 2 / 4 |
| `CH-v3-digit-histogram` | 十進位數字統計 / Digit histogram | Training (訓練) | 2 / 4 |
| `CH-v3-rotate-list` | 循環位移 / List rotation | Training (訓練) | 2 / 4 |
| `CH-v3-zip-pad` | 補齊配對 / Padded zip | Training (訓練) | 2 / 4 |
| `CH-v3-ragged-transpose` | 不等長矩陣轉置 / Ragged transpose | Training (訓練) | 2 / 4 |
| `CH-v3-strip-prefix` | 移除單次前綴 / Strip one prefix | Training (訓練) | 2 / 4 |
| `CH-v3-nearest-multiple` | 最近整數倍 / Nearest multiple | Training (訓練) | 2 / 4 |
| `CH-v3-safe-divisions` | 安全除法 / Safe divisions | Training (訓練) | 2 / 4 |
| `CH-v3-toggle-ascii` | ASCII 大小寫切換 / ASCII case toggle | Training (訓練) | 2 / 4 |
| `CH-v3-parity-partition` | 穩定奇偶分組 / Stable parity partition | Validation (驗證) | 2 / 4 |
| `CH-v3-common-prefix` | 共同前綴 / Common prefix | Validation (驗證) | 2 / 4 |
| `CH-v3-diagonal-sums` | 矩陣對角線加總 / Diagonal sums | Validation (驗證) | 2 / 4 |
| `CH-v3-inclusive-range` | 含端點數列 / Inclusive range | Validation (驗證) | 2 / 4 |
| `CH-v3-replace-slice` | 區段替換 / Slice replacement | Validation (驗證) | 2 / 4 |
| `CH-v3-pick-fields` | 欄位投影 / Field projection | Held-out (最終測試) | 2 / 4 |
| `CH-v3-duration` | 時間分解 / Duration decomposition | Held-out (最終測試) | 2 / 4 |
| `CH-v3-local-peaks` | 局部峰值 / Local peaks | Held-out (最終測試) | 2 / 4 |
| `CH-v3-half-balance` | 前後半部平衡 / Half balance | Held-out (最終測試) | 2 / 4 |
| `CH-v3-leap-date` | 日期合法性 / Gregorian date | Held-out (最終測試) | 2 / 4 |

### Medium (中階)

| ID | Task (題目) | Fixed split (固定分割) | Public / retained cases |
| --- | --- | --- | ---: |
| `CH-v2-quoted-fields` | 引號欄位掃描 / Quoted fields | Training (訓練) | 3 / 6 |
| `CH-v2-sessionize` | 事件分段 / Sessionization | Training (訓練) | 2 / 4 |
| `CH-v2-lru` | 有界 LRU 快取 / LRU cache | Training (訓練) | 2 / 4 |
| `CH-v2-dependency-layers` | 相依批次排序 / Dependency layers | Training (訓練) | 2 / 6 |
| `CH-v2-expression` | 整數運算式 / Integer expression | Training (訓練) | 3 / 8 |
| `CH-v2-grid-paths` | 網格最短路徑計數 / Grid paths | Training (訓練) | 2 / 5 |
| `CH-v3-sparse-add` | 稀疏矩陣相加 / Sparse addition | Training (訓練) | 2 / 4 |
| `CH-v3-stable-top-k` | 穩定前 K 名 / Stable top K | Training (訓練) | 2 / 4 |
| `CH-v3-expand-ranges` | 範圍展開 / Range expansion | Validation (驗證) | 2 / 4 |
| `CH-v3-simplify-path` | 路徑正規化 / Path normalization | Training (訓練) | 2 / 4 |
| `CH-v3-edit-distance` | 編輯距離 / Edit distance | Validation (驗證) | 2 / 4 |
| `CH-v3-polynomial-add` | 多項式合併 / Polynomial addition | Training (訓練) | 2 / 4 |
| `CH-v3-next-greater` | 右側下一個較大值 / Next greater | Validation (驗證) | 2 / 4 |
| `CH-v3-window-spread` | 滑動視窗全距 / Window spread | Validation (驗證) | 2 / 4 |
| `CH-v3-weighted-round-robin` | 加權輪詢 / Weighted round robin | Validation (驗證) | 2 / 4 |
| `CH-v3-rational-sum` | 分數加總 / Rational sum | Held-out (最終測試) | 2 / 4 |
| `CH-v3-tab-expand` | 定位點展開 / Tab expansion | Held-out (最終測試) | 2 / 4 |
| `CH-v3-competition-rank` | 同分競賽排名 / Competition ranks | Held-out (最終測試) | 2 / 4 |
| `CH-v3-reflected-walk` | 邊界反射步行 / Reflected walk | Held-out (最終測試) | 2 / 4 |
| `CH-v3-reservoir-transfer` | 儲槽轉移 / Reservoir transfer | Held-out (最終測試) | 2 / 4 |

### Hard (進階)

| ID | Task (題目) | Fixed split (固定分割) | Public / retained cases |
| --- | --- | --- | ---: |
| `CH-v2-glob` | 跳脫萬用字元比對 / Escaped glob | Validation (驗證) | 3 / 6 |
| `CH-v2-inventory` | 原子庫存交易 / Atomic inventory | Validation (驗證) | 2 / 4 |
| `CH-v2-sweep-load` | 時段負載統計 / Sweep load | Validation (驗證) | 2 / 5 |
| `CH-v2-tree-paths` | 樹狀路徑編碼 / Tree path encoding | Held-out (最終測試) | 2 / 4 |
| `CH-v2-ring-buffer` | 可調容量緩衝區 / Resizable buffer | Held-out (最終測試) | 2 / 4 |
| `CH-v2-bounded-change` | 有界找零 / Bounded change | Held-out (最終測試) | 2 / 6 |
| `CH-v3-strong-components` | 強連通分量 / Strong components | Training (訓練) | 2 / 4 |
| `CH-v3-knapsack` | 零一背包 / Zero-one knapsack | Held-out (最終測試) | 2 / 4 |
| `CH-v3-kth-permutation` | 第 K 個排列 / K-th permutation | Training (訓練) | 2 / 4 |
| `CH-v3-decode-count` | 編碼解讀計數 / Decode count | Training (訓練) | 2 / 5 |
| `CH-v3-water-fill` | 最低水位分配 / Minimum-level allocation | Training (訓練) | 2 / 4 |
| `CH-v3-regex-match` | 受限正規表示式 / Restricted regex | Validation (驗證) | 2 / 6 |
| `CH-v3-sheet-evaluation` | 儲存格相依求值 / Cell evaluation | Training (訓練) | 2 / 4 |
| `CH-v3-max-rectangle` | 最大子矩形和 / Maximum rectangle | Training (訓練) | 2 / 4 |
| `CH-v3-parenthesized-arithmetic` | 括號運算式 / Parenthesized arithmetic | Training (訓練) | 2 / 6 |
| `CH-v3-priority-toposort` | 字典序拓樸排序 / Priority topological order | Training (訓練) | 2 / 4 |
| `CH-v3-minimum-cover` | 最短涵蓋子字串 / Minimum cover | Validation (驗證) | 2 / 4 |
| `CH-v3-max-flow` | 整數最大流 / Integer max flow | Training (訓練) | 2 / 4 |
| `CH-v3-huffman-cost` | 最佳合併成本 / Huffman merge cost | Training (訓練) | 2 / 4 |
| `CH-v3-optimal-wrap` | 最佳文字換行 / Optimal wrapping | Held-out (最終測試) | 2 / 4 |

## Verification boundary (驗證範圍)

The shipped pack has 123 public and 259 retained examples. All references pass and all starting programs fail at least one retained example. Reference-source equality is checked across the sixty tasks to avoid counting renamed identical programs. Five harder families are additionally compared with 80 deterministic small-instance cases: exhaustive knapsack choices, min-cut enumeration for maximum flow, exhaustive line partitions, exhaustive merge orders and an independent regular-expression engine. Copied isolated evaluator tests run all sixty references without site packages.

Reference code is excluded from frozen model fixtures, and hidden cases remain inaccessible to repair tools. Preset installation calls no model. Only missing catalog questions are reference-validated during import, at most sixty serial five-second evaluator subprocesses; the GUI gives this explicit operation a 360-second HTTP wait. Subsequent batch changes reuse saved questions without revalidating or overwriting edits. Stale revisions, malformed fields, edited selected split/difficulty/group or storage overflow fail before the atomic catalog update.

The exact SDK graph remains test runner → RuntimeService → coordinator → pinned GEPA worker → fresh nanobot processes → bounded visible tools and immediate verification → independent final tasks → evaluator replay → reviewer replay → explicit approval replay. The V3 integration has the same 22-rollout/133-request ceiling as the V2 fixture: 4450 workflow seconds, 30 seconds terminal cleanup, 110 seconds approval replay, ten seconds JS consumer time and at most 300 seconds preset validation, contained by the existing 7200-second module bound. Trusted evaluator children retain five-second bounds. No inference deadline, syntax policy or release requirement was weakened.

A broader local run completed the V3 workflow through reviewer but then detected a malformed supplementary debug SQLite database when counting verifier events. That failure evidence is retained under `.local/test-reports/challenge-workflow/78c598f72298471c9b295c55940535b5`. The exact SDK case passed in an isolated run on unchanged runtime source, including all 66 workflow verifier batches and 88 batches after approval. This does not establish the cause or resolution of the SQLite corruption. A separate schema test originally mistook the word “references” in a prompt for a leaked reference field; it now checks actual row/fixture keys and passes for every frozen batch.

Focused results cover 34 distinct Python cases with zero skips and 141 frontend cases. The SDK fixtures use scripted loopback replies and prove implementation behavior; real-model evolution gains, Windows/GPU stability, Docker execution and full M acceptance remain separate qualifications.
