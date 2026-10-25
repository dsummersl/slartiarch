from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from slarti import proc
from slarti.domain import Probe
from slarti.findings import Finding, Severity

VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

Version = tuple[int, int, int]


@dataclass(frozen=True)
class Requirement:
    """A supported version range for one delegated tool."""

    tool: str
    floor: Version
    ceiling: Version | None
    argv: list[str]
    upgrade: str


REQUIREMENTS: list[Requirement] = [
    Requirement("node", (20, 0, 0), None, ["node", "--version"], "install Node >= 20"),
    Requirement(
        "likec4",
        (1, 59, 0),
        (2, 0, 0),
        proc.likec4(["--version"]),
        "npm install likec4@^1.59",
    ),
    Requirement(
        "linkml",
        (1, 11, 0),
        (2, 0, 0),
        ["linkml", "--version"],
        "uv pip install 'linkml>=1.11,<2'",
    ),
]


def version_text(version: Version | None) -> str:
    """A version tuple as the string the generated `Probe` carries."""
    return "not found" if version is None else ".".join(str(p) for p in version)


def _probe(req_tool: str, version: Version | None, location: str | None, detail: str,
           ok: bool) -> Probe:
    return Probe(
        tool=req_tool, version=version_text(version), location=location, detail=detail, ok=ok
    )


def parse_version(text: str) -> Version | None:
    match = VERSION_RE.search(text)
    if match is None:
        return None
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    return (int(major), int(minor), int(patch or 0))


def range_text(req: Requirement) -> str:
    floor = ".".join(str(p) for p in req.floor)
    if req.ceiling is None:
        return f">={floor}"
    return f">={floor},<{req.ceiling[0]}"


def _locate(req: Requirement) -> str | None:
    binary = req.argv[0]
    if binary == "npx":
        return f"npx --no-install {req.argv[2]}"
    return proc.resolve(binary)


def probe(req: Requirement, cwd: Path | None = None) -> Probe:
    """Probe one tool for its version and check it against the supported range."""
    try:
        result = proc.run(req.argv, cwd=cwd)
    except proc.ToolMissing:
        return _probe(req.tool, None, None, f"{req.argv[0]} not found on PATH", False)
    version = parse_version(result.stdout) or parse_version(result.stderr)
    if version is None:
        return _probe(req.tool, None, _locate(req), "version could not be determined", False)
    return _classify(req, version, _locate(req))


def _in_range(req: Requirement, version: Version) -> bool:
    return version >= req.floor and (req.ceiling is None or version < req.ceiling)


def _classify(req: Requirement, version: Version, location: str | None) -> Probe:
    if _in_range(req, version):
        return _probe(req.tool, version, location, f"within {range_text(req)}", True)
    detail = f"requires {range_text(req)}; upgrade with: {req.upgrade}"
    return _probe(req.tool, version, location, detail, False)


# The Mermaid adapter parses in Python, so no tool runs; a project that pins Mermaid for
# rendering must pin a version whose syntax the adapter's subset is checked against.
MERMAID = Requirement(
    "mermaid", (11, 0, 0), (13, 0, 0), [], "npm install @mermaid-js/mermaid-cli@^12"
)
MERMAID_PACKAGE = Path("node_modules/mermaid/package.json")


def probe_mermaid(root: Path) -> Probe:
    """Check the project's pinned Mermaid, read from its package; none pinned passes."""
    package = root / MERMAID_PACKAGE
    if not package.is_file():
        detail = f"none pinned; the adapter reads the Mermaid {range_text(MERMAID)} subset"
        return _probe(MERMAID.tool, None, None, detail, True)
    try:
        version = parse_version(str(json.loads(package.read_text(encoding="utf-8"))["version"]))
    except (ValueError, KeyError, TypeError):
        version = None
    if version is None:
        return _probe(MERMAID.tool, None, str(package), "version could not be determined", False)
    return _classify(MERMAID, version, str(package))


def probe_python() -> Probe:
    version = sys.version_info[:3]
    ok = (3, 11, 0) <= version < (4, 0, 0)
    detail = "within >=3.11,<4" if ok else "requires >=3.11,<4"
    return _probe("python", version, sys.executable, detail, ok)


# Tools only the LikeC4 adapter needs.
LIKEC4_TOOLS = ("node", "likec4")


def probe_all(cwd: Path | None = None, likec4: bool = True,
              mermaid: Path | None = None) -> list[Probe]:
    """Probe every delegated tool once. Cached in-process only by the caller (I4).

    Without ``likec4``, the tools only the LikeC4 adapter needs are not probed. With
    ``mermaid``, the Mermaid pinned under that project root is checked too."""
    required = [r for r in REQUIREMENTS if likec4 or r.tool not in LIKEC4_TOOLS]
    return [probe_python(), *(probe(req, cwd) for req in required), *_pinned(mermaid)]


def _pinned(root: Path | None) -> list[Probe]:
    return [] if root is None else [probe_mermaid(root)]


def env_findings(probes: list[Probe]) -> list[Finding]:
    """Turn failed probes into ENV-1 findings."""
    return [
        Finding(
            id="ENV-1",
            severity=Severity.error,
            file="-",
            subject=p.tool,
            message=f"{p.tool} {p.version} is unusable: {p.detail}.",
            remedy=f"Install a {p.tool} version that satisfies the supported range, then re-run.",
        )
        for p in probes
        if not p.ok
    ]
