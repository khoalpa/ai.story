from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("audio", "studio", "video", "scripts")
TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml"}
IGNORED_PARTS = {"__pycache__", "build", "dist", "local_models", "models"}

SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output"}


def iter_policy_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for source_root in SOURCE_ROOTS:
        base = root / source_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and not (set(path.parts) & IGNORED_PARTS):
                files.append(path)
    return sorted(files)


def _location(path: Path, line: int, root: Path) -> str:
    try:
        display = path.relative_to(root)
    except ValueError:
        display = path
    return f"{display}:{line}"


def check_text(path: Path, text: str, root: Path) -> list[str]:
    errors: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{_location(path, line, root)}: possible committed {label}")

    for match in URL_PATTERN.finditer(text):
        raw_url = match.group(0).rstrip(".,);]")
        parsed = urlparse(raw_url)
        if parsed.scheme.lower() == "http" and (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{_location(path, line, root)}: provider URL must use HTTPS or a loopback host: {raw_url}")
    return errors


def check_subprocess_ast(path: Path, text: str, root: Path) -> list[str]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{_location(path, exc.lineno or 1, root)}: cannot parse Python source: {exc.msg}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
            continue
        if node.func.attr not in SUBPROCESS_CALLS:
            continue
        if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords):
            errors.append(f"{_location(path, node.lineno, root)}: subprocess shell=True is forbidden")
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            errors.append(f"{_location(path, node.lineno, root)}: subprocess command must be an argv sequence, not a string")
    return errors


def check_repository(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in iter_policy_files(root):
        text = path.read_text(encoding="utf-8")
        errors.extend(check_text(path, text, root))
        if path.suffix.lower() == ".py":
            errors.extend(check_subprocess_ast(path, text, root))
    return errors


def main() -> int:
    errors = check_repository()
    if errors:
        print("Security policy check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Security policy check passed (secrets, provider URLs, subprocess usage).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
