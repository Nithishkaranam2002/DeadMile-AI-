"""The test split is never loaded outside the gate code path.

Static part: an AST scan of every module in dmlab proves that
* only dmlab/harness/splits.py reads configs/suites.yaml;
* only splits.py and the gate module touch ``_read_split`` (the one function
  that can return the test split);
* no module imports the gate module, except the gate modules listed below
  (Module 4 adds the promotion gate here).
Runtime part: the public loaders and suites refuse the test split, and
``_read_split("test")`` refuses any caller but the gate module.
"""

import ast
from pathlib import Path

import pytest

from dmlab.harness import splits, suites
from dmlab.safeguards import test_split

PKG = Path(__file__).parents[1] / "dmlab"
SPLITS_FILE = "harness/splits.py"
GATE_FILE = "safeguards/test_split.py"
GATE_MODULE = "dmlab.safeguards.test_split"
ALLOWED_GATE_IMPORTERS: set[str] = set()  # e.g. {"safeguards/gates.py"} in Module 4


def _modules():
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG).as_posix()
        yield rel, ast.parse(path.read_text(), filename=str(path))


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def test_scan_finds_the_package():
    rels = [rel for rel, _ in _modules()]
    assert SPLITS_FILE in rels and GATE_FILE in rels and len(rels) > 20


def test_only_splits_reads_suites_config():
    offenders = []
    for rel, tree in _modules():
        if rel == SPLITS_FILE:
            continue
        docs = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and (node.value == "suites" or "suites.yaml" in node.value)
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_only_gate_touches_read_split():
    offenders = []
    for rel, tree in _modules():
        if rel in (SPLITS_FILE, GATE_FILE):
            continue
        for node in ast.walk(tree):
            name = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.id
                if isinstance(node, ast.Name)
                else None
            )
            if name == "_read_split":
                offenders.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.ImportFrom) and any(
                a.name == "_read_split" for a in node.names
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_nobody_imports_the_gate_module():
    offenders = []
    for rel, tree in _modules():
        if rel == GATE_FILE or rel in ALLOWED_GATE_IMPORTERS:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == GATE_MODULE for a in node.names):
                offenders.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.ImportFrom):
                full = [f"{node.module}.{a.name}" for a in node.names]
                if node.module == GATE_MODULE or GATE_MODULE in full:
                    offenders.append(f"{rel}:{node.lineno}")
            # splits.py names the gate module to check its callers.
            if isinstance(node, ast.Constant) and node.value == GATE_MODULE and rel != SPLITS_FILE:
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_public_loaders_refuse_test():
    with pytest.raises(PermissionError):
        splits.split_names("test")
    with pytest.raises(PermissionError):
        splits.split_refs("test")
    with pytest.raises(PermissionError):
        suites.full_suite("test")
    with pytest.raises(PermissionError):
        suites.get_suite("full", "test")


def test_read_split_refuses_other_callers():
    with pytest.raises(PermissionError):
        splits._read_split("test")
    assert splits._read_split("validation") == splits.split_names("validation")


def test_gate_module_can_read_test_and_it_is_disjoint():
    test_names = set(test_split.gate_test_names())
    assert len(test_names) == 34
    settings = splits.suite_settings()
    assert not test_names & set(settings["quick_instances"])
    for s in splits.PUBLIC_SPLITS:
        assert not test_names & set(splits.split_names(s))
    assert "test" not in str(settings)  # suite settings carry no test instance lists


def test_cli_offers_no_test_split():
    assert "test" not in splits.PUBLIC_SPLITS
