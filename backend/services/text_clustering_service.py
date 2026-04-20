from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from bertopic import BERTopic


@dataclass
class TextClusteringResult:
    topics: list[int]


class TextClusteringService:
    """
    文字聚类骨架：用 BERTopic 做主题聚类。
    注意：首次运行需要下载模型/embedding 资源（取决于 sentence-transformers 配置）。
    """

    def __init__(self) -> None:
        self._model = BERTopic()

    def cluster(self, docs: Iterable[str]) -> TextClusteringResult:
        docs_list = list(docs)
        topics, _probs = self._model.fit_transform(docs_list)
        return TextClusteringResult(topics=list(topics))

