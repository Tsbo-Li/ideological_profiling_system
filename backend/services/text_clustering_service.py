from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Iterable, Optional

from bertopic import BERTopic
import jieba
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sqlalchemy import select

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import StudentTextData
from database.profile_repository import ProfileRepository
from services.preprocessor import Preprocessor

@dataclass
class TextClusteringResult:
    topics: list[int]
    probs: list[Optional[float]]
    text_ids: list[int]
    student_ids: list[int]
    period: str
    n_topics: int
    label_tags: dict[int, str]
    topic_profiles: dict[int, dict[str, Any]]
    student_topic_map: dict[int, int]
    student_text_tags: dict[int, dict[str, Any]]


class TextClusteringService:
    """
    文字聚类骨架：用 BERTopic 做主题聚类。
    注意：首次运行需要下载模型/embedding 资源（取决于 sentence-transformers 配置）。
    """

    # Default to a project-local embedding model directory if present (recommended for offline demos).
    # If you keep using a HF model id, pass it via --embedding-model and the resolver will still work.
    DEFAULT_EMBEDDING_MODEL = "models/bge-base-zh-v1.5"
    DEFAULT_HIT_STOPWORDS_PATH = "data/hit_stopwords.txt"
    # Other good Chinese embedding model options:
    # - "shibing624/text2vec-base-chinese"
    # - "GanymedeNil/text2vec-large-chinese"
    BUILTIN_FALLBACK_STOPWORDS = {
        "的", "了", "和", "是", "在", "就", "也", "都", "而", "及", "与", "着", "或", "一个", "我们",
        "你", "我", "他", "她", "它", "这", "那", "以及", "并且",
    }

    def __init__(self, preprocessor: Optional[Preprocessor] = None) -> None:
        self.preprocessor = preprocessor or Preprocessor()
        self._model: Optional[BERTopic] = None
        self._stop_words: set[str] = set()

    def _load_hit_stopwords(self, stopwords_path: Optional[str] = None) -> set[str]:
        path = Path(stopwords_path or self.DEFAULT_HIT_STOPWORDS_PATH)
        if not path.is_absolute():
            # Resolve from backend root when running with python -m services...
            path = Path.cwd() / path

        if not path.exists():
            print(f"[text_clustering] stopwords file not found: {path}. Fallback to built-in stopwords.")
            return set(self.BUILTIN_FALLBACK_STOPWORDS)

        words: set[str] = set()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:
                    words.add(w)
        # Always include built-in stopwords to filter common function words.
        words.update(self.BUILTIN_FALLBACK_STOPWORDS)
        return words

    def _tokenize_zh(self, text: str) -> list[str]:
        """
        Chinese tokenizer wrapper for CountVectorizer:
        - jieba segmentation
        - stopwords filtering (HIT + fallback)
        - punctuation/number/noise filtering
        """
        tokens = jieba.lcut(text or "")
        clean_tokens: list[str] = []
        for token in tokens:
            t = token.strip()
            if not t:
                continue
            if t in self._stop_words:
                continue
            # Remove punctuation/symbol-like tokens
            if re.fullmatch(r"[\W_]+", t, flags=re.UNICODE):
                continue
            # Remove pure numbers
            if re.fullmatch(r"\d+(\.\d+)?", t):
                continue
            # Remove 1-char chinese function noise, keep english/abbrev tokens if needed
            if len(t) <= 1 and re.fullmatch(r"[\u4e00-\u9fff]", t):
                continue
            clean_tokens.append(t)
        return clean_tokens

    def _create_model(
        self,
        min_topic_size: int = 5,
        nr_topics: Optional[int] = None,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        stopwords_path: Optional[str] = None,
    ) -> BERTopic:
        self._stop_words = self._load_hit_stopwords(stopwords_path=stopwords_path)
        # Prefer a project-local embedding model directory if present.
        # This allows fully offline runs after you copy the model under backend/models/.
        embedding_model = SentenceTransformer(self._resolve_embedding_model_name(embedding_model_name))
        vectorizer_model = CountVectorizer(
            tokenizer=self._tokenize_zh,
            token_pattern=None,
            min_df=1,
            stop_words=list(self._stop_words),
        )
        return BERTopic(
            embedding_model=embedding_model,
            vectorizer_model=vectorizer_model,
            min_topic_size=min_topic_size,
            nr_topics=nr_topics,
            calculate_probabilities=True,
        )

    @staticmethod
    def _resolve_embedding_model_name(name_or_path: str) -> str:
        raw = (name_or_path or "").strip()
        if not raw:
            return TextClusteringService.DEFAULT_EMBEDDING_MODEL

        backend_root = Path(__file__).resolve().parents[1]
        p = Path(raw)
        if p.exists():
            return str(p)
        if not p.is_absolute():
            # Prefer resolving relative to backend root (works even when cwd is not backend/).
            candidate = backend_root / p
            if candidate.exists():
                return str(candidate)
            # Fallback to cwd for backwards compatibility.
            candidate2 = Path.cwd() / p
            if candidate2.exists():
                return str(candidate2)

        # If user passed a HF model id (e.g. BAAI/bge-base-zh-v1.5), prefer local saved folder if exists:
        # backend/models/BAAI__bge-base-zh-v1.5
        safe = raw.replace("/", "__").replace("\\", "__").replace(":", "_")
        local_candidate = backend_root / "models" / safe
        if local_candidate.exists():
            return str(local_candidate)

        return raw

    def cluster(
        self,
        docs: Iterable[str],
        min_topic_size: int = 5,
        nr_topics: Optional[int] = None,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        stopwords_path: Optional[str] = None,
    ) -> tuple[list[int], list[Optional[float]]]:
        docs_list = list(docs)
        if not docs_list:
            return [], []
        self._model = self._create_model(
            min_topic_size=min_topic_size,
            nr_topics=nr_topics,
            embedding_model_name=embedding_model_name,
            stopwords_path=stopwords_path,
        )
        topics, probs = self._model.fit_transform(docs_list)

        prob_values: list[Optional[float]] = []
        if probs is None:
            prob_values = [None for _ in docs_list]
        else:
            for row in probs:
                # BERTopic returns per-topic probability vector for each document.
                # Store max prob for quick confidence display.
                try:
                    prob_values.append(float(max(row)))
                except Exception:
                    prob_values.append(None)
        return list(topics), prob_values

    def load_text_rows(self, period: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
        cfg = DatabaseConfig.from_env()
        _engine, SessionLocal = init_engine_and_session(cfg.database_url)
        session = SessionLocal()
        try:
            stmt = select(StudentTextData).where(StudentTextData.period == period).order_by(StudentTextData.text_id.asc())
            if limit:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            result: list[dict[str, Any]] = []
            for item in rows:
                result.append(
                    {
                        "text_id": item.text_id,
                        "student_id": item.student_id,
                        "period": item.period,
                        "source": item.source,
                        "text_type": item.text_type,
                        "content": item.content,
                        "event_time": item.event_time,
                    }
                )
            return result
        finally:
            session.close()

    def _build_topic_profiles(self, topics: list[int]) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
        if not topics:
            return {}, {}
        topic_counts = Counter(topics)
        topic_profiles: dict[int, dict[str, Any]] = {}
        label_tags: dict[int, str] = {}

        for topic_id in sorted(topic_counts.keys()):
            if topic_id == -1:
                display = "离群主题（未归类文本）"
                topic_profiles[topic_id] = {
                    "topic_id": -1,
                    "display_name": display,
                    "keywords": [],
                    "sample_count": topic_counts[topic_id],
                }
                label_tags[topic_id] = display
                continue

            keywords: list[str] = []
            if self._model is not None:
                info = self._model.get_topic(topic_id)
                if info:
                    keywords = [word for word, _score in info[:5]]

            key_display = "+".join(keywords[:3]) if keywords else f"主题{topic_id}"
            display = f"主题{topic_id}（{key_display}）"
            topic_profiles[topic_id] = {
                "topic_id": topic_id,
                "display_name": display,
                "keywords": keywords,
                "sample_count": topic_counts[topic_id],
            }
            label_tags[topic_id] = display
        return topic_profiles, label_tags

    def _aggregate_student_topics(
        self,
        text_topic_rows: list[dict[str, Any]],
        topic_profiles: dict[int, dict[str, Any]],
    ) -> tuple[dict[int, int], dict[int, dict[str, Any]]]:
        by_student: dict[int, list[int]] = defaultdict(list)
        for row in text_topic_rows:
            by_student[int(row["student_id"])].append(int(row["topic_id"]))

        student_topic_map: dict[int, int] = {}
        student_text_tags: dict[int, dict[str, Any]] = {}
        for student_id, topic_list in by_student.items():
            counter = Counter(topic_list)
            # Prefer non-outlier topic when possible.
            non_outlier = [(tid, cnt) for tid, cnt in counter.items() if tid != -1]
            if non_outlier:
                main_topic = sorted(non_outlier, key=lambda item: item[1], reverse=True)[0][0]
            else:
                main_topic = -1
            student_topic_map[student_id] = int(main_topic)

            top_topics = sorted(counter.items(), key=lambda item: item[1], reverse=True)[:3]
            topic_distribution = [
                {
                    "topic_id": int(topic_id),
                    "count": int(count),
                    "label_display": topic_profiles.get(topic_id, {}).get("display_name", f"主题{topic_id}"),
                }
                for topic_id, count in top_topics
            ]
            main_profile = topic_profiles.get(main_topic, {})
            student_text_tags[student_id] = {
                "label_display": main_profile.get("display_name", f"主题{main_topic}"),
                "label_code": f"topic_{main_topic}" if main_topic != -1 else "topic_outlier",
                "main_topic_id": int(main_topic),
                "keywords": main_profile.get("keywords", []),
                "topic_distribution": topic_distribution,
                "text_count": int(sum(counter.values())),
            }
        return student_topic_map, student_text_tags

    def visualize_topics(self, output_path: str) -> Optional[str]:
        if self._model is None:
            return None
        try:
            fig = self._model.visualize_topics()
        except Exception:
            return None
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(out_file))
        return str(out_file)

    def persist_text_results_to_profiles(self, result: TextClusteringResult) -> int:
        if not result.student_topic_map:
            return 0
        cfg = DatabaseConfig.from_env()
        _engine, SessionLocal = init_engine_and_session(cfg.database_url)
        repo = ProfileRepository(SessionLocal)

        upserted = 0
        for student_id, main_topic in result.student_topic_map.items():
            existing = repo.get_by_student_id(student_id=student_id, period=result.period)
            summary = dict(existing.feature_summary or {}) if existing and existing.feature_summary else {}
            summary["text_clustering"] = {
                "n_topics": result.n_topics,
                "main_topic_id": int(main_topic),
                "topic_label": result.label_tags.get(main_topic, f"主题{main_topic}"),
            }
            payload = {
                "period": result.period,
                "text_cluster_id": int(main_topic),
                "text_tags": result.student_text_tags.get(student_id, {}),
                "feature_summary": summary,
            }
            profile = repo.upsert_for_student(student_id=student_id, payload=payload, period=result.period)
            if profile is not None:
                upserted += 1
        return upserted

    def run_pipeline(
        self,
        period: Optional[str] = None,
        min_content_len: int = 5,
        deduplicate_by_content: bool = True,
        min_topic_size: int = 5,
        nr_topics: Optional[int] = None,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        stopwords_path: Optional[str] = None,
        limit: Optional[int] = None,
        persist_to_db: bool = True,
        generate_plot: bool = True,
    ) -> TextClusteringResult:
        period = period or datetime.now().strftime("%Y-%m")
        rows = self.load_text_rows(period=period, limit=limit)
        docs, metadata = self.preprocessor.build_bertopic_inputs(
            rows=rows,
            min_content_len=min_content_len,
            deduplicate_by_content=deduplicate_by_content,
        )
        if not docs:
            return TextClusteringResult(
                topics=[],
                probs=[],
                text_ids=[],
                student_ids=[],
                period=period,
                n_topics=0,
                label_tags={},
                topic_profiles={},
                student_topic_map={},
                student_text_tags={},
            )

        topics, probs = self.cluster(
            docs=docs,
            min_topic_size=min_topic_size,
            nr_topics=nr_topics,
            embedding_model_name=embedding_model_name,
            stopwords_path=stopwords_path,
        )
        text_ids = [int(item["text_id"]) for item in metadata]
        student_ids = [int(item["student_id"]) for item in metadata]

        text_topic_rows = [
            {
                "text_id": text_id,
                "student_id": student_id,
                "topic_id": int(topic_id),
                "prob": probs[i] if i < len(probs) else None,
            }
            for i, (text_id, student_id, topic_id) in enumerate(zip(text_ids, student_ids, topics))
        ]

        topic_profiles, label_tags = self._build_topic_profiles(topics=topics)
        student_topic_map, student_text_tags = self._aggregate_student_topics(
            text_topic_rows=text_topic_rows,
            topic_profiles=topic_profiles,
        )
        n_topics = len([tid for tid in set(topics) if tid != -1])

        result = TextClusteringResult(
            topics=topics,
            probs=probs,
            text_ids=text_ids,
            student_ids=student_ids,
            period=period,
            n_topics=n_topics,
            label_tags=label_tags,
            topic_profiles=topic_profiles,
            student_topic_map=student_topic_map,
            student_text_tags=student_text_tags,
        )

        if generate_plot:
            self.visualize_topics(output_path=f"results/pics/text_topics_{period}.html")
        if persist_to_db:
            self.persist_text_results_to_profiles(result)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BERTopic text clustering pipeline.")
    parser.add_argument("--period", type=str, default=None, help="Target period, format YYYY-MM.")
    parser.add_argument("--min-content-len", type=int, default=5, help="Minimum content length after preprocessing.")
    parser.add_argument("--min-topic-size", type=int, default=5, help="BERTopic min_topic_size.")
    parser.add_argument("--nr-topics", type=int, default=None, help="Optional target number of topics.")
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=TextClusteringService.DEFAULT_EMBEDDING_MODEL,
        help="SentenceTransformer model name for BERTopic embeddings.",
    )
    parser.add_argument(
        "--stopwords-path",
        type=str,
        default=TextClusteringService.DEFAULT_HIT_STOPWORDS_PATH,
        help="Path to HIT Chinese stopwords file.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows for debug runs.")
    parser.add_argument(
        "--persist-to-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Persist clustering outputs to student_profiles.",
    )
    parser.add_argument(
        "--generate-plot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate BERTopic HTML visualization under results/pics.",
    )
    args = parser.parse_args()

    service = TextClusteringService()
    result = service.run_pipeline(
        period=args.period,
        min_content_len=args.min_content_len,
        min_topic_size=args.min_topic_size,
        nr_topics=args.nr_topics,
        embedding_model_name=args.embedding_model,
        stopwords_path=args.stopwords_path,
        limit=args.limit,
        persist_to_db=args.persist_to_db,
        generate_plot=args.generate_plot,
    )
    print("=== Text Clustering Done ===")
    print(f"period={result.period}")
    print(f"docs={len(result.topics)}")
    print(f"n_topics={result.n_topics}")
    print(f"label_tags={result.label_tags}")
    if result.student_text_tags:
        first_sid = sorted(result.student_text_tags.keys())[0]
        print(f"student_text_tag_sample={result.student_text_tags[first_sid]}")


if __name__ == "__main__":
    main()

