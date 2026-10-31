"""Regression test: Widevine must be configured before QtWebEngine starts.

``QTWEBENGINE_CHROMIUM_FLAGS`` (including ``--widevine-cdm-path``) is read
by Chromium at engine init, i.e. when the first QWebEngineProfile/page is
created — which happens after ``QApplication`` is constructed. If
``configure_widevine()`` ran after that point, the flag would be silently
ignored and protected playback would fail with the system default (or no)
CDM. This test locks the ordering statically via AST so no GUI is needed.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_PY = Path(__file__).resolve().parents[2] / "src" / "amazon_music_desktop" / "app.py"


def _main_body() -> list[ast.stmt]:
    tree = ast.parse(APP_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
            return node.body
    raise AssertionError("app.main() not found")


def _call_order(body: list[ast.stmt]) -> dict[str, int]:
    """Map call name -> first statement index in main()."""
    order: dict[str, int] = {}

    def name_of(func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""

    for index, stmt in enumerate(body):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                name = name_of(node.func)
                if name and name not in order:
                    order[name] = index
    return order


def test_widevine_configured_before_qapplication():
    order = _call_order(_main_body())
    assert "ensure_widevine_user_dir" in order, "startup must prepare user-level CDM dirs"
    assert "configure_widevine" in order, "startup must set --widevine-cdm-path"
    assert "QApplication" in order, "expected QApplication construction in main()"
    assert order["ensure_widevine_user_dir"] < order["QApplication"]
    assert order["configure_widevine"] < order["QApplication"]
    assert order["ensure_widevine_user_dir"] <= order["configure_widevine"]
