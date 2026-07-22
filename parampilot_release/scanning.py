"""Credential, private-import, path, and dependency scans for public source."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from parampilot_release.dependency_scanning import scan_public_dependencies
from parampilot_release.errors import PublicAuditError

PRIVATE_IMPORT_ROOTS = frozenset(
    {"bofire", "django", "parampilot_backend", "parampilot_worker"}
)
SENSITIVE_PATTERNS = (
    ("ParamPilot API credential", re.compile(r"owa_pat-[A-Za-z0-9_-]{20,}")),
    ("PyPI credential", re.compile(r"pypi-[A-Za-z0-9_-]{50,}")),
    ("GitHub credential", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub credential", re.compile(r"github_pat_[A-Za-z0-9_]{60,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "bearer credential",
        re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/-]{16,}", re.I),
    ),
    (
        "network address",
        re.compile(
            r"(?<![0-9])"
            r"(?:(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})\.){3}"
            r"(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})"
            r"(?![0-9])"
        ),
    ),
)
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile("/" + "root" + "/"),
    re.compile(r"/(?:builds|workspace)/[A-Za-z0-9._-]+/"),
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\"),
)


def scan_public_files(
    root: Path,
    relative_paths: Iterable[PurePosixPath],
    *,
    denied_literals: Iterable[str] = (),
) -> None:
    """Reject sensitive text, private imports, and non-registry dependencies.

    Args:
        root: Root containing candidate public files.
        relative_paths: Package-relative file paths to inspect.
        denied_literals: Additional owner-supplied private host or organization text.

    Raises:
        PublicAuditError: If any candidate content crosses a prohibited boundary.

    """
    normalized_denials = tuple(value for value in denied_literals if value)
    for relative_path in relative_paths:
        _scan_sensitive_path(relative_path, normalized_denials)
        path = root.joinpath(*relative_path.parts)
        if path.is_symlink():
            raise PublicAuditError("public source symlink is prohibited")
        if not path.is_file():
            raise PublicAuditError("public source file is missing")
        text = _read_text(path)
        scan_sensitive_text(text, denied_literals=normalized_denials)
        if relative_path.suffix in {".py", ".pyi"}:
            _scan_python_imports(text, relative_path)
    scan_public_dependencies(root)


def scan_sensitive_text(
    text: str,
    *,
    denied_literals: Iterable[str] = (),
) -> None:
    """Reject credential-shaped, absolute-path, and owner-denied public text.

    Args:
        text: Candidate UTF-8 text from source or a built archive member.
        denied_literals: Additional exact private text fragments to reject.

    Returns:
        None after the text passes every sensitive-content check.

    Raises:
        PublicAuditError: If sensitive or owner-denied content is present.

    """
    normalized_denials = tuple(value for value in denied_literals if value)
    _scan_sensitive_text(text, normalized_denials)


def _read_text(path: Path) -> str:
    """Read strict UTF-8 public source without exposing its local absolute path.

    Args:
        path: Local candidate file.

    Returns:
        Decoded text.

    Raises:
        PublicAuditError: If a declared text file is not UTF-8.

    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PublicAuditError("public text file is not UTF-8") from error


def _scan_sensitive_path(
    relative_path: PurePosixPath,
    denied_literals: tuple[str, ...],
) -> None:
    """Reject sensitive text embedded in a candidate public filename.

    Args:
        relative_path: Candidate package-relative source path.
        denied_literals: Additional exact private text fragments.

    Raises:
        PublicAuditError: If the path contains sensitive or owner-denied text.

    """
    value = relative_path.as_posix()
    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(value):
            raise PublicAuditError(f"public source path contains {label}")
    if any(pattern.search(value) for pattern in ABSOLUTE_PATH_PATTERNS):
        raise PublicAuditError("public source path contains an absolute path")
    if any(denied in value for denied in denied_literals):
        raise PublicAuditError("public source path contains owner-denied text")


def _scan_sensitive_text(
    text: str,
    denied_literals: tuple[str, ...],
) -> None:
    """Reject credential-shaped, absolute-path, and caller-denied text.

    Args:
        text: Candidate UTF-8 source.
        denied_literals: Additional exact private text fragments.

    Raises:
        PublicAuditError: If sensitive content is present.

    """
    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise PublicAuditError(f"public source contains {label}")
    if any(pattern.search(text) for pattern in ABSOLUTE_PATH_PATTERNS):
        raise PublicAuditError("public source contains an absolute path")
    if any(value in text for value in denied_literals):
        raise PublicAuditError("public source contains owner-denied text")


def _scan_python_imports(text: str, relative_path: PurePosixPath) -> None:
    """Reject imports from private runtime packages.

    Args:
        text: Candidate Python source.
        relative_path: Privacy-safe path for diagnostics.

    Raises:
        PublicAuditError: If syntax is invalid or a private root is imported.

    """
    try:
        tree = ast.parse(text, filename=relative_path.as_posix())
    except SyntaxError as error:
        raise PublicAuditError("public Python syntax is invalid") from error
    imported: set[str] = set()
    builtins_names = {"builtins"}
    import_names = {"__import__"}
    importlib_names = {"importlib"}
    import_module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            importlib_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "importlib"
            )
            builtins_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "builtins"
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
            if node.module == "importlib":
                import_module_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "import_module"
                )
            elif node.module == "builtins":
                import_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "__import__"
                )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dynamic_root = _dynamic_import_root(
            node,
            builtins_names,
            import_names,
            importlib_names,
            import_module_names,
        )
        if dynamic_root is not None:
            imported.add(dynamic_root)
    private = sorted(imported & PRIVATE_IMPORT_ROOTS)
    if private:
        raise PublicAuditError(f"public source contains private import {private[0]}")


def _dynamic_import_root(
    node: ast.Call,
    builtins_names: set[str],
    import_names: set[str],
    importlib_names: set[str],
    import_module_names: set[str],
) -> str | None:
    """Return a statically named dynamic-import root when one is visible.

    Args:
        node: Candidate Python call expression.
        builtins_names: Local names bound to the ``builtins`` module.
        import_names: Local names bound to the built-in ``__import__``.
        importlib_names: Local names bound to the ``importlib`` module.
        import_module_names: Local names bound to ``importlib.import_module``.

    Returns:
        Imported top-level package name, or ``None`` when not statically known.

    """
    target: ast.expr | None = node.args[0] if node.args else None
    if target is None:
        target = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "name"),
            None,
        )
    if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
        return None
    function = node.func
    calls_importer = (
        isinstance(function, ast.Name)
        and function.id in import_names | import_module_names
    ) or (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and (
            (function.attr == "import_module" and function.value.id in importlib_names)
            or (function.attr == "__import__" and function.value.id in builtins_names)
        )
    )
    if not calls_importer:
        return None
    return target.value.split(".", 1)[0]


__all__ = ["scan_public_files", "scan_sensitive_text"]
