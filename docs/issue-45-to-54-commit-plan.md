# Issue #45～#54 Git 提交计划

> 文档生成日期：2026-11-17
> 当前分支：`refactor/user-context`
> 项目目录：`D:\STUDY\echo\personal-knowledge-base`
> 文档性质：**仅制定计划，未执行任何 `git add` / `git commit` / `git push`**。本文所有状态来自本次重新执行的 Git 命令与逐文件抽查，未沿用旧结论。

> **时效说明（后补，不代表原计划生成时的结论）**：本原计划生成于 2026-11-17，针对 **PR #55 合并前**的原子提交安排，文中"#46 未实施、不含"均为当时的真实决策，原样保留以还原提交边界的历史判断。**Issue #46 后由 PR #56（`849daad`，2026-11-19 合并，正文含 `Closes #46`）独立完成并关闭，并未包含在本计划所述的提交中。** 下文对涉及 #46 的 5 处原结论逐条追加"〔当前状态〕"标注；未标注部分仍为 2026-11-17 当时的计划记录，请勿将原文误读为"计划生成时 #46 已完成"。

---

## 1. 当前 Git 状态

### 1.1 本次执行的命令与结果

| 命令 | 结果摘要 |
|---|---|
| `git branch --show-current` | `refactor/user-context` |
| `git status --short --branch` | 24 个已跟踪修改（` M`）+ 26 个未跟踪项（`??`，目录已折叠）；分支头 `## refactor/user-context` |
| `git diff --stat` | `24 files changed, 1081 insertions(+), 902 deletions(-)` |
| `git diff --name-status` | 24 行，全部为 `M`（无新增/删除/重命名） |
| `git diff --cached --stat` | 空（**暂存区无任何内容**） |
| `git ls-files --others --exclude-standard` | 展开为 **65 个文件**（其中备份目录 39 个、工作日志 1 个、正式新增文件 25 个） |

> **两种计数口径需区分**：`git status` 的 **26 项**是把 `.workbuddy/`、`_ISSUE_PATCHES/`、`backend/modules/mistake/domain/` 折叠为目录后的数量；`git ls-files --others` 的 **65 个**是展开到文件的数量。二者不矛盾。

### 1.2 最近提交（`git log -5 --oneline`）
```
4224bf5 docs: add real-world learning scenario to README (#44)
42a3c22 Update README.md
16eac12 feat: complete tag management UI (#43)
fe699e7 Update README.md
6e8e087 feat: add embedding hybrid search (#42)
```
HEAD 仍停在 #44 之前，#45～#54 全部改动均未提交。

### 1.3 重要说明
- 真实数据库 `backend/pkb.db` 被 `.gitignore` 排除，未被跟踪、未出现在状态中；本轮未触碰。
- 但备份目录 `_ISSUE_PATCHES/ISSUE51/pkb.db.before_migration` 是一个 **数据库备份文件**，属于未跟踪文件，**绝不可提交**。
- 本文 `docs/issue-45-to-54-commit-plan.md` 为本轮新增，生成后未跟踪项由 26 变为 **27**，展开文件由 65 变为 **66**。

---

## 2. 全部文件分类清单

### 2.1 已跟踪修改（24 个）

