# Issue #45～#54 整体验收记录与待提交改动盘点

> 报告生成日期：2026-11-17
> 当前分支：`refactor/user-context`
> 项目目录：`D:\STUDY\echo\personal-knowledge-base`
> 报告性质：只读盘点 + 新增本文档。本轮未修改任何已有项目代码、文档、测试、备份或真实数据库。

---

## 1. 项目背景与本轮整理目标

个人知识库项目按 GitHub Issue #45～#54 顺序逐项修复与整理。经逐 Issue 实施与验收，#45～#54 均已完成开发并通过各自验收；其中 #46 按既定计划**未实施**（检索范围问题保留待办）。

本轮目标：
1. 形成一份完整、准确、可追溯的 #45～#54 验收记录；
2. 盘点当前工作区全部尚未提交的改动，区分归属、类别与是否应提交；
3. 核对当前代码、测试与文档是否存在明显矛盾；
4. 记录测试结果、风险遗留与后续建议。

本报告所有结论均来自本次实际执行的 Git 命令、diff 抽查、测试复跑与文档阅读，未依据文件名单独推断归属。

---

## 2. Issue #45～#54 逐项验收结果

| Issue | 主题 | 核心改动 | 关键业务规则 | 回归测试 | 最终验收状态 |
|---|---|---|---|---|---|
| #45 | 用户上下文统一 | 后端 `shared/user_context.py` 提供 `get_current_user`（`Depends`）；前端 `api.ts`/`App.tsx`/`MistakeView.tsx` 统一 `localStorage.currentUser` + `MOCK_USERS`；15 个接口接入当前用户上下文 | 后端不静默使用默认用户；前端模拟用户可回退张三；公开接口不强制 user_id | `test_user_context.py`(4)、`test_user_context_api.py`(10) | ✅ 已验收 |
| #46 | 搜索范围问题 | **未实施**（按既定计划保留） | search / Agent 当前**不**按所有者或公开范围限定结果，留待 #46 | 无（本 Issue 未实施） | ⏸ 未实施／保留待办 |
| #47 | 文档软删除与生命周期 | `ingest/models.py` 加 `is_deleted/deleted_at`；迁移脚本；`document_repo`/`reindex`/`search`/`chunk_repo` 过滤软删除；删除逻辑（后于 #54 迁入 `document_service`）含孤立文件 write-ahead 补偿清单 | 软删除/恢复/永久删除仅所有者；软删文档不出现在列表、正文、收藏、标签、文件夹与检索；孤立文件清单预登记→确认→清理+幂等重试 | `test_document_lifecycle.py`(11)、`test_document_lifecycle_recheck.py`(16) | ✅ 已验收 |
| #48 | 文件夹与文档归属 | `folder_service.py` 归属校验：仅自有未删文档可加入自有文件夹；公开文件夹不再批量改文档 is_public | 规则 A：他人公开文档也不得加入自己文件夹；私有文件夹对非所有者拒绝；文件夹公开与文档公开是两个独立状态 | `test_folder_ownership.py`(19) | ✅ 已验收 |
| #49 | 收藏规则 | `folder_service.py` 收藏新增/取消/列表：可收藏自有或公开资源；取消只删关系；列表隐藏不可见资源 | 收藏是私有关系，不复制不改归属；新增须可见；列表按当前浏览者过滤软删/转私有资源 | `test_favorite_access_rules.py`(19) | ✅ 已验收 |
| #50 | 文档内容访问权限 | 正文读取改为"所有者本人 OR 公开文档"可读，他人私有返回 404（不泄露存在性）；与公开列表/收藏同口径 | 正文可见性：`未删除 且 (所有者 ∨ 公开)`；#54 收敛为公共函数 | `test_public_data_scope.py`(15) | ✅ 已验收 |
| #51 | 全局共享标签 | `Tag.creator_id` + 迁移脚本；名称 `strip+casefold` 全局唯一；他人可对自有文档使用共享标签；标签文档按可见范围过滤；置顶全局生效 | 历史 `creator_id=NULL` 标签无人可删；仅创建者可删；**有关联文档的标签禁止删除**（Issue 原文裁决） | `test_tag_rules.py`(17) | ✅ 已验收 |
| #52 | 知识采集与 Embedding | 新增 `ingest/service/ingest_service.py`；收录流程临时文件→解析→切分→Embedding→正式文件迁移→单事务；共享 Embedding `shared/embedding.py`；README 说明图片/视频仅占位 | 空内容拒绝；URL 校验 http/https + hostname，保留原始 source_url；清理失败记录路径/阶段/原因，不静默跳过 | `test_ingest_flow.py`(22) | ✅ 已验收 |
| #53 | 错题模块归属与统计 | 新增 `mistake/domain/models.py` 为 `Mistake`/`MistakeReviewRecord` 唯一定义，ingest 侧兼容重导出；`shared/db.py` 显式注册；router+3 service 改新 import | 错题总数=实际记录；`total_reviews` 累计字段 vs `recorded_review_count` 记录条数；趋势 UTC；推荐仅 pending/reviewing，权重/阈值/排序锁定 | `test_mistake_data_scope.py`(15)、`docs/mistake-business-rules.md` | ✅ 已验收 |
| #54 | 工程整理 | 路由按业务域拆分（4 个 controller + 原有 mistake），`api/router.py` 缩为纯汇总；删除逻辑迁入 `document_service`；可见性公共函数；文档更新；语义检索软删测试补齐 | 路径/方法/契约不变（39 路径冻结）；#47 删除语义不变；#49/#50 复用同一可见性函数；检索范围仍留待 #46 | `test_issue54_structure.py`(5) + 新增 `test_search.py::test_semantic_search_excludes_soft_deleted_document` | ✅ 已验收 |

