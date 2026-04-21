## 后端说明文档

本后端基于 `Flask + SQLAlchemy + PostgreSQL`，主要包含：

- 学生与画像基础 CRUD 接口
- 数值聚类流程（KMeans）
- 文本聚类流程（BERTopic，中文模型 + 哈工大停词表）
- 一键执行脚本（同时跑 numeric + text）
- 统一 API 返回规范（`ok/message/data/meta/error`）

---

## 1）环境准备

### 创建并激活 conda 环境

```bash
conda env create -f environment.yaml
conda activate ideological_profiling
```

### 配置数据库连接

Windows 示例：

```bash
setx DATABASE_URL "postgresql+psycopg2://<user>:<password>@127.0.0.1:5432/ideological_profiling_sys"
```

执行 `setx` 后请重新打开终端。

---

## 2）初始化数据库与示例数据

```bash
python -m scripts.init_db
python -m scripts.generate_mock_data
```

---

## 3）启动后端 API

```bash
python -m api_server.app
```

默认监听：
- host: `127.0.0.1`
- port: `5000`

---

## 4）运行聚类流程

### 4.1 统一执行（推荐）

同时执行数值聚类和文本聚类：

```bash
python -m scripts.run_all_clustering --period 2026-04
```

常见参数示例：

```bash
python -m scripts.run_all_clustering --period 2026-04 --n-clusters 3 --normalization minmax --no-generate-plot
```

### 4.1.1 统一更新 profile + warning 分（推荐定时任务）

一次执行：数值聚类 + 文本聚类 + warning 分重算。

```bash
python -m scripts.run_profile_warning_refresh --period 2026-04
```

如需提升夜间任务速度（不生成图）：

```bash
python -m scripts.run_profile_warning_refresh --no-generate-plot
```

### 4.2 仅运行数值聚类

```bash
python -m services.numeric_clustering_service --period 2026-04 --n-clusters 3 --normalization minmax
```

### 4.3 仅运行文本聚类（BERTopic）

```bash
python -m services.text_clustering_service --period 2026-04 --stopwords-path data/hit_stopwords.txt
```

---

## 5）API 规范与接口

### 5.1 统一响应格式

所有接口统一返回结构：

- `ok`: 成功/失败
- `message`: 响应信息
- `data`: 业务数据
- `meta`: 附加信息（可选，常用于分页、period）
- `error`: 错误信息（失败时）

### 5.2 核心接口

- `GET /api/health`
- `GET /api/students`
- `POST /api/students`
- `GET /api/students/<student_id>`
- `PUT /api/students/<student_id>`
- `DELETE /api/students/<student_id>`
- `GET /api/students/<student_id>/profile`
- `PUT /api/students/<student_id>/profile`

### 5.3 聚类相关接口

- `POST /api/clustering/run-all`  
  从 API 触发 numeric + text 全流程

- `GET /api/profiles?period=2026-04&limit=50&offset=0`  
  查询画像列表（包含学生基础信息）

- `GET /api/clustering/summary?period=2026-04`  
  查询数值簇分布与文本主题分布

详细请求/响应示例见：`docs/api_examples.md`

---

## 6）中文 BERTopic 配置说明

文本聚类默认配置为：

- embedding 模型：`BAAI/bge-base-zh-v1.5`
- 分词：`jieba`
- 停词表：哈工大停词表（`data/hit_stopwords.txt`）

如主题关键词质量不理想，可优先调：

- `--min-content-len`
- `--min-topic-size`
- 停词表内容（补充高频虚词/标点）

---

## 7）关键目录与文件

- `api_server/app.py`：Flask API 入口与路由
- `scripts/run_all_clustering.py`：统一聚类执行脚本
- `services/numeric_clustering_service.py`：数值聚类流程
- `services/text_clustering_service.py`：文本聚类流程（BERTopic）
- `services/preprocessor.py`：数值/文本预处理
- `services/profile_query_service.py`：画像查询与聚类统计查询
- `services/clustering_orchestration_service.py`：聚类编排服务
- `database/models.py`：SQLAlchemy 数据模型
- `database/profile_repository.py`：画像 upsert/query
- `data/hit_stopwords.txt`：中文停词表

---

## 8）常见问题排查

### 8.1 BERTopic 报 `empty vocabulary`

常见原因：中文分词和停词过滤后有效词为空。  
建议：

- 确认使用 `jieba` 分词
- 检查停词表路径是否正确
- 降低 `--min-content-len`
- 适当降低 `--min-topic-size`

### 8.2 HuggingFace 下载提示 `UNEXPECTED`

多数情况下可忽略（模型结构键不完全一致提示）。  
若下载慢/超时，建议配置 `HF_TOKEN`。

### 8.3 SQLAlchemy DetachedInstanceError

已在 `database/db.py` 中配置 `expire_on_commit=False`，用于避免常见 detached 读取问题。

---

## 9）如何上传到 GitHub

> 建议在项目根目录（不是 `backend` 子目录）执行以下命令。

### 9.1 检查变更

```bash
git status
```

### 9.2 提交代码

```bash
git add .
git commit -m "完善后端聚类流程与API文档"
```

### 9.3 推送到远程仓库

如果远程已配置：
```bash
git push
```

如果还没配置远程（首次）：
```bash
git remote add origin <你的仓库URL>
git branch -M main
git push -u origin main
```

### 9.4 提交前建议确认

- `backend/.gitignore` 已生效（避免把 `results/` 输出和缓存上传）
- 本地 API 可启动：`python -m api_server.app`
- 聚类脚本可运行：`python -m scripts.run_all_clustering --period 2026-04`

---

## 10）每天凌晨自动更新（Windows 任务计划）

在项目根目录执行（按你的 Python 环境路径调整）：

```bash
schtasks /Create /SC DAILY /ST 00:00 /TN "IdeologicalProfileRefresh" /TR "\"D:\anaconda3\envs\ideological_profiling\python.exe\" -m scripts.run_profile_warning_refresh --no-generate-plot" /F
```

检查任务：

```bash
schtasks /Query /TN "IdeologicalProfileRefresh" /V /FO LIST
```

手动触发一次：

```bash
schtasks /Run /TN "IdeologicalProfileRefresh"
```

