"""哈希嵌入 Provider：把文本散列为固定维度向量（默认实现，无外部依赖）。"""

from __future__ import annotations

from hashlib import sha256
from math import sqrt


class HashEmbeddingProvider:
    provider_name = "hash-embedding-provider"

    def __init__(self, dimensions: int = 64):
        self.dimensions = max(8, dimensions)

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token for token in self._tokens(text) if token]
        if not tokens:
            return vector
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]

    def _tokens(self, text: str) -> list[str]:
        compact = text.lower().strip()
        if not compact:
            return []
        words = compact.replace("，", " ").replace("。", " ").replace("、", " ").split()
        if words:
            tokens = words
        else:
            tokens = []
        tokens.extend(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
        return tokens
