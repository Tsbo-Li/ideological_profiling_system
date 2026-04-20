from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from sklearn.cluster import DBSCAN


@dataclass
class NumericClusteringResult:
    labels: list[int]
    n_clusters: int


class NumericClusteringService:
    def cluster(self, vectors: Iterable[Iterable[float]], eps: float = 0.5, min_samples: int = 5) -> NumericClusteringResult:
        x = np.array(list(vectors), dtype=float)
        if x.size == 0:
            return NumericClusteringResult(labels=[], n_clusters=0)
        model = DBSCAN(eps=eps, min_samples=min_samples)
        labels = model.fit_predict(x).tolist()
        n_clusters = len(set([l for l in labels if l != -1]))
        return NumericClusteringResult(labels=labels, n_clusters=n_clusters)

