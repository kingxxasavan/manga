"""All known tools, and the picker that chooses which few the model sees.

A local model gets confused by 150 tool descriptions. Each turn it is offered
the core tools plus the best matches for the message. It can call find_tools
to pull in more.
"""

from __future__ import annotations

import math

import numpy as np

from anexis.memory.store import close_words, words
from anexis.tools.base import Tool


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._words: dict[str, set[str]] = {}
        self._name_words: dict[str, set[str]] = {}
        self._vocab: set[str] | None = None

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        name_words = set(words(tool.name.replace("_", " ").replace("-", " ")))
        self._name_words[tool.name] = name_words
        self._words[tool.name] = name_words | set(words(tool.description))
        self._vocab = None

    def remove_source(self, source: str) -> None:
        for name in [n for n, t in self._tools.items() if t.source == source]:
            del self._tools[name], self._words[name], self._name_words[name]
        self._vocab = None

    def _vocabulary(self) -> set[str]:
        if self._vocab is None:
            self._vocab = set().union(*self._words.values()) if self._words else set()
        return self._vocab

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def _scores(self, query: str, query_vec=None, stats: dict | None = None) -> dict[str, float]:
        terms = set(words(query))
        known = self._vocabulary()
        for term in list(terms):
            if term not in known:  # probably misspelled: "serach", "calculater"
                terms.update(close_words(term, known))
        total = max(len(self._tools), 1)
        scores: dict[str, float] = {}
        if query_vec is not None:
            query_vec = np.asarray(query_vec, dtype=np.float32)
            query_vec = query_vec / max(float(np.linalg.norm(query_vec)), 1e-9)
        for name, tool_words in self._words.items():
            score = 0.0
            for term in terms & tool_words:
                # Rare words say more about which tool is meant than common ones.
                seen_in = sum(1 for w in self._words.values() if term in w)
                weight = math.log(1 + total / seen_in)
                score += weight * (2.0 if term in self._name_words[name] else 1.0)
            tool = self._tools[name]
            if query_vec is not None and tool.vec is not None and len(tool.vec) == len(query_vec):
                similarity = float(np.dot(tool.vec, query_vec))
                if similarity > 0.35:
                    score += 4.0 * similarity
            if score <= 0:
                continue
            s = (stats or {}).get(name)
            if s and s.get("calls", 0) >= 3:
                score *= 1.0 - 0.7 * (s["failures"] / s["calls"])
            scores[name] = score
        return scores

    def find(self, query: str, k: int = 8, query_vec=None, stats: dict | None = None) -> list[Tool]:
        scores = self._scores(query, query_vec, stats)
        best = sorted(scores, key=lambda n: -scores[n])[:k]
        return [self._tools[n] for n in best]

    def pick(self, query: str, k: int = 12, query_vec=None, stats: dict | None = None, extra=()) -> list[Tool]:
        """Core tools, tools the model asked for, then the best matches, capped at k."""
        chosen: dict[str, Tool] = {t.name: t for t in self._tools.values() if t.core}
        for name in extra:
            if name in self._tools:
                chosen[name] = self._tools[name]
        for tool in self.find(query, k, query_vec, stats):
            if len(chosen) >= k:
                break
            chosen.setdefault(tool.name, tool)
        return list(chosen.values())[: max(k, 0)]

    async def embed_all(self, router) -> int:
        """Give every tool a meaning vector so the picker can match by meaning too."""
        todo = [t for t in self._tools.values() if t.vec is None]
        if not todo:
            return 0
        done = 0
        for start in range(0, len(todo), 64):
            batch = todo[start : start + 64]
            result = await router.embed([f"{t.name}: {t.description[:300]}" for t in batch])
            if not result:
                return done
            for tool, vec in zip(batch, result[1]):
                tool.vec = vec / max(float(np.linalg.norm(vec)), 1e-9)
                done += 1
        return done
