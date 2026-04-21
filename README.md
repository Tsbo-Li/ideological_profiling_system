# 数智育人研判平台（Ideological Profiling System）

面向高校辅导员的研判与处置工作台：在保证隐私脱敏的前提下，对学生画像（数值特征聚类 + 文本主题聚类）、预警分与处置闭环、以及“热点 + 群体画像”的内容策划生成提供一体化支撑。

> 说明：本仓库为课程/项目型实现，默认运行在本地开发环境；生产化部署需补齐鉴权、审计、数据合规与运维体系。

---

## 功能概览

- **工作台总览**
  - KPI（在册学生、预警关注、高风险、处理中/已闭环）
  - 群体聚类分布（雷达）
  - 近 7 日预警触发趋势（折线）
  - 待关注预警事件（当前仅展示高风险）
  - 近期热点榜单（抖音/B站，支持分页、可跳原链接）

- **群体画像分析**
  - 二维降维散点（数值/文本特征投影）
  - 群体关键词词云（加权）
  - 群体画像卡片（示例学生可跳转个体画像）

- **学生个体画像**
  - 标签词云（文本关键词 + 画像标签）
  - 预警分与处置状态展示
  - **预警处置登记**（处理中/已闭环/已忽略 + 处置记录）
  - AI 谈话建议（流式输出，隐私脱敏）

- **内容策划与生成**
  - 长文草稿（公众号/班会）
  - 短视频内容草稿（脚本与分镜 / 文生视频提示词）
  - **流式生成 + 断点续传（SSE）**
  - 生成结果入库与历史草稿回溯（生成中也可回到历史继续追踪）

---

## 技术栈

- **前端**：Vue 3 + Vite + TypeScript + ECharts + Three.js
- **后端**：Flask + Flask-CORS + SQLAlchemy
- **数据库**：PostgreSQL（SQLAlchemy URL）
- **聚类**：
  - 数值聚类：KMeans（sklearn）
  - 文本聚类：BERTopic（SentenceTransformers + jieba + HIT stopwords）
- **流式输出**：Server-Sent Events（SSE）

---

## 目录结构

```text
ideological_profiling_system/
  backend/                 # Flask API + 聚类/画像/生成服务
  frontend/                # Vue 工作台
  docs/                    # 项目文档（前后端交互等）
```

---

## 快速开始（本地开发）

### 1）后端

进入 `backend/`：

```bash
conda env create -f environment.yaml
conda activate ideological_profiling
```

配置数据库连接（Windows）：

```bash
setx DATABASE_URL "postgresql+psycopg2://<user>:<password>@127.0.0.1:5432/ideological_profiling_sys"
```

初始化数据库与示例数据：

```bash
python -m scripts.init_db
python -m scripts.generate_mock_data
```

启动后端 API：

```bash
python -m api_server.app
```

默认监听 `127.0.0.1:8000`（可用 `PORT` 覆盖）。

### 2）前端

进入 `frontend/`：

```bash
npm install
npm run dev
```

默认前端：`http://127.0.0.1:5173`  
开发代理：`frontend/vite.config.ts` 将 `/api` 转发到后端。

---

## 关键脚本与定时任务

### 一键更新画像 + warning 分（推荐每天凌晨跑）

在 `backend/` 下执行：

```bash
python -m scripts.run_profile_warning_refresh --no-generate-plot
```

Windows 任务计划（示例）见 `backend/README.md`。

---

## 环境变量（常用）

### 数据库

- `DATABASE_URL`：PostgreSQL SQLAlchemy URL（必需）

### 日志

- `LOG_LEVEL`：默认 `INFO`

### 模型/LLM（DeepSeek / OpenAI-compatible）

后端已支持从环境变量读取模型配置（以 OpenAI 兼容接口方式调用）。常见配置：

- `AI_BASE_URL` 或 `DEEPSEEK_BASE_URL`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY`
- `AI_MODEL` 或 `DEEPSEEK_MODEL`

> 注意：调用外部模型时会对学生隐私字段做脱敏过滤（不传学号/姓名等直接标识符）。

---

## API 与前后端交互

- 前后端交互说明：`docs/前后端交互说明.md`
- 后端接口与运行说明：`backend/README.md`
- 示例请求：`backend/docs/api_examples.md`

---

## 常见问题

- **页面图表第一次进入不显示？**  
  本项目已对 ECharts 的 DOM 挂载时机做了修复（`nextTick`/watch 容器挂载后再渲染）。如仍出现，优先检查浏览器缩放/容器是否为 0 高度。

- **文本聚类首次运行很慢/下载模型失败？**  
  SentenceTransformers 需要下载 embedding 模型，建议提前联网下载或配置镜像/缓存。

---

## License

如需开源协议请在此补充（例如 MIT / Apache-2.0 / GPL-3.0）。目前默认“仅项目演示/教学用途”。

