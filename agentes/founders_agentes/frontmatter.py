"""Leitura do frontmatter das Skills (SKILL.md).

Implementa o subconjunto de YAML que aparece em SKILL.md: mapas aninhados por
indentação, escalares simples, entre aspas, em bloco (| e >) e listas simples.
Sem dependências externas, para o runtime não precisar de PyYAML.
"""
from __future__ import annotations

import re

__all__ = ["ErroFrontmatter", "separar_frontmatter", "ler_yaml"]


class ErroFrontmatter(ValueError):
    """Frontmatter malformado."""


_KEY_RE = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^\s:#"'\[{-][^:#]*?|-[^\s:#][^:#]*?)\s*:(?:\s+(?P<rest>.*))?$""")
_BLOCK_RE = re.compile(r"^([|>])([+-]?)\d*\s*(?:#.*)?$")
_INT_RE = re.compile(r"^[-+]?\d+$")
_FLOAT_RE = re.compile(r"^[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?$")
_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": " ", "P": " ",
}


def separar_frontmatter(text: str) -> tuple[dict, str]:
    """Separa o frontmatter (dict) do corpo em Markdown."""
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = ler_yaml("\n".join(lines[1:i]))
            body = "\n".join(lines[i + 1:]).strip("\n")
            return meta, (body + "\n") if body else ""
    raise ErroFrontmatter("frontmatter sem a linha '---' de fechamento")


def ler_yaml(src: str) -> dict:
    lines = src.replace("\t", "    ").split("\n")
    i = _skip_blank(lines, 0)
    if i >= len(lines):
        return {}
    value, i = _parse_mapping(lines, i, _indent(lines[i]))
    i = _skip_blank(lines, i)
    if i < len(lines):
        raise ErroFrontmatter(f"linha {i + 1} fora do lugar: {lines[i].strip()!r}")
    return value


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skip_blank(lines: list[str], i: int) -> int:
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#"):
            break
        i += 1
    return i


def _is_item(stripped: str) -> bool:
    return stripped == "-" or stripped.startswith("- ")


def _parse_mapping(lines: list[str], i: int, indent: int) -> tuple[dict, int]:
    result: dict = {}
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        ind = _indent(line)
        if ind < indent:
            break
        if ind > indent:
            raise ErroFrontmatter(f"indentação inesperada na linha {i + 1}")
        stripped = line.strip()
        if _is_item(stripped):
            break
        match = _KEY_RE.match(stripped)
        if not match:
            raise ErroFrontmatter(f"linha {i + 1} não é 'chave: valor': {stripped!r}")
        key = match.group("key")
        if key[:1] in "\"'":
            key = key[1:-1]
        rest = (match.group("rest") or "").strip()
        result[key], i = _parse_value(lines, i + 1, indent, rest)
    return result, i


def _parse_value(lines: list[str], i: int, indent: int, rest: str):
    if rest.startswith("#"):
        rest = ""
    block = _BLOCK_RE.match(rest)
    if block:
        return _parse_block_scalar(lines, i, indent, block.group(1), block.group(2))
    if rest == "":
        j = _skip_blank(lines, i)
        if j < len(lines):
            child = _indent(lines[j])
            is_item = _is_item(lines[j].strip())
            if child > indent:
                return (_parse_list if is_item else _parse_mapping)(lines, j, child)
            if child == indent and is_item:
                return _parse_list(lines, j, child)
        return None, i
    return _parse_inline(lines, i, indent, rest)


def _parse_list(lines: list[str], i: int, indent: int) -> tuple[list, int]:
    items: list = []
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines):
            break
        line = lines[i]
        ind = _indent(line)
        stripped = line.strip()
        if ind != indent or not _is_item(stripped):
            if ind > indent:
                raise ErroFrontmatter(f"indentação inesperada na linha {i + 1}")
            break
        content = stripped[1:].strip()
        if content and content[0] not in "\"'[{" and _KEY_RE.match(content):
            item_indent = ind + (len(stripped) - len(content))
            lines[i] = " " * item_indent + content
            value, i = _parse_mapping(lines, i, item_indent)
        else:
            value, i = _parse_value(lines, i + 1, indent, content)
        items.append(value)
    return items, i


