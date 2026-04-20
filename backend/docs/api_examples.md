## API 请求与响应示例

本文档给出前端常用接口的请求与响应样例。  
统一响应结构：

```json
{
  "ok": true,
  "message": "success",
  "data": {},
  "meta": {},
  "error": null
}
```

> 失败时：`ok=false`，并返回 `error`。

---

## 1) 健康检查

### 请求
`GET /api/health`

### 响应示例
```json
{
  "ok": true,
  "message": "success",
  "data": {
    "service": "backend",
    "status": "healthy"
  }
}
```

---

## 2) 获取学生列表

### 请求
`GET /api/students?limit=20&offset=0`

### 响应示例
```json
{
  "ok": true,
  "message": "success",
  "data": [
    {
      "id": 1,
      "student_no": "20260001",
      "name": "学生1",
      "gender": "男",
      "age": 20,
      "grade": "大二",
      "major": "计算机",
      "gpa": 3.45
    }
  ],
  "meta": {
    "limit": 20,
    "offset": 0
  }
}
```

---

## 3) 一键执行聚类流程

### 请求
`POST /api/clustering/run-all`

```json
{
  "period": "2026-04",
  "n_clusters": 3,
  "normalization": "minmax",
  "min_content_len": 5,
  "min_topic_size": 5,
  "nr_topics": null,
  "embedding_model": "BAAI/bge-base-zh-v1.5",
  "stopwords_path": "data/hit_stopwords.txt",
  "persist_to_db": true,
  "generate_plot": true
}
```

### 响应示例
```json
{
  "ok": true,
  "message": "success",
  "data": {
    "numeric": {
      "rows": 20,
      "n_clusters": 3,
      "label_tags": {
        "0": "高活跃（成绩+正确率驱动）",
        "1": "中活跃（绩点+签到驱动）",
        "2": "低活跃（在线时长+提交次数驱动）"
      }
    },
    "text": {
      "docs": 15,
      "n_topics": 4,
      "label_tags": {
        "-1": "离群主题（未归类文本）",
        "0": "主题0（就业+考研+压力）"
      }
    }
  },
  "meta": {
    "period": "2026-04"
  }
}
```

---

## 4) 获取画像列表（前端主列表）

### 请求
`GET /api/profiles?period=2026-04&limit=50&offset=0`

### 响应示例
```json
{
  "ok": true,
  "message": "success",
  "data": [
    {
      "id": 12,
      "student_id": 1,
      "period": "2026-04",
      "warning_score": null,
      "numeric_cluster_id": 0,
      "text_cluster_id": 2,
      "numeric_tags": {
        "display_label": "高活跃（成绩+正确率驱动）",
        "label_code": "high_activity",
        "drivers": ["avg_score", "correct_rate"],
        "cluster_rank": 1,
        "cluster_score": 0.82
      },
      "text_tags": {
        "display_label": "主题2（就业+考研+压力）",
        "label_code": "topic_2",
        "main_topic_id": 2
      },
      "feature_summary": {
        "numeric_clustering": {
          "n_clusters": 3
        },
        "text_clustering": {
          "n_topics": 4
        }
      },
      "warning_status": "pending",
      "student": {
        "id": 1,
        "student_no": "20260001",
        "name": "学生1",
        "major": "计算机",
        "grade": "大二"
      }
    }
  ],
  "meta": {
    "period": "2026-04",
    "limit": 50,
    "offset": 0
  }
}
```

---

## 5) 获取聚类统计摘要（图表接口）

### 请求
`GET /api/clustering/summary?period=2026-04`

### 响应示例
```json
{
  "ok": true,
  "message": "success",
  "data": {
    "numeric": [
      { "cluster_id": 0, "count": 8 },
      { "cluster_id": 1, "count": 7 },
      { "cluster_id": 2, "count": 5 }
    ],
    "text": [
      { "topic_id": -1, "count": 3 },
      { "topic_id": 0, "count": 9 },
      { "topic_id": 2, "count": 8 }
    ]
  },
  "meta": {
    "period": "2026-04"
  }
}
```

---

## 6) 常见错误响应示例

### 学生不存在
```json
{
  "ok": false,
  "message": "student_not_found",
  "error": {
    "code": "student_not_found",
    "detail": "student_id=999"
  }
}
```

### 画像不存在
```json
{
  "ok": false,
  "message": "profile_not_found",
  "error": {
    "code": "profile_not_found",
    "detail": "student_id=999"
  }
}
```
