from __future__ import annotations

import types
from collections.abc import Callable
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

from pydantic import TypeAdapter, ValidationError, create_model
from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info
from strawberry.types.field import StrawberryField


class PydanticConstraintsExtension(FieldExtension):
    """
    Validate resolver arguments using the pydantic :class:`Annotated` metadata on every resolver argument.

    Usage:

    .. code-block:: python

        from src.utils import apply_pydantic_validation

        apply_pydantic_validation(Query, Mutation)  # BEFORE strawberry.Schema(...)
        schema = strawberry.Schema(query=Query, mutation=Mutation)
    """

    def apply(self, field: StrawberryField) -> None:
        """
        Inspect each argument's annotation and build a :class:`TypeAdapter` for it.

        Two cases are recognised:

        1. **Scalar argument** with pydantic metadata.
        2. **``@strawberry.input`` argument** whose fields carry pydantic metadata.
        """

        self._validators: dict[str, tuple[TypeAdapter[Any], bool]] = {}
        resolver = field.base_resolver

        if resolver is None:
            return

        try:
            hints = get_type_hints(resolver.wrapped_func, include_extras=True)
        except Exception:
            # Forward refs we cannot resolve: skip silently rather than
            # blow up schema construction.
            return

        for arg in field.arguments:
            hint = hints.get(arg.python_name)

            if hint is None:
                continue

            if get_origin(hint) is Annotated:
                _, *meta = get_args(hint)

                if any(_is_pydantic_metadata(m) for m in meta):
                    self._validators[arg.python_name] = (TypeAdapter(hint), False)
                    continue

            input_cls = _strawberry_input_class(hint)

            if input_cls is not None:
                adapter = _build_input_adapter(input_cls)

                if adapter is not None:
                    self._validators[arg.python_name] = (adapter, True)

    def resolve(
        self,
        next_: Callable[..., Any],
        source: Any,
        info: Info,
        **kwargs: Any,
    ) -> Any:
        return next_(source, info, **self._validate(kwargs))

    async def resolve_async(
        self,
        next_: Callable[..., Any],
        source: Any,
        info: Info,
        **kwargs: Any,
    ) -> Any:
        result = next_(source, info, **self._validate(kwargs))
        has_coroutine = hasattr(result, "__await__")

        if has_coroutine:
            return await result

        return result

    def _validate(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        for name, (adapter, is_input) in self._validators.items():
            if name not in kwargs or kwargs[name] is None:
                continue

            value = kwargs[name]

            try:
                if is_input:
                    validated_model = adapter.validate_python(_input_as_dict(value))

                    _apply_validated_dump(value, validated_model.model_dump())
                    continue

                kwargs[name] = adapter.validate_python(value)
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first["loc"]) or name

                raise ValueError(
                    f"Invalid value for argument '{name}.{loc}': {first['msg']}"
                    if is_input
                    else f"Invalid value for argument '{name}': {first['msg']}"
                ) from exc

        return kwargs


def _is_pydantic_metadata(obj: Any) -> bool:
    """
    Returns ``True`` if ``obj`` is pydantic / annotated-types validation metadata.
    """
    module = type(obj).__module__ or ""
    res = module.startswith("pydantic") or module.startswith("annotated_types")

    return res


def _strawberry_input_class(hint: Any) -> type | None:
    """
    Return the underlying class for a ``@strawberry.input`` hint, unwrapping ``Annotated[...]`` and optional unions; otherwise return ``None``.
    """
    hint = _unwrap_optional(hint)

    if get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
        hint = _unwrap_optional(hint)

    if not isinstance(hint, type):
        return None

    definition = getattr(hint, "__strawberry_definition__", None)

    if definition is None:
        return None

    if not getattr(definition, "is_input", False):
        return None

    return hint


def _unwrap_optional(hint: Any) -> Any:
    """
    Return ``T`` for ``Optional[T]`` or ``T | None``; otherwise return ``hint``.
    """
    origin = get_origin(hint)

    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(hint) if a is not type(None)]

        if len(non_none) == 1:
            return non_none[0]

    return hint


def _build_input_adapter(
    input_cls: type,
    *,
    _seen: dict[type, type] | None = None,
) -> TypeAdapter[Any] | None:
    """
    Build a :class:`TypeAdapter` for a ``@strawberry.input`` class. Nested input fields are handled recursively, including lists.

    Returns:
        ``None`` when no pydantic metadata is found at any depth.
    """
    seen: dict[type, type] = {} if _seen is None else _seen
    validator_model, has_metadata = _build_input_validator_model(input_cls, seen)

    if not has_metadata:
        return None

    adapter: TypeAdapter[Any] = TypeAdapter(validator_model)

    return adapter


