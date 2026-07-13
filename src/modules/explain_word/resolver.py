from __future__ import annotations

from src.modules.explain_word.agent import explain_word_via_agent
from src.modules.explain_word.types import WordExplanationType


async def explain_word(word: str, context: str) -> WordExplanationType:
    """explainWord resolver for the GraphQL API"""

    result = await explain_word_via_agent(word=word, context=context)

    return WordExplanationType.from_pydantic(result)