### 矛盾排查结论
- 本次抽查了 `document_repo.py`、`reindex_service.py`、`manage/domain/models.py`、`shared/db.py`、`mistake/controller/router.py`、3 个 mistake service、`chunk_repo.py`、`search.py`、`api/router.py`、前端 3 文件的实际 diff，改动内容与上述归属一致，未发现明显矛盾。
- `api/router.py` 已确认注册 mistake → ingest → retrieve → agent → manage 五个域路由，`main.py` 以 `/api/v1` 前缀统一挂载。
- #54 专项核查确认：可见性公共函数 `is_document_visible_to_user` / `visible_document_condition` 被 #49、#50 复用；`tag_service` 与 `folder_service` 中若干独立判断属既定业务规则（公开入口/归属口径），条件一致，未强行统一；检索范围未改。

---

## 3. 已确认的核心业务规则（汇总）

- **用户上下文（#45）**：后端统一 `get_current_user` 依赖；前端模拟用户仅用于数据隔离，非真实认证。
- **文档生命周期（#47）**：软删除/恢复/永久删除仅所有者；软删文档从所有列表、正文、收藏、标签、文件夹、检索中排除；孤立文件采用 write-ahead 清单 + 崩溃自愈 + 幂等重试，文件清理失败不回滚已提交数据库。
- **归属（#48）**：仅自有未删文档可加入自有文件夹；他人公开文档不可加入；公开文件夹不批量改文档公开状态。
- **收藏（#49）**：可收藏自有或公开资源；取消只删关系；列表隐藏不可见资源。
- **正文（#50）**：`未删除 且 (所有者 ∨ 公开)` 可读，他人私有 404。
- **标签（#51）**：全局共享、名称规范化唯一、置顶全局；仅创建者可删且必须无关联文档；历史无创建者标签无人可删。
- **收录（#52）**：共享 Embedding 单实现；临时文件事务化迁移；失败补偿可追踪；图片/视频仅占位。
- **错题（#53）**：模型归属 mistake 域；统计/趋势（UTC）/推荐口径见 `docs/mistake-business-rules.md`；跨用户 API 隔离经真实路由集成测试验证。
- **工程边界（#54）**：api 层只做适配与汇总；业务规则在 service；可见性口径单一定义；检索范围过滤**不在**本次范围。

---

## 4. 后端与前端测试结果

本次在报告生成时**重新运行**了后端全量 pytest 与前端 build/lint（仅运行测试，未改代码或数据库），结果与既有记录一致。

| 项目 | 命令 | 执行目录 | 结果 |
|---|---|---|---|
| 后端全量 pytest | `backend/.venv/Scripts/python.exe -m pytest backend -q` | `D:\STUDY\echo\personal-knowledge-base` | **220 passed, 1 skipped**（25.04s） |
| 前端生产构建 | `npm run build` | `frontend/` | 通过（82 modules transformed，built in 3.29s） |
| 前端 lint | `npm run lint` | `frontend/` | **0 warnings, 0 errors**（14 files, 116 rules） |
| #54 新增语义检索软删测试 | `test_search.py::test_semantic_search_excludes_soft_deleted_document` | 项目根目录（pytest） | **1 passed**（此前单跑 -v 确认；本次含于全量 220 中） |
| 关键保留测试（此前单独复跑） | `test_cross_user_operations_are_rejected`、`test_shared_embedding_is_single_implementation`、`test_no_duplicate_vendor_request_implementation` | 项目根目录 | 均 PASSED（函数存在性本次亦已核验） |

