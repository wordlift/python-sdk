from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class YarrrmlValidationIssue:
    code: str
    severity: str
    message: str
    reference: str
    line: int | None = None


@dataclass(frozen=True)
class YarrrmlValidationResult:
    path: str
    issues: tuple[YarrrmlValidationIssue, ...]

    @property
    def errors(self) -> tuple[YarrrmlValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")


def _extract_references(text: str) -> list[tuple[str, int]]:
    refs: list[tuple[str, int]] = []
    i = 0
    while i < len(text):
        start = text.find("$(", i)
        if start == -1:
            break
        depth = 1
        j = start + 2
        while j < len(text) and depth > 0:
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            j += 1
        if depth != 0:
            line = text.count("\n", 0, start) + 1
            refs.append(("", line))
            break
        ref = text[start + 2 : j - 1].strip()
        line = text.count("\n", 0, start) + 1
        refs.append((ref, line))
        i = j
    return refs


FUNCTION_CALL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\s*\(")
SIMPLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_yarrrml_text(
    text: str, *, path: str = "<memory>"
) -> YarrrmlValidationResult:
    issues: list[YarrrmlValidationIssue] = []
    refs = _extract_references(text)

    if not refs:
        return YarrrmlValidationResult(path=path, issues=tuple())

    for ref, line in refs:
        if not ref:
            issues.append(
                YarrrmlValidationIssue(
                    code="unbalanced_reference",
                    severity="error",
                    message="Unbalanced $(...) reference.",
                    reference=ref,
                    line=line,
                )
            )
            continue
        if ref.startswith("/"):
            issues.append(
                YarrrmlValidationIssue(
                    code="absolute_path_reference",
                    severity="error",
                    message="Absolute XPath in $(...) is not supported by morph-kgc XML reference extraction.",
                    reference=ref,
                    line=line,
                )
            )
        if "::" in ref:
            issues.append(
                YarrrmlValidationIssue(
                    code="xpath_axis_reference",
                    severity="error",
                    message="XPath axis in $(...) is not supported in morph-kgc XML references.",
                    reference=ref,
                    line=line,
                )
            )
        if "text()" in ref:
            issues.append(
                YarrrmlValidationIssue(
                    code="xpath_text_node_reference",
                    severity="error",
                    message="text() in $(...) is not supported in morph-kgc XML references.",
                    reference=ref,
                    line=line,
                )
            )
        if "|" in ref:
            issues.append(
                YarrrmlValidationIssue(
                    code="xpath_union_reference",
                    severity="error",
                    message="XPath union (|) in $(...) is not supported in morph-kgc XML references.",
                    reference=ref,
                    line=line,
                )
            )
        if FUNCTION_CALL_RE.search(ref):
            issues.append(
                YarrrmlValidationIssue(
                    code="xpath_function_reference",
                    severity="error",
                    message="Function call in $(...) is not supported in morph-kgc XML references.",
                    reference=ref,
                    line=line,
                )
            )
        if SIMPLE_NAME_RE.match(ref):
            issues.append(
                YarrrmlValidationIssue(
                    code="named_reference_needs_source_field",
                    severity="warning",
                    message=(
                        "Named reference in $(...) may require precomputed source fields "
                        "when mapping mode is XPath-only."
                    ),
                    reference=ref,
                    line=line,
                )
            )

    return YarrrmlValidationResult(path=path, issues=tuple(issues))


def validate_yarrrml_file(path: Path) -> YarrrmlValidationResult:
    text = path.read_text(encoding="utf-8")
    return validate_yarrrml_text(text, path=str(path))


def validate_yarrrml_paths(paths: Iterable[Path]) -> list[YarrrmlValidationResult]:
    return [validate_yarrrml_file(path) for path in paths]


def _find_default_paths(root: Path) -> list[Path]:
    return sorted(root.glob("profiles/*/mappings/*.yarrrml.j2"))


def _to_summary(results: list[YarrrmlValidationResult]) -> dict[str, object]:
    total_files = len(results)
    total_issues = sum(len(r.issues) for r in results)
    total_errors = sum(len(r.errors) for r in results)

    by_code: dict[str, int] = {}
    for result in results:
        for issue in result.issues:
            by_code[issue.code] = by_code.get(issue.code, 0) + 1

    return {
        "files": total_files,
        "issues": total_issues,
        "errors": total_errors,
        "issue_counts": dict(sorted(by_code.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate YARRRML mappings for morph-kgc XPath-reference compatibility."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Mapping files to validate. Defaults to profiles/*/mappings/*.yarrrml.j2",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report.",
    )
    args = parser.parse_args()

    if args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        paths = _find_default_paths(Path.cwd())

    results = validate_yarrrml_paths(paths)
    summary = _to_summary(results)

    if args.json:
        payload = {
            "summary": summary,
            "results": [
                {
                    "path": result.path,
                    "issues": [asdict(issue) for issue in result.issues],
                }
                for result in results
            ],
        }
        print(json.dumps(payload, indent=2))
        return

    print(
        f"Validated {summary['files']} files, "
        f"{summary['issues']} issues ({summary['errors']} errors)."
    )
    for result in results:
        if not result.issues:
            continue
        print(f"\n{result.path}")
        for issue in result.issues:
            line = f":{issue.line}" if issue.line else ""
            print(
                f"  - [{issue.severity}] {issue.code}{line}: "
                f"{issue.reference} -> {issue.message}"
            )


__all__ = [
    "YarrrmlValidationIssue",
    "YarrrmlValidationResult",
    "validate_yarrrml_text",
    "validate_yarrrml_file",
    "validate_yarrrml_paths",
]
