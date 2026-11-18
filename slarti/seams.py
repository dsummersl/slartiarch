from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from slarti import proc
from slarti.domain import Crossing, Hunk, ModelRelation
from slarti.models import NO_CONTRACT, Contract, Models

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
NEW_FILE = "+++ "
OLD_FILE = "--- "
DEV_NULL = "/dev/null"
GITHUB = re.compile(r"github\.com[:/]+(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$")
TODO = "  TODO[additive|breaking|internal]: what changed, and who must change with it"
HEADING = "## Contract boundaries"


class SeamsError(Exception):
    """Raised when git cannot describe the range."""


@dataclass
class Changed:
    """The lines a range changed in one file, at the head of the range."""

    hunks: list[tuple[int, int]] = field(default_factory=list)
    deleted: bool = False


def _git(args: list[str], models: Models) -> str:
    result = proc.run(["git", *args], cwd=models.config.root)
    if result.code != 0:
        raise SeamsError(f"git {' '.join(args)} failed:\n{result.stderr or result.stdout}")
    return result.stdout


def _strip(name: str) -> str | None:
    name = name.strip()
    if name == DEV_NULL:
        return None
    return name[2:] if name[:2] in ("a/", "b/") else name


@dataclass
class _Reader:
    """Reads a unified diff a line at a time, file header by file header."""

    files: dict[str, Changed] = field(default_factory=dict)
    old: str | None = None
    current: Changed | None = None

    def read(self, line: str) -> None:
        if line.startswith(OLD_FILE):
            self.old = _strip(line[len(OLD_FILE):])
        elif line.startswith(NEW_FILE):
            self.current = _file(self.files, _strip(line[len(NEW_FILE):]), self.old)
        else:
            self.hunk(line)

    def hunk(self, line: str) -> None:
        match = HUNK.match(line)
        if match and self.current is not None and not self.current.deleted:
            self.current.hunks.append(_lines(int(match[1]), int(match[2] or 1)))


def parse_diff(text: str) -> dict[str, Changed]:
    """Each changed file, relative to where the diff ran, with its hunks at the head."""
    reader = _Reader()
    for line in text.splitlines():
        reader.read(line)
    return reader.files


def _file(files: dict[str, Changed], new: str | None, old: str | None) -> Changed | None:
    """The entry a file header opens: the file at the head, or the file the range deleted."""
    if new is not None:
        return files.setdefault(new, Changed())
    return files.setdefault(old, Changed(deleted=True)) if old else None


def _lines(start: int, count: int) -> tuple[int, int]:
    """A hunk's lines at the head; a pure deletion is shown at the line it follows."""
    if count == 0:
        return max(start, 1), max(start, 1)
    return start, start + count - 1


def remote_url(url: str) -> str | None:
    """The web URL of a GitHub remote, in any of the forms git accepts."""
    match = GITHUB.search(url.strip())
    return f"https://github.com/{match['repo']}" if match else None


@dataclass(frozen=True)
class Range:
    """What the diff is between, and where permalinks into its head point."""

    base: str
    head: str
    prefix: str = ""
    web: str | None = None

    def url(self, file: str, hunk: tuple[int, int]) -> str | None:
        if self.web is None:
            return None
        return f"{self.web}/blob/{self.head}/{self.prefix}{file}#{anchor(hunk)}"


def anchor(hunk: tuple[int, int]) -> str:
    start, end = hunk
    return f"L{start}" if start == end else f"L{start}-L{end}"


def _web(models: Models, remote: str | None) -> str | None:
    if remote is not None:
        return remote.rstrip("/") or None
    result = proc.run(["git", "remote", "get-url", "origin"], cwd=models.config.root)
    return remote_url(result.stdout) if result.code == 0 else None


def describe(models: Models, base: str, remote: str | None = None
             ) -> tuple[Range, dict[str, Changed]]:
    """The range ``base...HEAD`` and the files it changed, relative to the project root."""
    head = _git(["rev-parse", "HEAD"], models).strip()
    prefix = _git(["rev-parse", "--show-prefix"], models).strip()
    diff = _git(["diff", "--relative", "--unified=0", "--no-color", "--no-ext-diff",
                 f"{base}...{head}"], models)
    return Range(base, head, prefix, _web(models, remote)), parse_diff(diff)


def _overlaps(hunk: tuple[int, int], lines: tuple[int, int] | None) -> bool:
    return lines is None or (hunk[0] <= lines[1] and lines[0] <= hunk[1])


def _crossing(relation: ModelRelation, file: str, hunks: list[tuple[int, int]],
              span: Range) -> Crossing:
    return Crossing(
        source=relation.source,
        target=relation.target,
        title=relation.title,
        contract=str(relation.contract),
        file=file,
        hunks=[Hunk(start=h[0], end=h[1], url=span.url(file, h)) for h in hunks],
    )


def _inside(change: Changed, contract: Contract) -> list[tuple[int, int]]:
    """The changed lines that fall inside the contract; a deleted file has none left."""
    return [h for h in change.hunks if _overlaps(h, contract.lines)]


def _touched(contract: Contract, changed: dict[str, Changed]
             ) -> list[tuple[str, list[tuple[int, int]]]]:
    """The contract's files the range changed, each with the changed lines inside it."""
    covered = sorted(filter(lambda item: contract.covers(item[0]), changed.items()))
    found = [(file, _inside(change, contract), change.deleted) for file, change in covered]
    return [(file, hunks) for file, hunks, deleted in filter(_crossed, found)]


def _crossed(found: tuple[str, list[tuple[int, int]], bool]) -> bool:
    return bool(found[1]) or found[2]


def _contract(models: Models, relation: ModelRelation) -> Contract | None:
    """Where a relation's contract resolves, unless it has none or names nothing."""
    ref = (relation.contract or "").strip()
    return models.contract(ref) if ref not in ("", NO_CONTRACT) else None


def crossings(models: Models, span: Range, changed: dict[str, Changed]) -> list[Crossing]:
    """Every relation whose contract the range changed, one per changed contract file."""
    resolved = [(r, _contract(models, r)) for r in models.vocabulary.relations]
    return [
        _crossing(relation, file, hunks, span)
        for relation, contract in resolved if contract is not None
        for file, hunks in _touched(contract, changed)
    ]


def _link(crossing: Crossing, hunk: Hunk) -> str:
    text = f"{crossing.file}#{anchor((hunk.start, hunk.end))}"
    return f"[{text}]({hunk.url})" if hunk.url else f"`{text}`"


def _item(crossing: Crossing) -> list[str]:
    links = ", ".join(_link(crossing, h) for h in crossing.hunks or [])
    where = links or f"`{crossing.file}` (deleted)"
    contract = "" if crossing.contract == crossing.file else f" (contract `{crossing.contract}`)"
    return [
        f"- `{crossing.source} -> {crossing.target}` {crossing.title}{contract}: {where}",
        TODO,
    ]


def as_markdown(span: Range, found: list[Crossing]) -> str:
    """The crossings as a section to put first in a pull request's description."""
    if not found:
        return (f"{HEADING}\n\nNo relation's contract changed between `{span.base}` and "
                f"`{span.head[:12]}`.")
    items = [line for crossing in found for line in _item(crossing)]
    return "\n".join([HEADING, "", "### Changed", *items])


def as_json(span: Range, found: list[Crossing]) -> str:
    payload = {
        "base": span.base,
        "head": span.head,
        "crossings": [c.model_dump(exclude_none=True) for c in found],
    }
    return json.dumps(payload, indent=2)