- 虚拟环境实际位于 `backend/.venv`（项目根目录无 `.venv`）；`pytest.ini` 位于 `backend/`。
- 全量 1456 条 warning 均为既有告警（`datetime.utcnow()`、`datetime.utcnow` 在测试 fixture、SQLAlchemy SAWarning、Starlette httpx deprecation），**非本次重构缺陷**。

---

## 5. 当前 Git 分支和工作区状态

**分支**：`refactor/user-context`（与预期一致）。

**最近 5 次提交**（均为历史提交，本轮无新提交）：
```
4224bf5 docs: add real-world learning scenario to README (#44)
42a3c22 Update README.md
16eac12 feat: complete tag management UI (#43)
fe699e7 Update README.md
6e8e087 feat: add embedding hybrid search (#42)
```

**暂存区**：`git diff --cached --stat` 为空，无任何已暂存改动。

**已跟踪文件修改（24 个，`git diff --stat`：1081 insertions，902 deletions）**——均为 #45～#54 改动：

| 文件 | 归属 Issue（依据 diff 内容） |
|---|---|
| `README.md` | #52（Embedding 说明）/ #54（目录树、文档链接、冲突标记清理） |
| `backend/api/router.py` | #54（566→28 行，改为纯路由汇总） |
| `backend/modules/ingest/domain/models.py` | #47（软删字段）/ #53（错题模型兼容重导出） |
| `backend/modules/ingest/repository/document_repo.py` | #47（get/list/delete 改为过滤软删 + 软删除） |
| `backend/modules/ingest/service/reindex_service.py` | #47（reindex 排除已删文档） |
| `backend/modules/manage/domain/models.py` | #51（Tag.creator_id） |
| `backend/modules/manage/service/document_service.py` | #47 + #54（删除生命周期迁入、可见性公共函数） |
| `backend/modules/manage/service/folder_service.py` | #47/#48/#49 + #54（归属、收藏、可见性收敛） |
| `backend/modules/manage/service/tag_service.py` | #51（全局标签规则） |
| `backend/modules/mistake/controller/router.py` | #45（Depends 用户上下文）+ #53（模型 import 迁移） |
| `backend/modules/mistake/service/{analytics,knowledge_point,recommendation}_service.py` | #53（模型 import 迁移） |
| `backend/modules/retrieve/repository/chunk_repo.py` | #47（关键词检索排除软删文档） |
| `backend/modules/retrieve/service/search.py` | #47（语义检索排除软删文档） |
| `backend/shared/db.py` | #53（init_db 显式注册 mistake 模型） |
| `backend/tests/test_analytics.py`、`test_knowledge_point.py`、`test_recommendation.py` | #53（import 改为新模型路径） |
| `backend/tests/test_search.py` | #54（新增语义检索软删测试） |
| `docs/architecture.md` | #54（架构文档对齐真实代码） |
| `frontend/src/App.tsx`、`api.ts`、`components/MistakeView.tsx` | #45（用户上下文统一） |

**未跟踪文件（`??`，共 26 项；其中此前已有 25 项，本轮新增验收报告 1 项）**：

