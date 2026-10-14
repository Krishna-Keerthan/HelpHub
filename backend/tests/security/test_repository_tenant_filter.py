"""Static check: repository functions are tenant-scoped.

Every public function in app/db/repositories/*.py (except tenants.py, the one
untenanted table) takes a ``tenant_id`` parameter, and every statement it builds
(select/update/delete/insert/text) references ``tenant_id`` -- directly, or
through a name earlier built from a statement that does.
"""

import ast
from pathlib import Path

import pytest

REPOSITORIES = Path(__file__).resolve().parents[2] / "app" / "db" / "repositories"
BUILDERS = {"select", "update", "delete", "insert", "pg_insert", "text"}
# Pure helpers: they take an already-built tenant statement or only clamp a number.
EXEMPT = {"chunks.clamp_k", "chunks.explain_statement"}
SIMPLE = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return, ast.Expr)


def _repo_files() -> list[Path]:
    return sorted(
        p
        for p in REPOSITORIES.glob("*.py")
        if p.name not in {"tenants.py", "__init__.py"}
    )


def _constants(tree: ast.Module) -> dict[str, str]:
    """Module-level string constants (SQL kept in a constant, e.g. _SEARCH_SQL)."""
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _names(node: ast.AST, constants: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
            if sub.id in constants and "tenant_id" in constants[sub.id]:
                found.add("tenant_id")
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
        elif isinstance(sub, ast.keyword) and sub.arg:
            found.add(sub.arg)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if "tenant_id" in sub.value:
                found.add("tenant_id")
    return found


def _is_setting(call: ast.Call) -> bool:
    first = call.args[0] if call.args else None
    return (
        isinstance(first, ast.Constant)
        and isinstance(first.value, str)
        and first.value.lstrip().lower().startswith("select set_config(")
    )


def _builds_statement(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "text" and _is_setting(sub):
                continue  # SELECT set_config(...): a GUC, not a table statement
            if name in BUILDERS:
                return True
    return False


def _simple_statements(func: ast.AST) -> list[ast.stmt]:
    stmts = [n for n in ast.walk(func) if isinstance(n, SIMPLE)]
    return sorted(stmts, key=lambda n: (n.lineno, n.col_offset))


def violations(source: str, module: str) -> list[str]:
    tree = ast.parse(source)
    constants = _constants(tree)
    problems: list[str] = []
    for func in tree.body:
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if func.name.startswith("_") or f"{module}.{func.name}" in EXEMPT:
            continue
        args = {a.arg for a in [*func.args.args, *func.args.kwonlyargs]}
        if "tenant_id" not in args:
            problems.append(f"{module}.{func.name}: no tenant_id parameter")
            continue
        tainted: set[str] = set()
        for stmt in _simple_statements(func):
            if not _builds_statement(stmt):
                continue
            refs = _names(stmt, constants)
            if "tenant_id" not in refs and not refs & tainted:
                problems.append(
                    f"{module}.{func.name}:{stmt.lineno}: statement without tenant_id"
                )
            if isinstance(stmt, ast.Assign):
                tainted |= {t.id for t in stmt.targets if isinstance(t, ast.Name)}
    return problems


def test_repository_files_are_discovered() -> None:
    names = {p.stem for p in _repo_files()}
    assert {"chunks", "documents", "users", "conversations", "chat_messages"} <= names
    assert "tenants" not in names


@pytest.mark.parametrize("path", _repo_files(), ids=lambda p: p.stem)
def test_repository_functions_are_tenant_scoped(path: Path) -> None:
    assert violations(path.read_text(), path.stem) == []


def test_exempt_helpers_still_exist() -> None:
    defined = {
        f"{p.stem}.{n.name}"
        for p in _repo_files()
        for n in ast.parse(p.read_text()).body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert EXEMPT <= defined


GOOD = """
async def get(session, tenant_id, document_id):
    return await session.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
"""
BAD_FILTER = GOOD.replace("Document.tenant_id == tenant_id, ", "")
BAD_PARAM = GOOD.replace("session, tenant_id,", "session,")
BAD_TEXT = """
async def f(session, tenant_id):
    await session.execute(text("SELECT 1 FROM documents"))
"""
GOOD_SUBQUERY = """
async def count(session, tenant_id):
    capped = select(Chunk.id).where(Chunk.tenant_id == tenant_id).subquery()
    return await session.execute(select(func.count()).select_from(capped))
"""
BAD_SUBQUERY = GOOD_SUBQUERY.replace(
    "Chunk.tenant_id == tenant_id", "Chunk.id.isnot(None)"
)
SQL_CONSTANT = """
_SQL = "SELECT 1 FROM chunks WHERE tenant_id = :tid"
async def f(session, tenant_id):
    await session.execute(text(_SQL))
"""


def test_checker_ignores_set_config_statements() -> None:
    source = (
        "async def f(session, tenant_id):\n"
        "    await session.execute(text(\"SELECT set_config('a', 'b', true)\"))\n"
    )
    assert violations(source, "m") == []


def test_checker_accepts_scoped_code() -> None:
    assert violations(GOOD, "m") == []
    assert violations(GOOD_SUBQUERY, "m") == []
    assert violations(SQL_CONSTANT, "m") == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (BAD_FILTER, "m.get:3: statement without tenant_id"),
        (BAD_PARAM, "m.get: no tenant_id parameter"),
        (BAD_TEXT, "m.f:3: statement without tenant_id"),
        (BAD_SUBQUERY, "m.count:3: statement without tenant_id"),
    ],
)
def test_checker_rejects_unscoped_code(source: str, expected: str) -> None:
    assert expected in violations(source, "m")
