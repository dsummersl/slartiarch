from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MARKDOWN = (".md", ".markdown")
MERMAID = (".mmd", ".mermaid")

_FENCE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*mermaid\s*$")
_REGION = re.compile(r"^\s*<!--\s*slarti:(?P<edge>begin|end)\s+\S+\s*-->\s*$")
_DIRECTIVE = re.compile(r"^\s*%%\s*slarti:\s*(?P<text>.*?)\s*$")
_COMMENT = re.compile(r"^\s*%%")
_FRONT_MATTER = "---"


@dataclass(frozen=True)
class Directive:
    """One ``%% slarti:`` comment, with the line it was written on."""

    line: int
    text: str


@dataclass
class Block:
    """One Mermaid diagram: its text, with comments and front matter blanked so lines still count.

    ``offset`` is the number of file lines before the diagram's first line."""

    id: str
    file: str
    offset: int
    text: str
    title: str = ""
    directives: list[Directive] = field(default_factory=list)

    def line(self, relative: int) -> int:
        """The file line of a line counted from the diagram's first line."""
        return self.offset + relative


def _front_matter_end(lines: list[str]) -> int | None:
    """The line closing a front matter that opens the diagram, counted from 0."""
    if not lines or lines[0].strip() != _FRONT_MATTER:
        return None
    return next((n for n in range(1, len(lines)) if lines[n].strip() == _FRONT_MATTER), None)


def _title(front_matter: str) -> str:
    try:
        raw = yaml.safe_load(front_matter)
    except yaml.YAMLError:
        return ""
    title = raw.get("title") if isinstance(raw, dict) else None
    return "" if title is None else str(title)


def _front_matter(lines: list[str]) -> tuple[str, int]:
    """The front matter's title, and how many leading lines the front matter takes."""
    end = _front_matter_end(lines)
    if end is None:
        return "", 0
    return _title("\n".join(lines[1:end])), end + 1


def block(identifier: str, file: str, offset: int, lines: list[str]) -> Block:
    """A diagram from its raw lines: front matter read, ``%%`` comments collected or dropped."""
    title, skip = _front_matter(lines)
    found = Block(id=identifier, file=file, offset=offset, text="", title=title)
    kept = []
    for number, text in enumerate(lines, start=1):
        directive = _DIRECTIVE.match(text)
        if directive:
            found.directives.append(Directive(offset + number, directive.group("text")))
        blank = number <= skip or _COMMENT.match(text)
        kept.append("" if blank else text)
    found.text = "\n".join(kept) + "\n"
    return found


def _closes(text: str, fence: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(fence) and set(stripped) == {fence[0]}


def _generated(text: str, inside: bool) -> bool:
    """Whether a line is inside a generated region, given whether the previous one was."""
    region = _REGION.match(text)
    return inside if region is None else region.group("edge") == "begin"


def _opening(text: str, generated: bool) -> str | None:
    opening = None if generated else _FENCE.match(text)
    return None if opening is None else opening.group("fence")


def _closing(lines: list[str], start: int, fence: str) -> int:
    return next((n for n in range(start, len(lines)) if _closes(lines[n], fence)), len(lines))


def _fences(lines: list[str]) -> Iterator[tuple[int, int]]:
    """The first and past-the-last content line of every ``mermaid`` fence a reader wrote."""
    generated, number = False, 0
    while number < len(lines):
        generated = _generated(lines[number], generated)
        fence = _opening(lines[number], generated)
        number += 1
        if fence is None:
            continue
        end = _closing(lines, number, fence)
        yield number, end
        number = end + 1


def _fenced(file: str, lines: list[str]) -> list[Block]:
    """Every ``mermaid`` fence outside the regions ``slartiarch docs`` generates."""
    fences = enumerate(_fences(lines), start=1)
    return [block(f"{file}#{n}", file, start, lines[start:end]) for n, (start, end) in fences]


def read(path: Path, file: str) -> list[Block]:
    """The diagrams one file holds: the whole of a ``.mmd`` file, the fences of Markdown."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if path.suffix in MARKDOWN:
        return _fenced(file, lines)
    return [block(file, file, 0, lines)]


def files_for(path: Path) -> list[Path]:
    """The files a configured path names: the file, or a directory's Mermaid and Markdown."""
    if path.is_dir():
        suffixes = (*MERMAID, *MARKDOWN)
        return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in suffixes)
    return [path]