- 新增测试文件（11）：`test_document_lifecycle.py`、`test_document_lifecycle_recheck.py`、`test_favorite_access_rules.py`、`test_folder_ownership.py`、`test_ingest_flow.py`、`test_issue54_structure.py`、`test_mistake_data_scope.py`、`test_public_data_scope.py`、`test_tag_rules.py`、`test_user_context.py`、`test_user_context_api.py`
- 新增源码/迁移（按 Issue）：`shared/user_context.py`(#45)、`migrations/migrate_document_soft_delete.py`(#47)、`migrations/migrate_tag_creator.py`(#51)、`ingest/service/ingest_service.py`(#52)、`mistake/domain/`(#53)、4 个 `controller/router.py`(#54)
- 新增文档（3）：`docs/mistake-business-rules.md`(#53)、`docs/user-stories.md`(#54)、本报告 `docs/issue-45-to-54-acceptance.md`（本轮新增）
- **不应提交的目录/文件**：`.workbuddy/`（仅含工作日志 `memory/2026-11-16.md`）、`_ISSUE_PATCHES/`（11 个 Issue 备份目录，39 个文件）、`backend/apply_user_context.py`（历史遗留一次性脚本，此前裁决**不执行**，仅保留）

**意外的修改**：未发现。所有已跟踪修改与未跟踪文件均可归属到 #45～#54 或明确的备份/遗留项。

---

## 6. 尚未解决的问题与风险

1. **#46 检索访问范围过滤（明确留给 #46）**：`search` / Agent 当前只接入用户上下文，不按所有者或公开范围限定结果。证据：`retrieve/controller/router.py` 注释"仅接入当前用户上下文；检索范围过滤规则由 #46 实现"，`search.py` 仅有软删文档排除（#47）。**不要误记为已解决。**
2. **历史 warning（非本次缺陷）**：`datetime.utcnow()` 废弃告警、SQLAlchemy SAWarning（Subquery coercing to select）、Starlette `httpx` deprecation。属既有技术债，不影响功能与验收。
3. **真实库历史孤儿数据**：此前核查发现真实库存在指向不存在 mistake_id 的历史复习记录（未清理）；本轮按要求未触碰真实库 `backend/pkb.db`（该文件被 `.gitignore` 排除、未被 git 跟踪）。
4. **SQLite 外键未启用**：ORM 级联删除依赖 SQLAlchemy relationship；应避免对相关模型使用 bulk delete 绕过 ORM。
5. **可能需要人工确认的规则**：标签删除规则曾有一次方向调整，最终裁决恢复 Issue 原文"有关联禁删"；收藏/标签/文件夹的独立可见性判断经专项核查确认条件一致，如后续要统一需单独评审。
6. **认证边界**：`user_id` 为演示用模拟身份，客户端可伪造，不构成安全边界；生产化需服务端认证授权。

---

## 7. 待提交文件清单及文件归属判断

**应纳入提交（#45～#54 正式改动）**：
- 已跟踪修改 24 个（见第 5 节表，均为 #45～#54 实际改动）。
- 新增正式源码/迁移/文档：
  - `backend/shared/user_context.py`(#45)
  - `backend/migrations/migrate_document_soft_delete.py`(#47)、`migrate_tag_creator.py`(#51)
  - `backend/modules/ingest/service/ingest_service.py`(#52)
  - `backend/modules/mistake/domain/`(#53)
  - `backend/modules/{ingest,retrieve,agent,manage}/controller/router.py`(#54)
  - 11 个新增测试文件（#47～#54，见第 5 节）
  - `docs/mistake-business-rules.md`(#53)、`docs/user-stories.md`(#54)、`docs/issue-45-to-54-acceptance.md`（本轮）

**不应纳入提交（需人工判断/已裁决保留）**：
- `_ISSUE_PATCHES/`（备份目录，39 文件）——备份性质，不提交。
- `.workbuddy/`（工作日志）——本地工作数据，不提交。
- `backend/apply_user_context.py`——历史遗留一次性脚本，此前裁决不执行、仅保留；是否提交需人工决定（建议不提交或单独归档）。

**判断依据**：结合实际 diff 内容（注释中的 Issue 编号、函数语义、import 变更）+ 既有验收记录 + 此前裁决，而非仅凭文件名。

---

## 8. 后续建议

1. 提交前由负责人确认 `backend/apply_user_context.py` 与 `_ISSUE_PATCHES/`、`.workbuddy/` 的处理方式（建议均不纳入代码提交；如需版本化备份另行归档）。
2. #46 检索范围规则单独排期，明确"仅本人 + 公开"口径后再实施，并补充相应回归测试；避免与 #50 正文口径混淆。
3. 生产化前处理认证授权、CORS 收窄与密钥管理；评估 SQLite 外键启用或文档中明确 ORM 级联的约束。
4. 历史 warning 作为技术债清单单独跟踪，不并入本次 Issue 验收结论。
5. 如需提交，建议按 Issue 逻辑分组或一次性提交全部 #45～#54 改动， commit message 明确范围；本轮**未执行**任何提交。

---

## 9. 本轮只读合规声明

本轮严格遵守限制：未修改任何已有项目代码、README、architecture、user-stories、测试文件；未删除或覆盖任何备份；未修改真实数据库 `backend/pkb.db`；未运行迁移；未执行 `git reset/clean/restore`；未切换分支；未提交、推送、合并；未修改 main；未开始 #55。唯一写入为新增本报告 `docs/issue-45-to-54-acceptance.md`。发现的问题仅记录，未自行修复。