| 文件路径 | 当前状态 | 所属 Issue | 是否应提交 | 原因 | 依赖关系 |
|---|---|---|---|---|---|
| `README.md` | M | #45/#52/#54 | ✅ 应提交 | 模拟用户说明(#45)、图片视频占位与收录说明(#52)、目录树/文档链接/冲突标记清理(#54) | 与前端用户上下文、收录服务、路由拆分描述一致 |
| `backend/api/router.py` | M | #54 | ✅ 应提交 | 574→28 行，改为纯汇总，仅 `include_router` | **强依赖**：需 4 个新 controller 与 document_service 同时提交，否则 import 失败 |
| `backend/modules/ingest/domain/models.py` | M | #47 + #53 | ✅ 应提交 | Document 加 `is_deleted/deleted_at`(#47)；错题模型迁出并兼容重导出(#53) | 同一文件跨两 Issue，需与 migration、mistake/domain 同提 |
| `backend/modules/ingest/repository/document_repo.py` | M | #47 | ✅ 应提交 | get/list/delete 过滤软删，物理删除改软删除 | 依赖 models 的 is_deleted 字段 |
| `backend/modules/ingest/service/reindex_service.py` | M | #47 | ✅ 应提交 | reindex 排除已删文档 | 同上 |
| `backend/modules/manage/domain/models.py` | M | #51 | ✅ 应提交 | `Tag.creator_id` 字段 | 依赖 migrate_tag_creator 迁移 |
| `backend/modules/manage/service/document_service.py` | M | #47 + #49/#50 + #54 | ✅ 应提交 | 删除生命周期(#47,#54 迁入)、可见性公共函数(#49/#50,#54) | **强依赖**：#54 controller 从此处 import 删除函数与可见性函数 |
| `backend/modules/manage/service/folder_service.py` | M | #47 + #48 + #49 + #54 | ✅ 应提交 | 归属(#48)、收藏(#49)、删除逻辑迁出(#47/#54)、可见性收敛(#54) | 与 document_service 互为配套（删除逻辑从这里迁出） |
| `backend/modules/manage/service/tag_service.py` | M | #51 | ✅ 应提交 | 全局共享标签规则、creator 校验、有关联禁删 | 依赖 models.creator_id |
| `backend/modules/mistake/controller/router.py` | M | #45 + #53 | ✅ 应提交 | Query(user_id)→Depends(get_current_user)(#45)；模型 import 改 mistake.domain(#53) | 同一文件跨两 Issue，依赖 user_context 与 mistake/domain |
| `backend/modules/mistake/service/analytics_service.py` | M | #53 | ✅ 应提交 | 模型 import 改新路径 | 依赖 mistake/domain |
| `backend/modules/mistake/service/knowledge_point_service.py` | M | #53 | ✅ 应提交 | 同上 | 同上 |
| `backend/modules/mistake/service/recommendation_service.py` | M | #53 | ✅ 应提交 | 同上 | 同上 |
| `backend/modules/retrieve/repository/chunk_repo.py` | M | #47 | ✅ 应提交 | 关键词检索排除软删文档 | 依赖 models.is_deleted |
| `backend/modules/retrieve/service/search.py` | M | #47 | ✅ 应提交 | 语义检索 `has(is_deleted==False)` 过滤 | 同上；#46 范围过滤仍未实现，勿改〔当前状态：#46 范围过滤已由后续 PR #56 实现；本行为计划生成时记录，勿改仅指当时不得在这批提交中补做。〕 |
| `backend/shared/db.py` | M | #53 | ✅ 应提交 | init_db 显式注册 mistake 模型 | 依赖 mistake/domain |
| `backend/tests/test_analytics.py` | M | #53 | ✅ 应提交 | 模型 import 改新路径 | 测试，随源码提交 |
| `backend/tests/test_knowledge_point.py` | M | #53 | ✅ 应提交 | 同上 | 同上 |
| `backend/tests/test_recommendation.py` | M | #53 | ✅ 应提交 | 同上 | 同上 |
| `backend/tests/test_search.py` | M | #54 | ✅ 应提交 | 新增语义检索软删测试 | 测试，随检索过滤提交 |
| `docs/architecture.md` | M | #54 | ✅ 应提交 | 架构文档对齐真实代码，新增已实现/未实现/未来设想 | 依赖全部代码改动落地 |
| `frontend/src/App.tsx` | M | #45 | ✅ 应提交 | 模拟用户切换用 MOCK_USERS | 依赖 api.ts 的 MOCK_USERS |
| `frontend/src/api.ts` | M | #45 | ✅ 应提交 | getCurrentUser / MOCK_USERS 统一上下文 | 被 App/MistakeView 依赖 |
| `frontend/src/components/MistakeView.tsx` | M | #45 | ✅ 应提交 | 统一从 getCurrentUser 取当前用户 | 依赖 api.ts |

