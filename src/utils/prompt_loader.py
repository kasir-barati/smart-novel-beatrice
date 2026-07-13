"""
Jinja2 loader for versioned prompt templates.

Each domain module (src/modules/<feature>/prompts/<version>.jinja2) calls load_prompt with its own module directory to get a fully-rendered prompt string. Templates are compiled once per (directory, name) pair and cached for the process lifetime.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@cache
def _environment_for(prompts_dir: Path) -> Environment:
    """
    Return the shared :class:`~jinja2.Environment` for a prompts directory.

    We are sharing a single :class:`~jinja2.Environment` across every module, but each module then has to worry about naming collisions with siblings. A tiny per-directory :class:`~jinja2.FileSystemLoader` is the cheaper isolation.
    """

    return Environment(
        loader=FileSystemLoader(str(prompts_dir)),
        autoescape=False,  # These templates render plain text prompts sent to an LLM, not HTML — HTML-escaping would corrupt punctuation.
        undefined=StrictUndefined,  # A missing variable is a bug, fail loudly, we should NOT silently substitute an empty string into a system prompt.
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def load_prompt(prompts_dir: Path, version: str, /, **variables: object) -> str:
    """
    Render ``<prompts_dir>/<version>.jinja2`` with the given variables.

    Parameters:
        prompts_dir: Directory holding a module's ``*.jinja2`` files.
        version:     Filename stem, e.g. ``"v1"`` for ``v1.jinja2``.
        variables:   Template variables. Missing variables raise
            :class:`~jinja2.exceptions.UndefinedError` at render time.

    :returns: The rendered prompt with leading / trailing whitespace stripped.
    """

    env = _environment_for(prompts_dir)
    template = env.get_template(f"{version}.jinja2")
    return template.render(**variables).strip()
