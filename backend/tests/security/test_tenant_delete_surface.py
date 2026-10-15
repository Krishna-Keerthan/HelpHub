"""Static check: tenants are deleted only through ``delete_if_candidate``."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TENANTS = ROOT / "app" / "db" / "repositories" / "tenants.py"
NAMES = {"delete_by_ids", "_delete_by_ids"}


def tenant_deleters(source: str) -> list[str]:
    """Public functions containing a ``delete(Tenant ...)`` statement."""
    out: list[str] = []
    for func in ast.parse(source).body:
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if func.name.startswith("_"):
            continue
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "delete"
                and any(
                    isinstance(n, ast.Name) and n.id == "Tenant"
                    for a in node.args
                    for n in ast.walk(a)
                )
            ):
                out.append(func.name)
    return out


def test_only_delete_if_candidate_deletes_tenants() -> None:
    assert tenant_deleters(TENANTS.read_text()) == ["delete_if_candidate"]


def test_checker_finds_a_public_unconditional_delete() -> None:
    source = "async def purge(i):\n    await s.execute(delete(Tenant).where(Tenant.id == i))\n"
    assert tenant_deleters(source) == ["purge"]


def test_no_module_references_delete_by_ids() -> None:
    offenders = []
    for base in ("app", "eval", "tests", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if path == TENANTS or path == Path(__file__):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                name = getattr(node, "attr", None) or getattr(node, "id", None)
                if name in NAMES or (
                    isinstance(node, ast.Constant) and node.value in NAMES
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []
