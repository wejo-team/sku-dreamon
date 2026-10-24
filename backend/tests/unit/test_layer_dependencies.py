"""전역 레이어의 import 방향과 조회 함수의 저장 금지 경계를 검사한다."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {
    "core": {"core"},
    "models": {"core", "models", "rules"},
    "schemas": {"core", "schemas", "rules"},
    "rules": {"core", "rules"},
    "security": {"core", "security", "rules"},
    "queries": {"core", "models", "schemas", "rules", "queries"},
    "services": {
        "core",
        "models",
        "schemas",
        "rules",
        "security",
        "queries",
        "services",
    },
    "dependencies": {"core", "schemas", "security", "services", "dependencies"},
    "routers": {
        "core",
        "schemas",
        "rules",
        "security",
        "dependencies",
        "queries",
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


def test_imports_follow_global_layer_boundaries() -> None:
    violations = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP)
        layer = relative.parts[0]
        if relative.as_posix() == "main.py":
            continue  # FastAPI 앱을 조립하는 명시적인 진입점이다.
        for target in imported_modules(ast.parse(path.read_text()), relative):
            if target.startswith("app."):
                target_layer = target.split(".")[1]
                if target_layer not in ALLOWED.get(layer, set()):
                    violations.append(f"{relative}: {target}")
            if target.split(".")[0] in {"fastapi", "starlette"} and not (
                layer in {"routers", "dependencies"}
                or relative.as_posix() in HTTP_ADAPTERS
            ):
                violations.append(f"{relative}: HTTP framework {target}")
    assert not violations, "\n".join(violations)


def test_queries_do_not_save_or_lock_rows() -> None:
    forbidden = {
        "flush",
        "commit",
        "rollback",
        "begin",
        "begin_nested",
        "with_for_update",
    }
    violations = []
    for path in sorted((APP / "queries").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and (
                    node.func.attr in forbidden
                    or (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "session"
                        and node.func.attr in {"add", "add_all", "delete"}
                    )
                )
            ):
                violations.append(
                    f"{path.relative_to(APP)}:{node.lineno} {node.func.attr}"
                )
    assert not violations, "\n".join(violations)


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
        imported_modules(ast.parse(source), Path("queries/example.py"))
    )