### 2.2 未跟踪项（26 项，目录折叠口径）

| 文件路径 | 当前状态 | 所属 Issue | 是否应提交 | 原因 | 依赖关系 |
|---|---|---|---|---|---|
| `.workbuddy/` | ??（目录） | 无（工作日志） | ❌ 不提交 | 仅含 `memory/2026-11-16.md` 工作记录，属本地过程数据 | 无 |
| `_ISSUE_PATCHES/` | ??（目录） | 无（历史备份） | ❌ **绝不提交** | 39 个 `.before` 备份文件，其中 `ISSUE51/pkb.db.before_migration` 是数据库备份 | 无 |
| `backend/apply_user_context.py` | ?? | 历史遗留 | ❌ 不提交（待人工确认） | 此前已裁决**不执行**的一次性正则替换脚本；保留但不入库 | 无 |
| `backend/migrations/migrate_document_soft_delete.py` | ?? | #47 | ✅ 应提交 | 幂等迁移：加 is_deleted/deleted_at | 与 models 字段同提 |
| `backend/migrations/migrate_tag_creator.py` | ?? | #51 | ✅ 应提交 | 幂等迁移：加 tags.creator_id | 与 models 字段同提 |
| `backend/modules/agent/controller/router.py` | ?? | #54 | ✅ 应提交 | Agent 域 Router（51 行） | api/router 汇总依赖 |
| `backend/modules/ingest/controller/router.py` | ?? | #54 | ✅ 应提交 | 收录域 Router（66 行） | 同上 |
| `backend/modules/ingest/service/ingest_service.py` | ?? | #52 | ✅ 应提交 | 统一收录流程（295 行，含临时文件/Embedding/补偿） | 被 ingest controller 依赖 |
| `backend/modules/manage/controller/router.py` | ?? | #54 | ✅ 应提交 | 管理域 Router（401 行，正文读取在此） | api/router 汇总依赖 |
| `backend/modules/mistake/domain/` | ??（目录） | #53 | ✅ 应提交 | `models.py`(96 行) 唯一正式定义 + `__init__.py`(空，包标记) | 全项目 import 依赖；空 `__init__.py` 是合法包标记，非无用途空壳 |
| `backend/modules/retrieve/controller/router.py` | ?? | #54 | ✅ 应提交 | 检索域 Router（28 行）；#46 范围过滤仍未实现〔当前状态：#46 范围过滤已由后续 PR #56 实现；本行为计划生成时记录。〕 | api/router 汇总依赖 |
| `backend/shared/user_context.py` | ?? | #45 | ✅ 应提交 | get_current_user 依赖（58 行） | 所有接上下文的 Router 依赖 |
| `backend/tests/test_document_lifecycle.py` | ?? | #47 | ✅ 应提交 | 软删除生命周期 11 用例 | 测试 |
| `backend/tests/test_document_lifecycle_recheck.py` | ?? | #47 | ✅ 应提交 | 补偿/回滚补充 16 用例 | 测试 |
| `backend/tests/test_favorite_access_rules.py` | ?? | #49 | ✅ 应提交 | 收藏可见性 19 用例 | 测试 |
| `backend/tests/test_folder_ownership.py` | ?? | #48 | ✅ 应提交 | 归属规则 19 用例 | 测试 |
| `backend/tests/test_ingest_flow.py` | ?? | #52 | ✅ 应提交 | 收录流程 22 用例 | 测试 |
| `backend/tests/test_issue54_structure.py` | ?? | #54 | ✅ 应提交 | 结构/路由契约 5 用例 | 测试 |
| `backend/tests/test_mistake_data_scope.py` | ?? | #53 | ✅ 应提交 | 错题数据隔离 15 用例 | 测试 |
| `backend/tests/test_public_data_scope.py` | ?? | #50 | ✅ 应提交 | 公开范围/正文权限 15 用例 | 测试 |
| `backend/tests/test_tag_rules.py` | ?? | #51 | ✅ 应提交 | 标签规则 17 用例 | 测试 |
| `backend/tests/test_user_context.py` | ?? | #45 | ✅ 应提交 | 用户上下文单测 4 用例 | 测试 |
| `backend/tests/test_user_context_api.py` | ?? | #45 | ✅ 应提交 | 用户上下文 API 10 用例 | 测试 |
| `docs/issue-45-to-54-acceptance.md` | ?? | 验收记录 | ⚠️ 建议提交（待人工确认） | 本轮新增验收报告，与 architecture/user-stories 同属项目文档，具可追溯价值；是否入库由你决定 | 依赖全部代码落地 |
| `docs/mistake-business-rules.md` | ?? | #53 | ✅ 应提交 | 错题业务规则与统计口径文档 | 与错题实现同提 |
| `docs/user-stories.md` | ?? | #54 | ✅ 应提交 | 用户故事/流程/验收标准（6 个故事） | 与架构文档同提 |
| `docs/issue-45-to-54-commit-plan.md` | ??（本文，新增） | 本次 | ⚠️ 建议提交（待人工确认） | 本计划文档；生成后未跟踪项 26→27 | 无 |

