from __future__ import annotations

import json
from pathlib import Path

from wordlift_sdk.kg_build import yarrrml_validator as yv


def test_extract_references_and_unbalanced() -> None:
    refs = yv._extract_references("x $(foo) y $(bar(baz)) z $(")
    assert refs[0] == ("foo", 1)
    assert refs[1] == ("bar(baz)", 1)
    assert refs[2] == ("", 1)


def test_validate_yarrrml_text_emits_expected_issue_codes() -> None:
    text = """
    s: $(/abs/path)
    p: $(a::b)
    q: $(text())
    r: $(foo|bar)
    t: $(fn(name))
    u: $(simple_name)
    v: $(
    """
    result = yv.validate_yarrrml_text(text, path="demo")
    codes = {issue.code for issue in result.issues}
    assert "absolute_path_reference" in codes
    assert "xpath_axis_reference" in codes
    assert "xpath_text_node_reference" in codes
    assert "xpath_union_reference" in codes
    assert "xpath_function_reference" in codes
    assert "named_reference_needs_source_field" in codes
    assert "unbalanced_reference" in codes
    assert result.errors


def test_validate_yarrrml_file_paths_and_summary(tmp_path: Path) -> None:
    a = tmp_path / "a.yarrrml.j2"
    b = tmp_path / "b.yarrrml.j2"
    a.write_text("s: $(name)", encoding="utf-8")
    b.write_text("s: $(/x)", encoding="utf-8")
    results = yv.validate_yarrrml_paths([a, b])
    summary = yv._to_summary(results)
    assert summary["files"] == 2
    assert summary["issues"] >= 2
    assert summary["errors"] >= 1
    assert "absolute_path_reference" in summary["issue_counts"]


def test_find_default_paths(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "profiles" / "demo" / "mappings" / "x.yarrrml.j2"
    p.parent.mkdir(parents=True)
    p.write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    paths = yv._find_default_paths(Path.cwd())
    assert paths == [p]


def test_main_json_and_text_output(tmp_path: Path, monkeypatch, capsys) -> None:
    f = tmp_path / "x.yarrrml.j2"
    f.write_text("s: $(name)", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv", ["yarrrml_validator", "--json", str(f)], raising=False
    )
    yv.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["files"] == 1
    assert payload["results"][0]["path"] == str(f)

    monkeypatch.setattr("sys.argv", ["yarrrml_validator", str(f)], raising=False)
    yv.main()
    out = capsys.readouterr().out
    assert "Validated 1 files" in out