def _build_input_validator_model(
    input_cls: type,
    seen: dict[type, type],
) -> tuple[type, bool]:
    """
    Build a Pydantic model mirroring a ``@strawberry.input`` class.

    ``seen`` prevents infinite recursion on cyclic input types.
    """
    if input_cls in seen:
        return seen[input_cls], False

    try:
        hints = get_type_hints(input_cls, include_extras=True)
    except Exception:
        # Opaque model that will let Pydantic pass values through untouched.
        placeholder = create_model(f"{input_cls.__name__}__Validator")

        return placeholder, False

    fields: dict[str, Any] = {}
    has_metadata = False

    # Register a forward placeholder BEFORE recursing, so cyclic references
    # resolve to this same model rather than looping forever.
    placeholder = create_model(f"{input_cls.__name__}__Validator")
    seen[input_cls] = placeholder

    for name, hint in hints.items():
        if name.startswith("_"):
            continue

        rewritten, field_has_metadata = _rewrite_hint(hint, seen)
        fields[name] = (rewritten, ...)
        has_metadata = has_metadata or field_has_metadata

    if not fields:
        return placeholder, has_metadata

    model = create_model(f"{input_cls.__name__}__Validator", **fields)
    seen[input_cls] = model

    return model, has_metadata


def _rewrite_hint(hint: Any, seen: dict[type, type]) -> tuple[Any, bool]:
    """
    Rewrite a type hint by replacing nested ``@strawberry.input`` types
    with their validator models.

    Preserve ``Annotated`` metadata and container shapes.
    """
    origin = get_origin(hint)

    if origin is Annotated:
        inner, *meta = get_args(hint)
        rewritten_inner, inner_has_metadata = _rewrite_hint(inner, seen)
        this_has_metadata = any(_is_pydantic_metadata(m) for m in meta)

        return Annotated[rewritten_inner, *meta], inner_has_metadata or this_has_metadata

    input_cls = _strawberry_input_class(hint)

    if input_cls is not None:
        nested_model, nested_has_metadata = _build_input_validator_model(input_cls, seen)
        return nested_model, nested_has_metadata

    if origin is not None:
        args = get_args(hint)

        if not args:
            return hint, False

        rewritten_args: list[Any] = []
        any_has_metadata = False

        for arg in args:
            rewritten_arg, arg_has_metadata = _rewrite_hint(arg, seen)
            rewritten_args.append(rewritten_arg)
            any_has_metadata = any_has_metadata or arg_has_metadata

        try:
            return origin[tuple(rewritten_args)], any_has_metadata
        except TypeError:
            # Some special forms (Union, Optional, etc.) don't support the
            # bracket protocol on `origin`. Fall back to the original hint;
            # nested constraints inside these are rare and preserving the
            # outer shape matters more than trying to be clever here.
            return hint, any_has_metadata

    return hint, False


def _input_as_dict(instance: Any) -> dict[str, Any]:
    """
    Best-effort conversion of a ``@strawberry.input`` instance to a plain dict.
    """
    if isinstance(instance, dict):
        return {k: _to_plain(v) for k, v in instance.items()}

    if hasattr(instance, "__dict__"):
        return {k: _to_plain(v) for k, v in vars(instance).items() if not k.startswith("_")}

    raise TypeError(f"Cannot extract fields from {instance!r}")


def _to_plain(value: Any) -> Any:
    """
    Recursively convert strawberry-input instances (and lists of them) to dicts.
    """

    if _is_strawberry_input_instance(value):
        return _input_as_dict(value)

    if isinstance(value, list):
        return [_to_plain(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_to_plain(item) for item in value)

    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}

    return value


def _is_strawberry_input_instance(value: Any) -> bool:
    definition = getattr(type(value), "__strawberry_definition__", None)

    return definition is not None and getattr(definition, "is_input", False)


def _apply_validated_dump(instance: Any, validated: dict[str, Any]) -> None:
    """
    Write validated values back to a strawberry-input instance in place.
    """
    for field_name, new_value in validated.items():
        current = getattr(instance, field_name, None)

        setattr(instance, field_name, _reconcile(current, new_value))


def _reconcile(current: Any, new_value: Any) -> Any:
    """
    Merge a validated value back onto the original input shape.
    """
    if _is_strawberry_input_instance(current) and isinstance(new_value, dict):
        _apply_validated_dump(current, new_value)

        return current

    if isinstance(current, list) and isinstance(new_value, list):
        reconciled: list[Any] = []

        for i, item in enumerate(new_value):
            if i < len(current):
                reconciled.append(_reconcile(current[i], item))

                continue

            reconciled.append(item)

        return reconciled

    return new_value


def apply_pydantic_validation(*types: type) -> None:
    """
    Attach :class:`PydanticConstraintsExtension` to fields on the given Strawberry types.

    Call this before building the schema. Repeated calls are idempotent.

    Usage::

        apply_pydantic_validation(Query, Mutation)
        schema = strawberry.Schema(query=Query, mutation=Mutation)
    """
    seen: set[int] = set()

    def _visit(tp: type) -> None:
        definition = getattr(tp, "__strawberry_definition__", None)

        if definition is None:
            return

        if id(definition) in seen:
            return

        seen.add(id(definition))

        for field in definition.fields:
            if any(isinstance(ext, PydanticConstraintsExtension) for ext in field.extensions):
                continue

            ext = PydanticConstraintsExtension()
            ext.apply(field)
            field.extensions.append(ext)

    for tp in types:
        _visit(tp)


__all__ = ["PydanticConstraintsExtension", "apply_pydantic_validation"]