### 2.3 `.gitkeep` 说明（易误判项）
全部 16 个 `.gitkeep`（如 `backend/modules/agent/controller/.gitkeep`、`retrieve/domain/.gitkeep` 等）经 `git ls-files` 核实**均已被跟踪**，不在未跟踪列表中，属历史占位文件，**不是新增代码**，无需任何处理，也不应因目录拆分而误删。

### 2.4 分类汇总
- 应提交：已跟踪 24 个 + 未跟踪正式文件 23 项（含 2 个待人工确认文档）= 核心改动 47 项。
- 不提交：`.workbuddy/`、`_ISSUE_PATCHES/`（含数据库备份）、`apply_user_context.py` 共 3 项。
- 待人工确认：`docs/issue-45-to-54-acceptance.md`、本文提交计划（2 项，倾向提交）。

---

## 3. Issue 依赖关系分析

| Issue | 依赖分析 |
|---|---|
| **#45 用户上下文** | **不能单独提交**。后端 `get_current_user` 与前端 3 文件可独立，但 #45 的 API 层改动（`Query(user_id)`→`Depends`）物理上分布在 `mistake/controller/router.py` 与 #54 新建的各 controller 中；`mistake/controller/router.py` 同一文件还含 #53 的 import 变更。按文件拆分会把 #45 与 #53/#54 撕开。 |
| **#46 搜索范围** | **未实施**，无代码改动，不得写入提交内容，也不得为提交而补做。检索范围过滤仍留待 #46；当前 search/Agent 只接上下文、不过滤范围。〔当前状态：#46 后由 PR #56（`849daad`）独立完成并关闭，未包含在本计划所述提交中；本行为计划生成时（PR #55 合并前）的历史决策。〕 |
| **#47 软删除** | **跨多文件且跨 #54**。models 字段、migration、document_repo、reindex、chunk_repo、search 可成组，但删除生命周期函数体在 #54 从 folder_service **迁入** document_service；#54 的 controller 又从 document_service import 这些函数。单独提交 #47 会导致 #54 前的文件状态不一致。 |
| **#48 文件夹归属 / #49 收藏** | 与 #47 删除逻辑、#54 可见性收敛同处 `folder_service.py`，同一文件内高度交织，无法按 Issue 拆文件。 |
| **#50 正文权限** | 判断逻辑在 #54 新建的 `manage/controller/router.py`，公共函数在 #54 的 `document_service.py`；不可脱离 #54 单独提交。 |
| **#51 标签规则** | models 字段 + migration + tag_service 可成组，但 tag_service 函数签名加了 `user_id`（沿用 #45 的用户上下文口径），且文档/测试独立。逻辑上依赖 #45 建立的上下文模式，但文件内容不强制同提。 |
| **#52 收录重构** | `ingest_service.py` 本身较独立（新增文件），但其调用入口在 #54 新建的 `ingest/controller/router.py`；只提交 service 而不提交 controller 会使功能无入口。 |
| **#53 错题模型迁移** | **必须与兼容重导出同提**。`ingest/domain/models.py` 删除原定义并改为 `from modules.mistake.domain.models import ...`；若只提新文件不提 ingest 兼容改动，旧 import 路径全部失效；`mistake/controller/router.py` 同时含 #45 的 Depends 改动。 |
| **#54 工程整理** | **枢纽依赖**。api/router 拆分依赖 4 个新 controller 与 document_service 迁移；可见性公共函数被 #49/#50 复用；文档与测试描述最终状态。必须与其所依赖的全部改动处于同一可构建状态。 |

