"""Serialization utilities for Document IR and ICD IR.

Handles exporting/importing models to/from YAML and JSON formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def to_yaml(model: BaseModel, path: Path | str | None = None) -> str:
    """Serialize a Pydantic model to YAML.

    Args:
        model: The model to serialize.
        path: Optional file path to write to.

    Returns:
        YAML string representation.
    """
    data = model.model_dump(mode="json", exclude_none=True)
    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")

    return yaml_str


def to_json(model: BaseModel, path: Path | str | None = None, indent: int = 2) -> str:
    """Serialize a Pydantic model to JSON.

    Args:
        model: The model to serialize.
        path: Optional file path to write to.
        indent: JSON indentation level.

    Returns:
        JSON string representation.
    """
    json_str = model.model_dump_json(indent=indent, exclude_none=True)

    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_str, encoding="utf-8")

    return json_str


def from_yaml(model_class: type[T], path: Path | str) -> T:
    """Deserialize a Pydantic model from a YAML file.

    Args:
        model_class: The Pydantic model class.
        path: Path to the YAML file.

    Returns:
        An instance of model_class.
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model_class.model_validate(data)


def from_json(model_class: type[T], path: Path | str) -> T:
    """Deserialize a Pydantic model from a JSON file.

    Args:
        model_class: The Pydantic model class.
        path: Path to the JSON file.

    Returns:
        An instance of model_class.
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_class.model_validate(data)
