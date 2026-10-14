"""PreToolUse hook (matcher: Bash): block destructive or secret-reading commands.

Best-effort guard, not a sandbox: it inspects the command text only. The .env
reader rules in particular can be bypassed (variables, encodings, scripts);
the real protection for .env is the permissions.deny Read/Edit rules.

Input: hook JSON on stdin (tool_input.command). No network.
Exit codes: 0 = allowed (no output); 2 = blocked, reason on stderr (fed back
to Claude). Fails closed: unreadable hook input and unparseable commands are
blocked (exit 2), never allowed.
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


def _is_volumes_flag(token: str) -> bool:
    """``-v``, ``--volumes`` or a short-flag cluster containing v (``-fv``)."""
    if token == "--volumes":
        return True
    return bool(re.fullmatch(r"-[a-zA-Z]+", token)) and "v" in token


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
        if down is not None and any(_is_volumes_flag(t) for t in down):
            return "docker compose down with volumes deletes the database volume"
        for verb in ("rm", "remove", "prune"):
            if _after(seg, "volume", verb) is not None:
                return f"docker volume {verb} is blocked"
        if _after(seg, "system", "prune") is not None:
            return "docker system prune is blocked"

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


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")


def _split_heredocs(command: str) -> tuple[str, list[str]]:
    """The command without heredoc bodies (they are data, not shell), and the bodies."""
    lines = command.split("\n")
    kept: list[str] = []
    bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for match in _HEREDOC.finditer(line):
            body: list[str] = []
            while i < len(lines) and lines[i].strip() != match[2]:
                body.append(lines[i])
                i += 1
            i += 1  # the terminator line
            bodies.append("\n".join(body))
    return "\n".join(kept), bodies


def check(command: str) -> str | None:
    """Return the reason ``command`` must be blocked, or None if allowed."""
    stripped, bodies = _split_heredocs(command)
    try:
        segments = _segments(_tokenize(stripped))
    except ValueError:  # unbalanced quotes: fail closed
        return "unparseable command (cannot be inspected)"
    for seg in segments:
        reason = _check_segment(seg)
        if reason:
            return reason
    # A heredoc fed to a shell is code: inspect it too.
    if bodies and any(seg[0] in _SHELLS or seg[0] == "eval" for seg in segments):
        for body in bodies:
            reason = check(body)
            if reason:
                return reason
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        tool_input = data["tool_input"]
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            raise TypeError("command is not a string")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(
            f"guard_bash: unreadable hook input ({type(exc).__name__}); blocked",
            file=sys.stderr,
        )
        return 2
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
