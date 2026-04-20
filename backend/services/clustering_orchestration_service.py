from __future__ import annotations

from typing import Any

from services.numeric_clustering_service import NumericClusteringService
from services.text_clustering_service import TextClusteringService


class ClusteringOrchestrationService:
    def __init__(self, numeric_service: NumericClusteringService, text_service: TextClusteringService):
        self.numeric_service = numeric_service
        self.text_service = text_service

    def run_all(self, payload: dict[str, Any]) -> dict[str, Any]:
        period = payload.get("period")
        limit = payload.get("limit")
        persist_to_db = bool(payload.get("persist_to_db", True))
        generate_plot = bool(payload.get("generate_plot", True))

        numeric_result = self.numeric_service.run_pipeline(
            period=period,
            n_clusters=int(payload.get("n_clusters", 3)),
            normalization=str(payload.get("normalization", "minmax")),
            random_state=int(payload.get("random_state", 42)),
            limit=int(limit) if limit is not None else None,
            persist_to_db=persist_to_db,
            generate_plot=generate_plot,
        )
        text_result = self.text_service.run_pipeline(
            period=period,
            min_content_len=int(payload.get("min_content_len", 5)),
            min_topic_size=int(payload.get("min_topic_size", 5)),
            nr_topics=int(payload["nr_topics"]) if payload.get("nr_topics") is not None else None,
            embedding_model_name=str(
                payload.get("embedding_model", TextClusteringService.DEFAULT_EMBEDDING_MODEL)
            ),
            stopwords_path=str(
                payload.get("stopwords_path", TextClusteringService.DEFAULT_HIT_STOPWORDS_PATH)
            ),
            limit=int(limit) if limit is not None else None,
            persist_to_db=persist_to_db,
            generate_plot=generate_plot,
        )

        return {
            "period": numeric_result.period or text_result.period,
            "numeric": {
                "rows": len(numeric_result.labels),
                "n_clusters": numeric_result.n_clusters,
                "label_tags": numeric_result.label_tags,
            },
            "text": {
                "docs": len(text_result.topics),
                "n_topics": text_result.n_topics,
                "label_tags": text_result.label_tags,
            },
        }

