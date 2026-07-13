from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import UndefinedError

from src.utils.prompt_loader import load_prompt


def test_renders_template_with_variables(tmp_path: Path) -> None:
    (tmp_path / "v1.jinja2").write_text("Hello {{ name }}!\n")

    rendered = load_prompt(tmp_path, "v1", name="world")

    assert rendered == "Hello world!"


def test_missing_variable_raises(tmp_path: Path) -> None:
    (tmp_path / "v1.jinja2").write_text("Hello {{ name }}!")

    with pytest.raises(UndefinedError):
        load_prompt(tmp_path, "v1")


def test_versions_are_resolved_by_stem(tmp_path: Path) -> None:
    (tmp_path / "v1.jinja2").write_text("v1 prompt")
    (tmp_path / "v2.jinja2").write_text("v2 prompt")

    assert load_prompt(tmp_path, "v1") == "v1 prompt"
    assert load_prompt(tmp_path, "v2") == "v2 prompt"


def test_leading_and_trailing_whitespace_stripped(tmp_path: Path) -> None:
    (tmp_path / "v1.jinja2").write_text("\n\n  hello  \n\n")

    assert load_prompt(tmp_path, "v1") == "hello"
