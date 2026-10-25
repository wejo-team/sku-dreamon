"""전역 레이어의 import 방향과 서비스·저장소의 DB 책임 경계를 검사한다."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {
    "cli": {"core", "schemas", "services"},
    "core": {"core"},
    "models": {"core", "models", "rules"},
    "schemas": {"core", "schemas", "rules"},
    "rules": {"core", "rules"},
    "security": {"core", "security", "rules"},
    "repositories": {"core", "models", "rules", "repositories"},
    "services": {
        "core",
        "models",
        "schemas",
        "rules",
        "security",
        "repositories",
        "services",
    },
    "dependencies": {"core", "schemas", "security", "services", "dependencies"},
    "routers": {
        "core",
        "schemas",
        "rules",
        "security",
        "dependencies",
        "services",
        "routers",
    },
}
# 기존 공통 HTTP 어댑터와 앱 조립 지점만 예외로 둔다. DB 기반은 포함하지 않는다.
HTTP_ADAPTERS = {
    "main.py",
    "core/http/dependencies.py",
    "core/http/handlers.py",
    "core/http/routers.py",
}


def imported_modules(tree: ast.AST, relative_path: Path) -> Iterator[str]:
    package = ["app", *relative_path.parent.parts]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (name.name for name in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            if node.module:
                base.extend(node.module.split("."))
            # `from app import services`와 상대 import도 같은 경계로 검사한다.
            yield from (".".join([*base, name.name]) for name in node.names)


def import_violations(tree: ast.AST, relative: Path) -> list[str]:
    layer = relative.parts[0]
    violations = []
    for target in imported_modules(tree, relative):
        if target.startswith("app."):
            target_layer = target.split(".")[1]
            if target_layer not in ALLOWED.get(layer, set()):
                violations.append(f"{relative}: {target}")
            if layer == "repositories" and (
                target.startswith("app.core.http")
                or target.startswith("app.core.exceptions")
            ):
                violations.append(f"{relative}: HTTP/business dependency {target}")
        if target.split(".")[0] in {"fastapi", "starlette"} and not (
            layer in {"routers", "dependencies"} or relative.as_posix() in HTTP_ADAPTERS
        ):
            violations.append(f"{relative}: HTTP framework {target}")
        if layer in {"services", "routers"} and target.startswith("sqlalchemy"):
            if target != "sqlalchemy.ext.asyncio.AsyncSession" and not (
                target.startswith("sqlalchemy.exc.")
            ):
                violations.append(f"{relative}: SQL construction {target}")
    return violations


def session_receivers(tree: ast.AST) -> set[str]:
    """세션 매개변수와 Database.session context가 바인딩한 이름을 찾는다."""
    types = {"AsyncSession", "DatabaseSession"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            types.update(
                name.asname or name.name
                for name in node.names
                if name.name in {"AsyncSession", "DatabaseSession"}
            )
    names = {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg)
        and node.annotation is not None
        and ast.unparse(node.annotation).split(".")[-1] in types
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.withitem)
            and isinstance(node.context_expr, ast.Call)
            and isinstance(node.context_expr.func, ast.Attribute)
            and node.context_expr.func.attr == "session"
            and isinstance(node.optional_vars, ast.Name)
        ):
            names.add(node.optional_vars.id)
    return names


def session_violations(tree: ast.AST, relative: Path) -> list[str]:
    layer = relative.parts[0]
    sessions = session_receivers(tree)
    violations = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in sessions
        ):
            method = node.func.attr
            if layer == "services" and method not in {
                "commit",
                "rollback",
                "in_transaction",
                "connection",
            }:
                violations.append(f"{relative}:{node.lineno} session.{method}")
            if layer == "routers" or (
                layer == "repositories"
                and method
                in {
                    "commit",
                    "rollback",
                    "begin",
                    "begin_nested",
                    "connection",
                    "close",
                    "invalidate",
                    "reset",
                }
            ):
                violations.append(f"{relative}:{node.lineno} session.{method}")
        if layer == "repositories" and isinstance(node, ast.Constant):
            if isinstance(node.value, str) and (
                node.value == "isolation_level"
                or "SET TRANSACTION" in node.value.upper()
            ):
                violations.append(f"{relative}:{node.lineno} transaction setting")
    return violations


def test_imports_and_db_calls_follow_global_layer_boundaries() -> None:
    violations = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP)
        if relative.as_posix() == "main.py":
            continue  # FastAPI 앱을 조립하는 명시적인 진입점이다.
        tree = ast.parse(path.read_text())
        violations.extend(import_violations(tree, relative))
        violations.extend(session_violations(tree, relative))
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "layer, source",
    [
        ("routers", "from app.repositories import teams"),
        ("routers", "from app.queries.teams import get_team_detail"),
        ("services", "from sqlalchemy import select as query"),
        ("services", "async def read(db: AsyncSession):\n    await db.scalar(query)"),
        (
            "services",
            "from sqlalchemy.ext.asyncio import AsyncSession as Session\n"
            "async def save(db: Session):\n    db.add(row)",
        ),
        (
            "services",
            "async def auth(database):\n    async with database.session() as db:\n"
            "        await db.execute(query)",
        ),
        ("repositories", "from app.schemas.teams import TeamDetail"),
        ("repositories", "from app.core.http.schemas import PageMeta"),
        ("repositories", "from app.core import exceptions"),
        ("repositories", "async def save(db: AsyncSession):\n    await db.commit()"),
        ("repositories", "options = {'isolation_level': 'REPEATABLE READ'}"),
    ],
)
def test_boundary_check_rejects_cross_layer_responsibilities(
    layer: str, source: str
) -> None:
    tree = ast.parse(source)
    relative = Path(layer) / "example.py"
    assert import_violations(tree, relative) or session_violations(tree, relative)


@pytest.mark.parametrize(
    "layer, source",
    [
        (
            "services",
            "from sqlalchemy.ext.asyncio import AsyncSession\n"
            "from sqlalchemy.exc import IntegrityError\n"
            "from app.repositories import teams\n"
            "async def save(db: AsyncSession):\n    row.name = 'new'\n"
            "    await teams.flush(db)\n    await db.commit()",
        ),
        (
            "repositories",
            "from sqlalchemy import select\n"
            "async def read(db: AsyncSession):\n"
            "    return await db.scalar(select(Model).with_for_update()"
            ".execution_options(populate_existing=True))",
        ),
    ],
)
def test_boundary_check_allows_owned_responsibilities(layer: str, source: str) -> None:
    tree = ast.parse(source)
    relative = Path(layer) / "example.py"
    assert not import_violations(tree, relative)
    assert not session_violations(tree, relative)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import app.services.teams as teams", "app.services.teams"),
        ("from app import services as commands", "app.services"),
        ("from ..services import teams", "app.services.teams"),
        ("if TYPE_CHECKING:\n    from .. import services", "app.services"),
    ],
)
def test_import_check_includes_aliases_relative_and_type_checking(
    source: str, expected: str
) -> None:
    assert expected in set(
        imported_modules(ast.parse(source), Path("repositories/example.py"))
    )
