from __future__ import annotations

import argparse
from datetime import datetime

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from services.counselor_api_service import CounselorApiService
from services.numeric_clustering_service import NumericClusteringService
from services.text_clustering_service import TextClusteringService


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh profiles (numeric+text) and recompute warning scores.")
    parser.add_argument("--period", type=str, default=None, help="Target period, format YYYY-MM.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for debug runs.")
    parser.add_argument("--n-clusters", type=int, default=3, help="KMeans cluster count for numeric clustering.")
    parser.add_argument(
        "--normalization",
        type=str,
        default="minmax",
        choices=["none", "minmax", "zscore"],
        help="Normalization strategy for numeric features.",
    )
    parser.add_argument("--random-state", type=int, default=42, help="Random state for KMeans.")
    parser.add_argument("--min-content-len", type=int, default=5, help="Minimum cleaned text length.")
    parser.add_argument("--min-topic-size", type=int, default=5, help="BERTopic min_topic_size.")
    parser.add_argument("--nr-topics", type=int, default=None, help="Optional target number of BERTopic topics.")
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
    parser.add_argument(
        "--generate-plot",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate plot/html outputs under results/pics.",
    )
    args = parser.parse_args()

    period = args.period or datetime.now().strftime("%Y-%m")

    numeric_service = NumericClusteringService()
    text_service = TextClusteringService()

    numeric_result = numeric_service.run_pipeline(
        period=period,
        n_clusters=args.n_clusters,
        normalization=args.normalization,
        random_state=args.random_state,
        limit=args.limit,
        persist_to_db=True,
        generate_plot=args.generate_plot,
    )
    text_result = text_service.run_pipeline(
        period=period,
        min_content_len=args.min_content_len,
        min_topic_size=args.min_topic_size,
        nr_topics=args.nr_topics,
        embedding_model_name=args.embedding_model,
        stopwords_path=args.stopwords_path,
        limit=args.limit,
        persist_to_db=True,
        generate_plot=args.generate_plot,
    )

    cfg = DatabaseConfig.from_env()
    _engine, SessionLocal = init_engine_and_session(cfg.database_url)
    counselor_service = CounselorApiService(session_factory=SessionLocal)
    score_result = counselor_service.recompute_warning_scores()

    print("=== Profile + Warning Refresh Done ===")
    print(f"period={period}")
    print(f"numeric_rows={len(numeric_result.labels)}")
    print(f"text_docs={len(text_result.topics)}")
    print(f"warning_scores_updated={score_result.get('updated', 0)}")


if __name__ == "__main__":
    main()

