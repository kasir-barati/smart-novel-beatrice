from __future__ import annotations

from strawberry.types.base import get_object_definition

from src.modules.explain_word.types import WordExplanation, WordExplanationType


def test_word_explanation_preserves_clean_input() -> None:
    explanation = WordExplanation(
        meaning="Lasting a very short time.",
        simplified_explanation="Not around for long.",
        synonyms=["fleeting", "transient", "momentary"],
        antonyms=["permanent", "enduring"],
    )

    assert explanation.synonyms == ["fleeting", "transient", "momentary"]
    assert explanation.antonyms == ["permanent", "enduring"]


def test_word_explanation_deduplicates_synonyms_preserving_first_seen_order() -> None:
    explanation = WordExplanation(
        meaning="m",
        simplified_explanation="s",
        synonyms=["transient", "fleeting", "transient", "momentary", "fleeting"],
    )

    assert explanation.synonyms == ["transient", "fleeting", "momentary"]


def test_word_explanation_deduplicates_antonyms_case_insensitively() -> None:
    explanation = WordExplanation(
        meaning="m",
        simplified_explanation="s",
        antonyms=["Stability", "stability", "STABILITY"],
    )

    assert explanation.antonyms == ["Stability"]


def test_word_explanation_caps_synonyms_and_antonyms_at_five_items() -> None:
    explanation = WordExplanation(
        meaning="m",
        simplified_explanation="s",
        synonyms=["a", "b", "c", "d", "e", "f", "g"],
        antonyms=["a", "b", "c", "d", "e", "f", "g"],
    )

    assert explanation.synonyms == ["a", "b", "c", "d", "e"]
    assert explanation.antonyms == ["a", "b", "c", "d", "e"]


def test_word_explanation_strips_whitespace_and_drops_empty_entries() -> None:
    explanation = WordExplanation(
        meaning="m",
        simplified_explanation="s",
        synonyms=["  fleeting  ", "", "   ", "transient"],
    )

    assert explanation.synonyms == ["fleeting", "transient"]


def test_word_explanation_defaults_are_empty_lists() -> None:
    explanation = WordExplanation(
        meaning="m",
        simplified_explanation="s",
    )

    assert explanation.synonyms == []
    assert explanation.antonyms == []


def test_word_explanation_type_exposes_the_same_fields_as_the_pydantic_model() -> None:
    pydantic_fields = set(WordExplanation.model_fields.keys())
    graphql_fields = {
        field.python_name
        for field in get_object_definition(WordExplanationType, strict=True).fields
    }

    assert pydantic_fields == graphql_fields, (
        "WordExplanation and WordExplanationType fields have drifted. "
        f"Only on WordExplanation: {sorted(pydantic_fields - graphql_fields)}. "
        f"Only on WordExplanationType: {sorted(graphql_fields - pydantic_fields)}."
    )