**核心结论**：不存在"一个 Issue 一个 commit"的安全拆分边界。多数文件在**同一文件、甚至同一函数层面**混合了多个 Issue 的改动；若按 Issue 拆提交，需 `git add -p` 逐 hunk 操作，且会产生中间提交无法 import/测试失败的状态（例如先提 #54 的 `api/router.py` 而未提新 controller，或先提 #53 新模型而未提 ingest 兼容重导出）。

---

## 4. A/B 两种提交方案对比

| 方案 | 做法 | 优点 | 缺点 | 适用条件 |
|---|---|---|---|---|
| **A. 单个大提交** | 把 #45～#54 全部应提交文件一次提交 | 操作简单；无中间态；每个提交点都可构建、测试全绿；不破坏任何依赖；风险最低 | 提交粒度粗，历史可追溯性弱，回退只能整批 | **当前强烈推荐**（文件高度耦合） |
| **B. 按业务边界拆分** | 按 Issue 或域拆成多个提交 | 历史清晰，便于逐 Issue review/cherry-pick | 需逐 hunk 拆分；中间提交极可能 import 失败/测试失败；拆分操作易出错、可能漏文件；违背"不破坏依赖" | 仅当愿意承担中间态不可构建风险，且逐 hunk 极为谨慎时 |

**折中说明**：若确实希望一定粒度，唯一相对安全的是**按"代码 / 文档"两段拆**（先提全部代码+测试，再提 README/architecture/user-stories/验收报告/本计划），两段都可构建。但这**不是**按业务边界拆分，收益有限；如无特殊要求，仍建议方案 A。

---

## 5. 推荐提交方案

**推荐方案 A：单个原子提交**，包含 #45～#54 全部应提交改动（已跟踪 24 个 + 未跟踪正式文件 23 项，其中 2 份文档待你确认是否纳入）。

理由：
1. 文件级与 hunk 级耦合使按 Issue 拆分不安全；
2. 全量测试已通过（220 passed, 1 skipped），当前工作区是一个**经过验证的完整状态**，整体提交可保留这一可验证性；
3. 符合"不丢失现有工作、不破坏依赖"的硬性要求。

建议提交标题（Conventional Commits）：
```
refactor: unify user context and reorganize modules (#45-#54)
```
（若你更希望突出功能，也可改为 `feat: harden multi-user data isolation and document lifecycle (#45-#54)`。）

---

## 6. 每个 commit 的文件范围与标题

### 方案 A（推荐）：1 个提交

| 顺序 | 建议提交标题 | 包含的 Issue | 文件范围 | 前置依赖 |
|---|---|---|---|---|
| 1 | `refactor: unify user context and reorganize modules (#45-#54)` | #45,#47,#48,#49,#50,#51,#52,#53,#54（**#46 未实施，不含**）〔当前状态：#46 后由 PR #56 独立完成，不在本计划提交内；此处为计划生成时记录。〕 | 第 2.1 节全部 24 个已跟踪修改 + 第 2.2 节标记 ✅/⚠️ 的 23 项未跟踪正式文件 | HEAD 当前状态；工作区测试全绿 |

