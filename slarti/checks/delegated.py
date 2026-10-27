from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from slarti import proc, vocabulary
from slarti.config import Config


@dataclass(frozen=True)
class Delegation:
    """One delegated validation and the exit code it returned."""

    tool: str
    argv: list[str]
    result: proc.Result

    @property
    def ok(self) -> bool:
        return self.result.code == 0


def likec4_validate(config: Config) -> Delegation:
    argv = proc.likec4(["validate", str(config.path("likec4"))])
    return Delegation("likec4", argv, proc.run(argv, cwd=config.root))


def _lint(config: Config, schema: Path, staged: Path) -> Delegation:
    argv = ["linkml", "lint", str(config.rel(schema))]
    result = proc.run(["linkml", "lint", str(staged / schema.name)], cwd=config.root)
    real = str(config.rel(config.path("linkml")))

    def restore(text: str) -> str:
        return text.replace(str(staged), real)

    return Delegation("linkml", argv, proc.Result(result.code, restore(result.stdout),
                                                  restore(result.stderr)))


def linkml_lint(config: Config) -> list[Delegation]:
    """Lint each schema from a staged copy whose vocabulary imports resolve locally;
    ``linkml lint`` takes no importmap. Output names the real files."""
    texts = {schema: schema.read_text(encoding="utf-8") for schema in config.schema_files()}
    force = any(vocabulary.imports_vocabulary(text) for text in texts.values())
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        for schema, text in texts.items():
            (staged / schema.name).write_text(vocabulary.localised(text, force), encoding="utf-8")
        return [_lint(config, schema, staged) for schema in config.schema_files()]


def run_all(config: Config) -> list[Delegation]:
    """Run every delegated validation; slarti reimplements none of them (I2)."""
    likec4 = [likec4_validate(config)] if config.likec4_enabled() else []
    return [*likec4, *linkml_lint(config)]


def report(delegations: list[Delegation]) -> int:
    """Pass every delegated diagnostic through unaltered; the number that failed."""
    failed = [d for d in delegations if not d.ok]
    for delegation in failed:
        proc.passthrough(delegation.result)
    return len(failed)
