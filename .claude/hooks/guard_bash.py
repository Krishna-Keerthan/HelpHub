"""PreToolUse hook (matcher: Bash): block destructive or secret-reading commands.

Best-effort guard, not a sandbox: it inspects the command text only. The .env
reader rules in particular can be bypassed (variables, encodings, scripts);
the real protection for .env is the permissions.deny Read/Edit rules.

Input: hook JSON on stdin (tool_input.command). No network.
Exit codes: 0 = allowed (no output); 2 = blocked, reason on stderr (fed back
to Claude); 1 = unreadable input (non-blocking).
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOME = Path(os.path.expanduser("~"))

_SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
_SHELLS = {"bash", "sh", "zsh", "dash"}
_ENV_READERS = {
    "cat", "head", "tail", "less", "more", "sed", "awk", "gawk", "grep", "egrep",
    "fgrep", "rg", "ag", "source", ".", "bat", "nl", "tac", "strings", "xxd",
    "od", "hexdump", "cut", "sort", "uniq", "tee", "cp", "mv", "base64",
}  # fmt: skip
_PYTHONS = re.compile(r"^python[\d.]*$")
_ENV_IN_CODE = re.compile(r"\.env(?![\w]|\.example)")
_DROP_DB = re.compile(r"\bdrop\s+database\b", re.IGNORECASE)
_DANGEROUS_RELATIVE = {".", "./", "..", "../", "*", "./*", "../*", ".git"}


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _after(tokens: list[str], *words: str) -> list[str] | None:
    """Tokens following the first occurrence of the word sequence, or None."""
    n = len(words)
    for i in range(len(tokens) - n + 1):
        if tuple(tokens[i : i + n]) == words:
            return tokens[i + n :]
    return None


def _is_env_file(token: str) -> bool:
    token = token.lstrip("<>")
    name = token.rsplit("/", 1)[-1]
    if name == ".env":
        return True
    return name.startswith(".env.") and name != ".env.example"


def _normalise(target: str) -> str:
    target = target.replace("${HOME}", "~").replace("$HOME", "~")
    if target.startswith("~"):
        target = str(HOME) + target[1:]
    return os.path.normpath(target) if target.startswith("/") else target


def _dangerous_rm_target(target: str) -> bool:
    if target in _DANGEROUS_RELATIVE:
        return True
    norm = _normalise(target.rstrip("/") or "/")
    if norm.endswith("/*"):
        norm = norm[:-2] or "/"
    protected = {"/", str(HOME), str(REPO_ROOT), *map(str, REPO_ROOT.parents)}
    return norm in protected


def _check_segment(seg: list[str]) -> str | None:
    # Shell wrappers: recurse into the quoted script.
    if seg[0] in _SHELLS or seg[0] == "eval":
        for token in seg[1:]:
            if " " in token:
                reason = check(token)
                if reason:
                    return reason

    if "docker" in seg or "docker-compose" in seg:
        down = _after(seg, "down")
        if down is not None and any(t in ("-v", "--volumes") for t in down):
            return "docker compose down with volumes deletes the database volume"
        if _after(seg, "volume", "rm") is not None or _after(seg, "volume", "remove"):
            return "docker volume rm is blocked"
        if _after(seg, "volume", "prune") is not None:
            return "docker volume prune is blocked"
        prune = _after(seg, "system", "prune")
        if prune is not None and "--volumes" in prune:
            return "docker system prune --volumes is blocked"

    if "git" in seg:
        push = _after(seg, "push")
        if push is not None and any(
            t in ("-f", "--force") or t.startswith("--force-") or t.startswith("+")
            for t in push
        ):
            return "git force push is blocked"
        if _after(seg, "reset", "--hard") is not None:
            return "git reset --hard is blocked"
        clean = _after(seg, "clean")
        if clean is not None and any(
            t == "--force" or (re.fullmatch(r"-[a-zA-Z]+", t) and "f" in t)
            for t in clean
        ):
            return "git clean -f is blocked"
        commit = _after(seg, "commit")
        if commit is not None and any(
            t == "-n" or (re.fullmatch(r"-[a-zA-Z]+", t) and "n" in t) for t in commit
        ):
            return "git commit -n (--no-verify) is blocked"


    if "--no-verify" in seg and seg[0] != "echo":
        return "--no-verify (skipping hooks) is blocked"

    rm = _after(seg, "rm")
    if rm is not None:
        flags = [t for t in rm if t.startswith("-")]
        recursive = any(
            t == "--recursive" or (not t.startswith("--") and re.search(r"[rR]", t))
            for t in flags
        )
        if "--no-preserve-root" in flags:
            return "rm --no-preserve-root is blocked"
        targets = [t for t in rm if not t.startswith("-")]
        if recursive and any(_dangerous_rm_target(t) for t in targets):
            return "recursive rm of /, ~, the repo root or a parent is blocked"

    if seg[0] != "git" and _DROP_DB.search(" ".join(seg)):
        return "DROP DATABASE is blocked"

    # Best-effort .env readers.
    readers = [t for t in seg if t in _ENV_READERS]
    if readers and any(_is_env_file(t) for t in seg):
        return "reading .env is blocked (best-effort)"
    if any(_PYTHONS.match(t.rsplit("/", 1)[-1]) for t in seg) and "-c" in seg:
        code = seg[seg.index("-c") + 1 :] if seg.index("-c") + 1 < len(seg) else []
        if any(_ENV_IN_CODE.search(t) for t in code):
            return "python code touching .env is blocked (best-effort)"
    if any(t.startswith("<") and _is_env_file(t) for t in seg):
        return "reading .env is blocked (best-effort)"
    return None


def check(command: str) -> str | None:
    """Return the reason ``command`` must be blocked, or None if allowed."""
    try:
        segments = _segments(_tokenize(command))
    except ValueError:  # unbalanced quotes: fall back to whitespace split
        segments = _segments(command.split())
    for seg in segments:
        reason = _check_segment(seg)
        if reason:
            return reason
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command", "")
    except (json.JSONDecodeError, AttributeError) as exc:
        print(f"guard_bash: unreadable hook input: {exc}", file=sys.stderr)
        return 1
    try:
        reason = check(command)
    except Exception as exc:  # fail closed: a guard bug must not allow a command
        print(f"guard_bash: internal error ({type(exc).__name__}); blocked", file=sys.stderr)
        return 2
    if reason:
        print(f"Blocked by guard_bash: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