> 若选择"代码/文档"两段折中方案，见第 7.3 节命令（2 个提交，标题分别为 `refactor: ... (#45-#54)` 与 `docs: add architecture, user stories and acceptance records`）。

---

## 7. 具体执行命令（PowerShell，供后续真正提交时使用）

> 本节仅为**后续执行参考**，本轮**未执行**任何 `git add` / `git commit`。

### 7.1 提交前检查（必做）
```powershell
cd "D:\STUDY\echo\personal-knowledge-base"
git branch --show-current                 # 必须输出 refactor/user-context
git status --short --branch
git diff --cached --stat                  # 必须为空（暂存区干净）
```

### 7.2 方案 A：单提交（推荐）

**第 1 步：显式暂存（逐路径，禁止 `git add .` / `git add -A`）**
```powershell
$files = @(
  "README.md",
  "backend/api/router.py",
  "backend/modules/ingest/domain/models.py",
  "backend/modules/ingest/repository/document_repo.py",
  "backend/modules/ingest/service/reindex_service.py",
  "backend/modules/manage/domain/models.py",
  "backend/modules/manage/service/document_service.py",
  "backend/modules/manage/service/folder_service.py",
  "backend/modules/manage/service/tag_service.py",
  "backend/modules/mistake/controller/router.py",
  "backend/modules/mistake/service/analytics_service.py",
  "backend/modules/mistake/service/knowledge_point_service.py",
  "backend/modules/mistake/service/recommendation_service.py",
  "backend/modules/retrieve/repository/chunk_repo.py",
  "backend/modules/retrieve/service/search.py",
  "backend/shared/db.py",
  "backend/tests/test_analytics.py",
  "backend/tests/test_knowledge_point.py",
  "backend/tests/test_recommendation.py",
  "backend/tests/test_search.py",
  "docs/architecture.md",
  "frontend/src/App.tsx",
  "frontend/src/api.ts",
  "frontend/src/components/MistakeView.tsx",
  "backend/migrations/migrate_document_soft_delete.py",
  "backend/migrations/migrate_tag_creator.py",
  "backend/modules/agent/controller/router.py",
  "backend/modules/ingest/controller/router.py",
  "backend/modules/ingest/service/ingest_service.py",
  "backend/modules/manage/controller/router.py",
  "backend/modules/mistake/domain/__init__.py",
  "backend/modules/mistake/domain/models.py",
  "backend/modules/retrieve/controller/router.py",
  "backend/shared/user_context.py",
  "backend/tests/test_document_lifecycle.py",
  "backend/tests/test_document_lifecycle_recheck.py",
  "backend/tests/test_favorite_access_rules.py",
  "backend/tests/test_folder_ownership.py",
  "backend/tests/test_ingest_flow.py",
  "backend/tests/test_issue54_structure.py",
  "backend/tests/test_mistake_data_scope.py",
  "backend/tests/test_public_data_scope.py",
  "backend/tests/test_tag_rules.py",
  "backend/tests/test_user_context.py",
  "backend/tests/test_user_context_api.py",
  "docs/mistake-business-rules.md",
  "docs/user-stories.md"
)
git add -- $files
```
> 上列**刻意不含** `.workbuddy/`、`_ISSUE_PATCHES/`、`apply_user_context.py`，也不含两份待确认文档（验收报告、本计划）。若你决定纳入这两份文档，在上述数组末尾追加 `"docs/issue-45-to-54-acceptance.md"` 与 `"docs/issue-45-to-54-commit-plan.md"` 即可。

**第 2 步：检查暂存区（确认无备份/日志/脚本混入）**
```powershell
git diff --cached --stat
git diff --cached --name-only
# 以下应无任何输出（有输出说明误暂存）
git diff --cached --name-only | Select-String -Pattern '_ISSUE_PATCHES|\.workbuddy|apply_user_context|pkb\.db'
```

