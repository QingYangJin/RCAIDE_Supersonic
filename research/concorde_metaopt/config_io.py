"""Dependency-free configuration loading for the Concorde Phase I programme.

The project environment deliberately stays close to the published RCAIDE-LEADS
dependency set and does not ship PyYAML.  This module supports two formats:

* JSON files are parsed with the standard json module.
* YAML files are parsed with PyYAML when it is importable, otherwise with a
  small indentation-based loader for the strict subset used by the Phase I
  configs (nested mappings, sequences of mappings or scalars, inline scalar
  lists, comments and single-line scalars).

The subset loader rejects tabs, unexpected indentation and duplicate keys so a
config cannot silently change meaning.  It does not implement anchors, aliases,
multi-line scalars or block scalars; Phase I configs must not use them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Tuple


class ConfigError(ValueError):
    """Raised when a config file cannot be parsed or has an invalid shape."""


def load_config(path: str | Path) -> Any:
    """Load a JSON or YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError("config file does not exist: %s" % config_path)
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ConfigError("%s: invalid JSON: %s" % (config_path, error)) from error
    if suffix not in (".yaml", ".yml"):
        raise ConfigError("unsupported config suffix %r (expected .json/.yaml/.yml)" % suffix)
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return load_yaml_subset(text, source=str(config_path))
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:  # pragma: no cover - PyYAML is absent here
        raise ConfigError("%s: invalid YAML: %s" % (config_path, error)) from error


def load_yaml_subset(text: str, source: str = "<string>") -> Any:
    """Parse the strict YAML subset used by the Phase I configs."""
    lines = _tokenize(text, source)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0][1], source)
    if index != len(lines):
        raise ConfigError("%s:%d: unexpected content after the top-level block" % (source, lines[index][0]))
    return value


def _tokenize(text: str, source: str) -> List[Tuple[int, int, str]]:
    lines: List[Tuple[int, int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise ConfigError("%s:%d: tab characters are not supported in YAML configs" % (source, number))
        content = _strip_comment(raw).rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        lines.append((number, indent, content.strip()))
    return lines


def _strip_comment(raw: str) -> str:
    in_single = False
    in_double = False
    for index, character in enumerate(raw):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif character == "#" and not in_single and not in_double and (index == 0 or raw[index - 1].isspace()):
            return raw[:index]
    return raw


def _parse_block(lines: List[Tuple[int, int, str]], index: int, indent: int, source: str) -> Tuple[Any, int]:
    if index >= len(lines):
        raise ConfigError("%s: unexpected end of file" % source)
    number, line_indent, text = lines[index]
    if line_indent < indent:
        raise ConfigError("%s:%d: block ends unexpectedly" % (source, number))
    if text.startswith("- "):
        return _parse_sequence(lines, index, line_indent, source)
    return _parse_mapping(lines, index, line_indent, source, {})


def _parse_sequence(lines: List[Tuple[int, int, str]], index: int, indent: int, source: str) -> Tuple[List[Any], int]:
    items: List[Any] = []
    while index < len(lines):
        number, line_indent, text = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ConfigError("%s:%d: unexpected indentation in sequence" % (source, number))
        if not text.startswith("- "):
            break
        rest = text[2:].strip()
        item_indent = indent + 2
        index += 1
        if rest == "":
            if index < len(lines) and lines[index][1] >= item_indent:
                value, index = _parse_block(lines, index, lines[index][1], source)
            else:
                value = None
            items.append(value)
            continue
        key, inline_value = _split_key_value(rest, source, number)
        if key is None:
            items.append(_parse_scalar(rest, source, number))
            continue
        item: dict = {}
        if inline_value is None:
            if index < len(lines) and lines[index][1] > item_indent:
                inline_value, index = _parse_block(lines, index, lines[index][1], source)
            else:
                inline_value = None
        item[key] = inline_value
        if index < len(lines) and lines[index][1] == item_indent and not lines[index][2].startswith("- "):
            extra, index = _parse_mapping(lines, index, item_indent, source, {})
            for extra_key in extra:
                if extra_key in item:
                    raise ConfigError("%s:%d: duplicate key %r" % (source, number, extra_key))
            item.update(extra)
        items.append(item)
    return items, index


def _parse_mapping(
    lines: List[Tuple[int, int, str]],
    index: int,
    indent: int,
    source: str,
    seed: dict,
) -> Tuple[dict, int]:
    result: dict = dict(seed)
    while index < len(lines):
        number, line_indent, text = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ConfigError("%s:%d: unexpected indentation in mapping" % (source, number))
        if text.startswith("- "):
            break
        key, inline_value = _split_key_value(text, source, number)
        if key is None:
            raise ConfigError("%s:%d: expected a key/value mapping entry" % (source, number))
        if key in result:
            raise ConfigError("%s:%d: duplicate key %r" % (source, number, key))
        index += 1
        if inline_value is None:
            if index < len(lines) and lines[index][1] > indent:
                inline_value, index = _parse_block(lines, index, lines[index][1], source)
            else:
                inline_value = None
        result[key] = inline_value
    return result, index


def _split_key_value(text: str, source: str, number: int) -> Tuple[Optional[str], Any]:
    in_single = False
    in_double = False
    for position, character in enumerate(text):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif character == ":" and not in_single and not in_double:
            after = text[position + 1:]
            if after == "" or after.startswith(" "):
                key = text[:position].strip()
                if not key:
                    raise ConfigError("%s:%d: empty mapping key" % (source, number))
                if len(key) >= 2 and key[0] in ("'", '"') and key[-1] == key[0]:
                    key = key[1:-1]
                value_text = after.strip()
                return key, (_parse_scalar(value_text, source, number) if value_text else None)
    return None, None


def _parse_scalar(token: str, source: str, number: int) -> Any:
    token = token.strip()
    if token == "":
        raise ConfigError("%s:%d: empty scalar value" % (source, number))
    if len(token) >= 2 and token[0] in ("'", '"') and token[-1] == token[0]:
        return token[1:-1]
    if token[0] == "[" and token[-1] == "]":
        inner = token[1:-1].strip()
        if inner == "":
            return []
        return [_parse_scalar(part, source, number) for part in inner.split(",")]
    lowered = token.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "none", "~"):
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token
