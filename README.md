# 个人知识库管理系统 (personal-knowledge-base)

> 把散落的文档、笔记、链接丢进来，用自然语言提问，答案带出处。

[![CI](https://github.com/epoch-fresh-2026/personal-knowledge-base/actions/workflows/ci.yml/badge.svg)](https://github.com/epoch-fresh-2026/personal-knowledge-base/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev/)

## 📖 解决什么问题

收藏夹吃灰、笔记散落各处，信息越攒越多却越没法用。
这个系统让你：随手丢进去 → 一句话问出来 → 知道答案从哪来。

## ✨ 功能演示

- **📄 多源上传**：支持 Markdown、PDF、Word、代码文件，以及图片/视频的物理归档。
- **🤖 智能问答**：基于私有资料库的 Agent 混合检索，带强制防幻觉与精准溯源。
- **🌐 社区共享**：支持文档/收藏夹设为公开，广场浏览他人分享，一键收藏。
- **📁 资料管理**：自定义收藏夹分类，支持文件夹改名、删除、文件移出与多模态在线预览。
- **👥 多用户隔离**：模拟多用户身份切换，严格的私有数据权限控制。

*(此处插入 1 张主界面截图或 GIF)*

## 🏗️ 技术栈与架构

| 层 | 选型 |
|---|---|
| 前端 | React + Vite + TypeScript |
| 后端 | Python 3.11 + FastAPI |
| 数据库 | SQLite（开发阶段） |
| 检索 | **jieba 关键词倒排 + 混合检索** |
| LLM | DeepSeek API |
| Agent | **自研步进式状态机（已落地）** |

*(此处可插入简化的架构图或 Mermaid 流程图)*

## 🚀 如何本地运行

### 1. 环境准备
- Python 3.11+
- Node.js 18+
- 一个 DeepSeek API Key（[获取地址](https://platform.deepseek.com/)）

### 2. 启动后端
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
# 配置环境变量：复制 .env.example 为 .env，并填入你的 API Key
cp .env.example .env
# 启动后端
uvicorn main:app --reload
```
> 后端跑在 `http://localhost:8000`，API 文档见 `http://localhost:8000/docs`。

### 3. 启动前端
```bash
cd frontend
npm install
npm run dev
```
> 前端跑在 `http://localhost:5173`。

## 🗺️ Roadmap（后续演进计划）
- [ ] **向量检索**：接入 `pgvector`，实现纯向量语义检索与 RRF（倒数排名融合）。
- [ ] **Agent 深度编排**：引入更成熟的 Agent 框架（如 LangGraph），支持更复杂的多步推理与自动纠错。
- [ ] **多模态扩展**：支持 OCR 提取图片文字，以及视频 ASR 语音转文字。

## 📚 项目文档与资源
- [产品需求文档 (Issue #1)](https://github.com/epoch-fresh-2026/personal-knowledge-base/issues/1)
- [架构设计文档 (Issue #2)](https://github.com/epoch-fresh-2026/personal-knowledge-base/issues/2)

## 📜 License
This project is licensed under the MIT License.