def _parse_inline(lines: list[str], i: int, indent: int, rest: str):
    quote = rest[0]
    if quote in "\"'":
        text = rest
        while _closing_quote(text, quote) < 0:
            if i >= len(lines):
                raise ErroFrontmatter("aspas sem fechamento no frontmatter")
            nxt = lines[i].strip()
            i += 1
            text += (" " + nxt) if nxt else "\n"
        end = _closing_quote(text, quote)
        trailing = text[end + 1:].strip()
        if trailing and not trailing.startswith("#"):
            raise ErroFrontmatter(f"texto depois das aspas: {trailing!r}")
        inner = text[1:end]
        if quote == '"':
            return _unescape_double(inner), i
        return inner.replace("''", "'"), i
    if rest.startswith("[") and rest.endswith("]"):
        inner = rest[1:-1].strip()
        return ([_scalar(part.strip().strip("\"'")) for part in inner.split(",")] if inner else []), i
    parts = [_strip_comment(rest)]
    while i < len(lines):
        line = lines[i]
        if not line.strip() or _indent(line) <= indent:
            break
        parts.append(_strip_comment(line.strip()))
        i += 1
    return _scalar(" ".join(p for p in parts if p)), i


def _parse_block_scalar(lines: list[str], i: int, indent: int, style: str, chomp: str):
    block: list[str] = []
    block_indent: int | None = None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            block.append("")
            i += 1
            continue
        ind = _indent(line)
        if ind <= indent or (block_indent is not None and ind < block_indent):
            break
        if block_indent is None:
            block_indent = ind
        block.append(line[block_indent:])
        i += 1
    trailing = 0
    while block and block[-1] == "":
        block.pop()
        trailing += 1
    if style == "|":
        text = "\n".join(block)
    else:
        paragraphs: list[str] = []
        current: list[str] = []
        for line in block:
            if line == "":
                paragraphs.append(" ".join(current))
                current = []
            else:
                current.append(line.strip())
        paragraphs.append(" ".join(current))
        text = "\n".join(paragraphs)
    if chomp == "-":
        return text, i
    if chomp == "+":
        return text + "\n" * (trailing + 1), i
    return (text + "\n") if text else "", i


def _closing_quote(text: str, quote: str) -> int:
    k = 1
    while k < len(text):
        ch = text[k]
        if quote == '"' and ch == "\\":
            k += 2
            continue
        if ch == quote:
            if quote == "'" and k + 1 < len(text) and text[k + 1] == "'":
                k += 2
                continue
            return k
        k += 1
    return -1


def _unescape_double(s: str) -> str:
    out: list[str] = []
    k = 0
    while k < len(s):
        ch = s[k]
        if ch != "\\" or k + 1 >= len(s):
            out.append(ch)
            k += 1
            continue
        nxt = s[k + 1]
        width = {"x": 2, "u": 4, "U": 8}.get(nxt)
        if width:
            code = s[k + 2:k + 2 + width]
            try:
                out.append(chr(int(code, 16)))
            except ValueError as exc:
                raise ErroFrontmatter(f"escape inválido: \\{nxt}{code}") from exc
            k += 2 + width
            continue
        if nxt not in _ESCAPES:
            raise ErroFrontmatter(f"escape inválido: \\{nxt}")
        out.append(_ESCAPES[nxt])
        k += 2
    return "".join(out)


def _strip_comment(text: str) -> str:
    match = re.search(r"\s#", text)
    return (text[:match.start()] if match else text).strip()


def _scalar(text: str):
    low = text.lower()
    if low in ("", "~", "null"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text
