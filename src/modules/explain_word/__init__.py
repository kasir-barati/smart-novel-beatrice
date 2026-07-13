"""``explainWord`` mutation module.

Public surface:

- :func:`explain_word`: the Strawberry mutation resolver.
- :class:`WordExplanationType`: the GraphQL type returned by the resolver.
"""

from __future__ import annotations

from src.modules.explain_word.resolver import explain_word
from src.modules.explain_word.types import WordExplanationType


__all__ = ["WordExplanationType", "explain_word"]
