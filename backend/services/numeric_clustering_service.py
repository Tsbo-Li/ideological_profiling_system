from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from sqlalchemy import select
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from configs.database_cfg import DatabaseConfig
from database.profile_repository import ProfileRepository
from database.db import init_engine_and_session
from database.models import StudentNumericData
from services.preprocessor import Preprocessor


@dataclass
class NumericClusteringResult:
    labels: list[int]
    n_clusters: int
    student_ids: list[int]
    period: str
    feature_fields: list[str]
    label_tags: dict[int, str]
    cluster_profiles: dict[int, dict[str, Any]]


class NumericClusteringService:
    def __init__(self, preprocessor: Optional[Preprocessor] = None):
        self.preprocessor = preprocessor or Preprocessor()

    def cluster(self, vectors: Iterable[Iterable[float]], n_clusters: int = 3, random_state: int = 42) -> NumericClusteringResult:
        x = np.array(list(vectors), dtype=float)
        if x.size == 0:
            return NumericClusteringResult(
                labels=[],
                n_clusters=0,
                student_ids=[],
                period="",
                feature_fields=[],
                label_tags={},
                cluster_profiles={},
            )
        n_clusters = max(1, min(n_clusters, len(x)))
        model = KMeans(n_clusters=n_clusters, n_init="auto", random_state=random_state)
        labels = model.fit_predict(x).tolist()
        return NumericClusteringResult(
            labels=labels,
            n_clusters=n_clusters,
            student_ids=[],
            period="",
            feature_fields=[],
            label_tags={},
            cluster_profiles={},
        )

    def load_numeric_rows(self, period: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
        cfg = DatabaseConfig.from_env()
        _engine, SessionLocal = init_engine_and_session(cfg.database_url)
        session = SessionLocal()
        try:
            stmt = select(StudentNumericData).where(StudentNumericData.period == period).order_by(StudentNumericData.id.asc())
            if limit:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            result: list[dict[str, Any]] = []
            for item in rows:
                result.append(
                    {
                        "student_id": item.student_id,
                        "period": item.period,
                        "library_visits": item.library_visits,
                        "signin_count": item.signin_count,
                        "course_submit_count": item.course_submit_count,
                        "online_duration_min": item.online_duration_min,
                        "avg_score": item.avg_score,
                        "correct_rate": item.correct_rate,
                        "gpa": item.student.gpa if item.student is not None else None,
                    }
                )
            return result
        finally:
            session.close()

    FEATURE_IMPORTANCE_WEIGHTS: dict[str, float] = {
        # Higher weights for core academic/behavior indicators
        "avg_score": 1.4,
        "gpa": 1.4,
        "correct_rate": 1.2,
        "signin_count": 1.0,
        "course_submit_count": 1.0,
        "online_duration_min": 0.8,
        "library_visits": 0.8,
    }
    LEVEL_DISPLAY_MAP: dict[str, str] = {
        "high_activity": "高活跃",
        "medium_activity": "中活跃",
        "low_activity": "低活跃",
    }
    FEATURE_DISPLAY_MAP: dict[str, str] = {
        "avg_score": "成绩",
        "gpa": "绩点",
        "correct_rate": "正确率",
        "signin_count": "签到",
        "course_submit_count": "提交次数",
        "online_duration_min": "在线时长",
        "library_visits": "图书馆访问",
    }

    def _build_cluster_profiles(
        self,
        labels: list[int],
        vectors: list[list[float]],
        feature_fields: list[str],
    ) -> dict[int, dict[str, Any]]:
        """
        Build frontend-friendly, interpretable cluster profiles.
        """
        if not labels or not vectors or not feature_fields:
            return {}
        profiles: dict[int, dict[str, Any]] = {}
        x = np.array(vectors, dtype=float)
        cluster_ids = sorted(set(labels))
        cluster_scores: dict[int, float] = {}
        cluster_top_features: dict[int, list[str]] = {}
        cluster_feature_contribs: dict[int, dict[str, float]] = {}

        # 1) For each cluster, compute weighted score and top contributing features.
        for cluster_id in cluster_ids:
            idx = [i for i, lb in enumerate(labels) if lb == cluster_id]
            if not idx:
                continue

            centroid = np.mean(x[idx], axis=0)
            feature_scores: list[tuple[str, float]] = []
            weighted_sum = 0.0
            weight_sum = 0.0

            for j, field in enumerate(feature_fields):
                val = float(centroid[j])
                weight = float(self.FEATURE_IMPORTANCE_WEIGHTS.get(field, 1.0))
                weighted_sum += val * weight
                weight_sum += weight
                feature_scores.append((field, val * weight))

            cluster_scores[cluster_id] = weighted_sum / weight_sum if weight_sum > 0 else 0.0
            feature_scores.sort(key=lambda item: item[1], reverse=True)
            cluster_top_features[cluster_id] = [name for name, _ in feature_scores[:2]]
            cluster_feature_contribs[cluster_id] = {name: round(float(score), 4) for name, score in feature_scores}

        if not cluster_scores:
            return {}

        # 2) Rank clusters by weighted score and assign level labels by rank.
        ranked = sorted(cluster_scores.items(), key=lambda item: item[1], reverse=True)
        total = len(ranked)
        for rank, (cluster_id, _score) in enumerate(ranked):
            ratio = rank / total if total > 0 else 0.0
            if ratio < 1 / 3:
                level = "high_activity"
            elif ratio < 2 / 3:
                level = "medium_activity"
            else:
                level = "low_activity"
            drivers = cluster_top_features.get(cluster_id, [])
            level_display = self.LEVEL_DISPLAY_MAP.get(level, level)
            drivers_display = "+".join([self.FEATURE_DISPLAY_MAP.get(name, name) for name in drivers]) if drivers else "特征"
            profiles[cluster_id] = {
                "level": level,
                "display_name": f"{level_display}（{drivers_display}驱动）",
                "score": round(float(cluster_scores[cluster_id]), 4),
                "rank": rank + 1,
                "cluster_id": cluster_id,
                "drivers": drivers,
                "feature_contributions": cluster_feature_contribs.get(cluster_id, {}),
                "sample_count": int(sum(1 for lb in labels if lb == cluster_id)),
            }
        return profiles

    def visualize_clusters(
        self,
        vectors: list[list[float]],
        labels: list[int],
        output_path: str,
    ) -> Optional[str]:
        """
        Optional visualization by PCA(2D). Returns saved path or None.
        """
        if not vectors or len(vectors) < 2:
            return None
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return None

        x = np.array(vectors, dtype=float)
        pca = PCA(n_components=2)
        xy = pca.fit_transform(x)
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(7, 5))
        scatter = plt.scatter(xy[:, 0], xy[:, 1], c=labels, cmap="tab10", s=24)
        plt.title("Numeric Clustering (PCA)")
        plt.xlabel("PC1")
        plt.ylabel("PC2")
        plt.colorbar(scatter, label="cluster")
        plt.tight_layout()
        plt.savefig(out_file, dpi=140)
        plt.close()
        return str(out_file)

    def persist_numeric_results_to_profiles(self, result: NumericClusteringResult) -> int:
        """
        Persist numeric clustering outputs into student_profiles table.
        Mapped fields:
          - numeric_cluster_id
          - numeric_tags (frontend-ready cluster profile subset)
          - feature_summary (pipeline metadata)
        Returns number of upserted rows.
        """
        if not result.student_ids or not result.labels:
            return 0

        cfg = DatabaseConfig.from_env()
        _engine, SessionLocal = init_engine_and_session(cfg.database_url)
        repo = ProfileRepository(SessionLocal)

        upserted = 0
        for student_id, cluster_id in zip(result.student_ids, result.labels):
            cluster_profile = result.cluster_profiles.get(cluster_id, {})
            payload = {
                "period": result.period,
                "numeric_cluster_id": int(cluster_id),
                "numeric_tags": {
                    "label_display": cluster_profile.get("display_name"),
                    "label_code": cluster_profile.get("level"),
                    "level": cluster_profile.get("level"),
                    "drivers": cluster_profile.get("drivers", []),
                    "cluster_rank": cluster_profile.get("rank"),
                    "cluster_score": cluster_profile.get("score"),
                },
                "feature_summary": {
                    "numeric_clustering": {
                        "n_clusters": result.n_clusters,
                        "feature_fields": result.feature_fields,
                        "cluster_id": int(cluster_id),
                        "cluster_contributions": cluster_profile.get("feature_contributions", {}),
                        "sample_count_in_cluster": cluster_profile.get("sample_count", 0),
                    }
                },
            }
            profile = repo.upsert_for_student(student_id=student_id, payload=payload, period=result.period)
            if profile is not None:
                upserted += 1
        return upserted

    def run_pipeline(
        self,
        period: Optional[str] = None,
        numeric_feature_fields: Optional[list[str]] = None,
        normalization: str = "minmax",
        n_clusters: int = 3,
        random_state: int = 42,
        limit: Optional[int] = None,
        generate_plot: bool = False,
        persist_to_db: bool = False,
    ) -> NumericClusteringResult:
        """
        End-to-end:
          1) load from DB
          2) preprocess payloads
          3) clustering
          4) cluster tagging
          5) optional plot
        """
        period = period or datetime.now().strftime("%Y-%m")
        rows = self.load_numeric_rows(period=period, limit=limit)
        payloads = self.preprocessor.build_numeric_payloads(
            rows,
            numeric_feature_fields=numeric_feature_fields,
            normalization=normalization,
            include_only_existing_fields=True,
            drop_if_all_none=True,
        )
        if not payloads:
            return NumericClusteringResult(
                labels=[],
                n_clusters=0,
                student_ids=[],
                period=period,
                feature_fields=numeric_feature_fields or list(self.preprocessor.DEFAULT_NUMERIC_FEATURE_FIELDS),
                label_tags={},
                cluster_profiles={},
            )

        feature_fields = list(payloads[0]["features"].keys())
        vectors = [[float(payload["features"][key]) for key in feature_fields] for payload in payloads]
        student_ids = [int(payload["student_id"]) for payload in payloads]

        core_result = self.cluster(
            vectors=vectors,
            n_clusters=n_clusters,
            random_state=random_state,
        )
        labels = core_result.labels
        n_clusters = core_result.n_clusters
        cluster_profiles = self._build_cluster_profiles(
            labels=labels,
            vectors=vectors,
            feature_fields=feature_fields,
        )
        label_tags = {
            cid: profile["display_name"]
            for cid, profile in cluster_profiles.items()
        }

        if generate_plot:
            self.visualize_clusters(
                vectors=vectors,
                labels=labels,
                output_path=f"results/pics/numeric_clusters_{period}.png",
            )

        final_result = NumericClusteringResult(
            labels=labels,
            n_clusters=n_clusters,
            student_ids=student_ids,
            period=period,
            feature_fields=feature_fields,
            label_tags=label_tags,
            cluster_profiles=cluster_profiles,
        )
        if persist_to_db:
            self.persist_numeric_results_to_profiles(final_result)
        return final_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run numeric clustering pipeline.")
    parser.add_argument("--period", type=str, default=None, help="Target period, format YYYY-MM.")
    parser.add_argument("--n-clusters", type=int, default=3, help="KMeans cluster count.")
    parser.add_argument(
        "--normalization",
        type=str,
        default="minmax",
        choices=["none", "minmax", "zscore"],
        help="Numeric normalization strategy.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows for debug runs.")
    parser.add_argument("--random-state", type=int, default=42, help="Random state for KMeans.")
    parser.add_argument(
        "--persist-to-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Persist clustering results to student_profiles.",
    )
    parser.add_argument(
        "--generate-plot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save PCA scatter plot to results/pics.",
    )
    args = parser.parse_args()

    service = NumericClusteringService()
    result = service.run_pipeline(
        period=args.period,
        n_clusters=args.n_clusters,
        normalization=args.normalization,
        limit=args.limit,
        random_state=args.random_state,
        persist_to_db=args.persist_to_db,
        generate_plot=args.generate_plot,
    )

    print("=== Numeric Clustering Done ===")
    print(f"period={result.period}")
    print(f"n_clusters={result.n_clusters}")
    print(f"rows={len(result.labels)}")
    print(f"label_tags={result.label_tags}")
    if result.cluster_profiles:
        first_key = sorted(result.cluster_profiles.keys())[0]
        print(f"cluster_profile_sample={result.cluster_profiles[first_key]}")


if __name__ == "__main__":
    main()