**第 3 步：提交**
```powershell
git commit -m "refactor: unify user context and reorganize modules (#45-#54)"
```

**第 4 步：提交后检查**
```powershell
git status --short --branch
git log -3 --oneline
```

### 7.3 折中方案：代码 / 文档两段提交（可选，非推荐）

按 7.2 第 1 步的数组**去掉** 4 份文档（`docs/architecture.md`、`docs/mistake-business-rules.md`、`docs/user-stories.md`、`docs/issue-45-to-54-acceptance.md`、本计划）后暂存并提交：
```powershell
git commit -m "refactor: unify user context and reorganize modules (#45-#54)"
```
再单独暂存文档并提交：
```powershell
git add -- "docs/architecture.md" "docs/mistake-business-rules.md" "docs/user-stories.md" "docs/issue-45-to-54-acceptance.md" "docs/issue-45-to-54-commit-plan.md"
git diff --cached --stat
git commit -m "docs: add architecture, user stories and acceptance records"
git status --short --branch
git log -3 --oneline
```

---

## 8. 提交前检查清单

- [ ] 分支确认为 `refactor/user-context`，未切分支、未动 main。
- [ ] 暂存区起始为空（`git diff --cached --stat` 无输出）。
- [ ] 使用明确路径暂存，**未**用 `git add .` 或 `git add -A`。
- [ ] 暂存区不含 `_ISSUE_PATCHES/`、`.workbuddy/`、`apply_user_context.py`、`pkb.db`。
- [ ] 两份待确认文档（验收报告、本计划）是否纳入已由你决定。
- [ ] 后端全量测试通过（220 passed, 1 skipped），前端 build/lint 通过。
- [ ] 未运行任何数据库迁移；未修改 `backend/pkb.db`。
- [ ] 提交后立即执行 `git status --short --branch` 与 `git log -3 --oneline` 核验。
- [ ] 不执行 `git push`（除非另行指示）。

---

## 9. 风险和注意事项

1. **备份目录含数据库备份**：`_ISSUE_PATCHES/ISSUE51/pkb.db.before_migration` 是数据库备份文件，误提交会泄露/污染仓库，必须排除。
2. **遗留脚本**：`apply_user_context.py` 此前裁决"不执行、仅保留"，不要因它存在而 `add` 或执行。
3. **空 `__init__.py`**：`mistake/domain/__init__.py` 为空但属合法 Python 包标记，应提交（与 Issue #54"不造无用途空壳"不冲突——它是 import 所需的包标记）。
4. **`.gitkeep` 已跟踪**：不要删除或改动；它们不是新增代码。
5. **#46 未实施**：提交信息或文档中不得声称搜索范围过滤已完成；当前 search/Agent 仍不过滤所有者/公开范围。〔当前状态：该约束针对本计划所述提交（PR #55 合并前）有效；#46 后由 PR #56 独立完成并合并，搜索范围过滤现已实现。本条为历史记录。〕
6. **中间态风险**：若强行按 Issue 拆分，中间提交可能 import 失败或测试失败；方案 A 规避此风险。
7. **待人工确认**：`docs/issue-45-to-54-acceptance.md` 与本计划文档是否入库由你决定；本计划倾向纳入（属项目文档，具可追溯价值）。
8. **本轮合规**：本次仅新增本文档，未执行任何 git 写操作、未修改任何已有文件、未碰真实数据库、未开始 #55。

---

## 10. 摘要（便于审核）

- 应提交：**已跟踪 24 个 + 未跟踪正式文件 23 项**；不提交：**3 项**（备份目录、工作日志、遗留脚本）；待确认：**2 份文档**。
- 推荐：**方案 A，1 个提交**，标题 `refactor: unify user context and reorganize modules (#45-#54)`。
- 不能安全按 Issue 拆分，原因：文件/hunk 级跨 Issue 耦合（详见第 3 节）。
- 未发现意外改动；Git 状态除新增本文档外与盘点时一致。
