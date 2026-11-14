#!/usr/bin/env python3
"""Fail when a tenant workflow template writes a path not scoped to one tenant.

`wft-create-tenant.yaml` and `wft-delete-tenant-safe.yaml` both run
concurrently for different tenants.
Two concurrent runs are only safe from a git-merge-conflict-then-`set -e`-abort
if every write they make lands on a path that differs between tenants. That
was violated once already: both `create-tenant` runs used to `awk`-insert a
6-line RBAC block into the single shared
`platform-gitops/argocd/values.yaml` at the same anchor point, so the second
run's `git rebase origin/main` hit a real content conflict and the workflow
step died under `set -e`, leaving an orphaned Vault policy behind
(mctlhq/mctl-gitops#1431). The fix moved that write to a
per-tenant file; this script is the regression test that the pattern does
not come back, here or anywhere else in these templates.

It tokenizes each template's `script.source` block(s) the way a POSIX shell
does (quotes, escapes, line continuations, comments, heredoc bodies,
`$(...)` / backtick substitutions, and the `;` `&&` `||` `|` `&` separators),
then reads every path written by:

- a redirect (`> FILE`, `>> FILE`, `>| FILE`, `&> FILE`, `cat > FILE <<EOF`);
- `sed -i` / `sed --in-place` (every file operand, not the sed script);
- `yq -i` / `yq --inplace` (every file operand, not the expression);
- `tee FILE...`;
- `git add` / `git rm` (every pathspec, honouring `git -C DIR`);
- `mv` / `cp` (the destination, honouring `-t DIR`).

Quoted and unquoted operands are treated alike, because the shell treats them
alike. Simple `VAR=literal` assignments (quoted or not) are resolved back to
their literal form, and the script fails on any resolved path that both sits
under `platform-gitops/` and does not carry the tenant name as a whole
variable reference (`$TENANT`, `${TENANT}`, `$PARAM_TENANT_NAME`,
`${PARAM_TENANT_NAME}`; `$TENANTS_FILE` is a different variable and does not
count).

A script the tokenizer cannot parse (an unterminated quote, heredoc or
substitution, or a process substitution) is an error, never a pass: a write
the gate could not see is not a write that is absent. Likewise a target that
keeps any expansion without one literal value -- `$UNKNOWN`, `$(...)`,
`${F:?}`, `$1`, or a variable assigned two different values -- fails.

Known gaps, none used by the templates today: the source of an `mv` (which
it removes), `rm`, whole-tree staging (`git add -A`, `git add .`,
`git commit -a`), and paths relative to a `cd` (only `git -C` is followed).

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"
TEMPLATE_FILES = (
    "wft-create-tenant.yaml",
    "wft-delete-tenant-safe.yaml",
)

# Real instances of the same "shared file, not parameterized by tenant name"
# shape — but delete-only, part of the CNPG shared-cluster lifecycle, and
# explicitly out of scope for issue 1431 per the proposal's requirements.md.
# Tracked separately; do not add to this list to work around a new finding.
WAIVED_PATHS = {
    "platform-gitops/infra-components/data/cnpg/shared/databases.yaml",
    "platform-gitops/infra-components/data/cnpg/shared/secrets.yaml",
    "platform-gitops/infra-components/data/cnpg/shared/cluster.yaml",
}

TENANT_VARS = ("TENANT", "PARAM_TENANT_NAME")
# A tenant marker is a whole variable reference: `$TENANT` must not be
# followed by another identifier character (`$TENANTS_FILE` is a different
# variable), and a `\$` (escaped, or written inside single quotes) is literal
# text, not a reference.
TENANT_MARKER_RE = re.compile(
    r"(?<!\\)(?:\$\{(?:TENANT|PARAM_TENANT_NAME)\}"
    r"|\$(?:TENANT|PARAM_TENANT_NAME)(?![A-Za-z0-9_]))"
)
VARREF_RE = re.compile(r"(?<!\\)(?:\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*))")
ASSIGNMENT_WORD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)

# Placeholder for the output of a command substitution inside a word. It is
# never a literal path, so a write target that contains it under
# platform-gitops/ is not tenant-scoped unless it also carries a marker.
SUBST = "$(...)"


class ShellParseError(ValueError):
    """The script could not be tokenized; its writes are unknown."""


# ── Tokenizer ──────────────────────────────────────────────────────────────

# Operators, longest first. A leading fd number (`2>`) is handled in the lexer.
OPERATORS = (
    "&>>", "<<-", "<<<", ">>", ">|", ">&", "<&", "<>", "&>", "<<",
    "&&", "||", ";;", "|&", ">", "<", ";", "&", "|", "(", ")",
)
# `<>` opens the file read-write and creates it. `>&` duplicates an fd
# (`2>&1`, `>&-`) unless its target is a word, where bash reads it as `&>`.
REDIRECT_OPS = {">", ">>", ">|", "&>", "&>>", "<>"}
FD_TARGET_RE = re.compile(r"^(?:\d+-?|-)$")
HEREDOC_OPS = {"<<", "<<-"}
SEPARATORS = {"&&", "||", ";;", "|&", ";", "&", "|", "(", ")", "\n"}
METACHARS = set(" \t\n;&|()<>")


class Command:
    """One simple command: its argv words and its redirections."""

    def __init__(self) -> None:
        self.words: list[str] = []
        self.redirects: list[tuple[str, str]] = []


class Lexer:
    def __init__(self, src: str) -> None:
        self.src = src
        self.pos = 0
        self.pending_heredocs: list[tuple[str, bool]] = []
        self.commands: list[Command] = []

    # -- low level ---------------------------------------------------------
    def peek(self, n: int = 0) -> str:
        i = self.pos + n
        return self.src[i] if i < len(self.src) else ""

    def startswith(self, s: str) -> bool:
        return self.src.startswith(s, self.pos)

    def error(self, msg: str) -> ShellParseError:
        line = self.src.count("\n", 0, self.pos) + 1
        return ShellParseError(f"line {line}: {msg}")

    # -- heredocs ----------------------------------------------------------
    def read_heredoc_bodies(self) -> None:
        """Consume the bodies of heredocs opened on the line just ended."""
        for delim, strip_tabs in self.pending_heredocs:
            while True:
                if self.pos >= len(self.src):
                    raise self.error(f"unterminated heredoc <<{delim}")
                end = self.src.find("\n", self.pos)
                if end == -1:
                    end = len(self.src)
                line = self.src[self.pos:end]
                self.pos = end + 1 if end < len(self.src) else end
                check = line.lstrip("\t") if strip_tabs else line
                # Argo `script.source` blocks are indented YAML scalars, so
                # the delimiter commonly carries the block's own indentation
                # after YAML strips it; tolerate surrounding whitespace.
                if check.strip() == delim:
                    break
        self.pending_heredocs = []

    # -- words -------------------------------------------------------------
    def read_single_quoted(self) -> str:
        self.pos += 1
        end = self.src.find("'", self.pos)
        if end == -1:
            raise self.error("unterminated single quote")
        text = self.src[self.pos:end]
        self.pos = end + 1
        # Nothing expands inside single quotes: escape `$` so the marker and
        # variable resolution regexes see literal text.
        return text.replace("$", "\\$")

    def read_double_quoted(self) -> str:
        self.pos += 1
        out = []
        while True:
            c = self.peek()
            if c == "":
                raise self.error("unterminated double quote")
            if c == '"':
                self.pos += 1
                return "".join(out)
            if c == "\\":
                nxt = self.peek(1)
                if nxt == "\n":
                    self.pos += 2
                    continue
                if nxt in ('"', "\\", "`"):
                    out.append(nxt)
                    self.pos += 2
                    continue
                if nxt == "$":
                    out.append("\\$")
                    self.pos += 2
                    continue
                out.append(c)
                self.pos += 1
                continue
            if c == "$":
                out.append(self.read_dollar())
                continue
            if c == "`":
                out.append(self.read_backtick())
                continue
            out.append(c)
            self.pos += 1

    def read_backtick(self) -> str:
        self.pos += 1
        buf = []
        while True:
            c = self.peek()
            if c == "":
                raise self.error("unterminated backtick substitution")
            if c == "\\" and self.peek(1) in ("`", "\\", "$"):
                buf.append(self.peek(1))
                self.pos += 2
                continue
            if c == "`":
                self.pos += 1
                break
            buf.append(c)
            self.pos += 1
        inner = Lexer("".join(buf))
        inner.parse()
        self.commands.extend(inner.commands)
        return SUBST

    def read_balanced(self, open_c: str, close_c: str) -> str:
        """Raw text up to the matching close, quotes respected."""
        depth = 1
        start = self.pos
        while depth:
            c = self.peek()
            if c == "":
                raise self.error(f"unterminated {open_c}")
            if c == "\\":
                self.pos += 2
                continue
            if c == "'":
                self.read_single_quoted()
                continue
            if c == '"':
                self.read_double_quoted()
                continue
            if c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
            self.pos += 1
        return self.src[start:self.pos - 1]

    def read_dollar(self) -> str:
        if self.startswith("$(("):
            self.pos += 3
            self.read_balanced("(", ")")
            if self.peek() != ")":
                raise self.error("unterminated arithmetic expansion")
            self.pos += 1
            return SUBST
        if self.startswith("$("):
            self.pos += 2
            self.parse(until=")")
            return SUBST
        if self.startswith("${"):
            self.pos += 2
            return "${" + self.read_balanced("{", "}") + "}"
        self.pos += 1
        return "$"

    def read_word(self) -> str:
        out = []
        while True:
            c = self.peek()
            if c == "" or c in METACHARS:
                return "".join(out)
            if c == "\\":
                nxt = self.peek(1)
                if nxt == "\n":
                    self.pos += 2
                    continue
                if nxt == "":
                    self.pos += 1
                    return "".join(out)
                out.append("\\$" if nxt == "$" else nxt)
                self.pos += 2
                continue
            if c == "'":
                out.append(self.read_single_quoted())
                continue
            if c == '"':
                out.append(self.read_double_quoted())
                continue
            if c == "$":
                out.append(self.read_dollar())
                continue
            if c == "`":
                out.append(self.read_backtick())
                continue
            out.append(c)
            self.pos += 1

    def read_operator(self) -> str:
        for op in OPERATORS:
            if self.startswith(op):
                self.pos += len(op)
                return op
        raise self.error(f"unexpected character {self.peek()!r}")

    # -- commands ----------------------------------------------------------
    def parse(self, until: str | None = None) -> None:
        cmd = Command()

        def flush() -> None:
            nonlocal cmd
            if cmd.words or cmd.redirects:
                self.commands.append(cmd)
            cmd = Command()

        while True:
            c = self.peek()
            if c == "":
                if until is not None:
                    raise self.error("unterminated $( substitution")
                flush()
                return
            if c in " \t":
                self.pos += 1
                continue
            if c == "\\" and self.peek(1) == "\n":
                self.pos += 2
                continue
            if c == "#":
                end = self.src.find("\n", self.pos)
                self.pos = len(self.src) if end == -1 else end
                continue
            if c == "\n":
                self.pos += 1
                flush()
                if self.pending_heredocs:
                    self.read_heredoc_bodies()
                continue
            if until is not None and c == until:
                self.pos += 1
                flush()
                return
            # `2>file`, `2>&1`: an all-digit word glued to a redirect is an fd.
            m = re.match(r"\d+(?=[<>])", self.src[self.pos:])
            if m:
                self.pos += m.end()
                c = self.peek()
            if c in METACHARS:
                op = self.read_operator()
                if op in SEPARATORS:
                    flush()
                    continue
                self.skip_blanks()
                if op in ("<", ">") and self.peek() == "(":
                    # `done < <(cmd)` / `cmd > >(tee f)`: a process
                    # substitution's body is not read for writes.
                    raise self.error(
                        f"process substitution {op}(...) is not supported; "
                        "use a pipe, a temp file or $(...) instead"
                    )
                target = self.read_word()
                if not target:
                    raise self.error(f"redirect {op!r} without a target")
                if op in HEREDOC_OPS:
                    delim = target.replace("\\$", "$")
                    self.pending_heredocs.append((delim, op == "<<-"))
                    continue
                cmd.redirects.append((op, target))
                continue
            cmd.words.append(self.read_word())

    def skip_blanks(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1


def tokenize(source: str) -> list[Command]:
    lexer = Lexer(source)
    lexer.parse()
    if lexer.pending_heredocs:
        raise lexer.error("unterminated heredoc at end of script")
    return lexer.commands


# ── Write-target extraction ────────────────────────────────────────────────

PREFIX_WORDS = {
    "if", "then", "else", "elif", "do", "while", "until", "!", "{", "}",
    "time", "command", "exec", "nohup", "sudo",
}
DECLARE_WORDS = {"export", "local", "readonly", "declare", "typeset"}


def argv_of(cmd: Command) -> list[str]:
    """The command's argv with assignments, keywords and wrappers stripped."""
    words = list(cmd.words)
    while words:
        w = words[0]
        if w in PREFIX_WORDS or ASSIGNMENT_WORD_RE.match(w):
            words.pop(0)
            continue
        if w == "env":
            words.pop(0)
            while words and (words[0].startswith("-") or ASSIGNMENT_WORD_RE.match(words[0])):
                words.pop(0)
            continue
        break
    if words:
        words[0] = os.path.basename(words[0])
    return words


def split_options(
    args: list[str],
    short_value: str = "",
    long_value: tuple[str, ...] = (),
) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Split GNU-style args into (options, operands).

    `short_value` lists short options that take a value (attached or as the
    next word); `long_value` lists long options that take one (`--x=v` or
    `--x v`). Everything after `--` is an operand.
    """
    opts: list[tuple[str, str | None]] = []
    operands: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            operands.extend(args[i + 1:])
            break
        if a.startswith("--") and len(a) > 2:
            name, eq, val = a.partition("=")
            if eq:
                opts.append((name, val))
            elif name in long_value and i + 1 < len(args):
                opts.append((name, args[i + 1]))
                i += 1
            else:
                opts.append((name, None))
        elif a.startswith("-") and len(a) > 1:
            j = 1
            while j < len(a):
                ch = a[j]
                if ch in short_value:
                    rest = a[j + 1:]
                    if rest:
                        opts.append(("-" + ch, rest))
                    elif i + 1 < len(args):
                        opts.append(("-" + ch, args[i + 1]))
                        i += 1
                    else:
                        opts.append(("-" + ch, None))
                    break
                opts.append(("-" + ch, None))
                j += 1
        else:
            operands.append(a)
        i += 1
    return opts, operands


def sed_targets(args: list[str]) -> list[str]:
    """File operands of an in-place sed; [] when sed does not edit in place.

    GNU sed takes the `-i` suffix attached (`-i.bak`), so `i` ends a short
    option cluster (`-ie` means suffix "e", not `-i -e`). Without `-e`/`-f`
    the first operand is the sed script; with them every operand is a file.
    """
    inplace = False
    has_script = False
    operands: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            operands.extend(args[i + 1:])
            break
        if a.startswith("--") and len(a) > 2:
            name, eq, _ = a.partition("=")
            if name == "--in-place":
                inplace = True
            elif name in ("--expression", "--file", "--line-length"):
                has_script = has_script or name != "--line-length"
                if not eq:
                    i += 1
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], start=1):
                if ch == "i":
                    inplace = True
                    break
                if ch in "efl":
                    has_script = has_script or ch != "l"
                    if j == len(a) - 1:
                        i += 1
                    break
        else:
            operands.append(a)
        i += 1
    if not inplace:
        return []
    return operands if has_script else operands[1:]


YQ_SHORT_VALUE = "opIs"
YQ_LONG_VALUE = (
    "--output-format", "--input-format", "--indent", "--split-exp",
    "--expression", "--from-file", "--front-matter", "--lua-prefix",
    "--lua-suffix", "--properties-separator", "--csv-separator",
    "--tsv-separator", "--xml-attribute-prefix", "--xml-content-name",
    "--xml-proc-inst-prefix", "--xml-directive-name", "--string-interpolation-prefix",
    "--string-interpolation-suffix", "--shell-key-separator",
)
YQ_SUBCOMMANDS = {"eval", "e", "eval-all", "ea"}


def yq_targets(args: list[str]) -> list[str]:
    opts, operands = split_options(args, short_value=YQ_SHORT_VALUE, long_value=YQ_LONG_VALUE)
    names = {n for n, _ in opts}
    if not ({"-i", "--inplace"} & names):
        return []
    if operands and operands[0] in YQ_SUBCOMMANDS:
        operands = operands[1:]
    if {"--expression", "--from-file"} & names:
        return operands
    # `yq -i FILE` (expression omitted) edits FILE in place: with a single
    # operand, count it as a file rather than miss the write.
    return operands[1:] if len(operands) > 1 else operands


def tee_targets(args: list[str]) -> list[str]:
    _, operands = split_options(args)
    return operands


def mv_cp_targets(args: list[str]) -> list[str]:
    opts, operands = split_options(
        args, short_value="tS", long_value=("--target-directory", "--suffix")
    )
    for name, val in opts:
        if name in ("-t", "--target-directory") and val is not None:
            return [val]
    return operands[-1:] if len(operands) >= 2 else []


GIT_GLOBAL_VALUE = ("-C", "-c")


def git_targets(args: list[str]) -> list[str]:
    cwd = ""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in GIT_GLOBAL_VALUE and i + 1 < len(args):
            if args[i] == "-C":
                cwd = os.path.join(cwd, args[i + 1]) if cwd else args[i + 1]
            i += 2
            continue
        i += 1
    if i >= len(args) or args[i] not in ("add", "rm"):
        return []
    _, operands = split_options(
        args[i + 1:], long_value=("--chmod", "--pathspec-from-file")
    )
    if cwd:
        return [os.path.join(cwd, o) for o in operands]
    return operands


TARGET_FUNCS = {
    "sed": sed_targets,
    "yq": yq_targets,
    "tee": tee_targets,
    "mv": mv_cp_targets,
    "cp": mv_cp_targets,
    "git": git_targets,
}


def write_targets(cmd: Command) -> list[str]:
    """Every raw path one simple command writes, removes or renames into place."""
    targets = [
        t
        for op, t in cmd.redirects
        if op in REDIRECT_OPS or (op == ">&" and not FD_TARGET_RE.match(t))
    ]
    argv = argv_of(cmd)
    if argv and argv[0] in TARGET_FUNCS:
        targets.extend(TARGET_FUNCS[argv[0]](argv[1:]))
    return targets


# ── Resolution and verdict ─────────────────────────────────────────────────


RESERVED_PREFIX_WORDS = ("then", "else", "do", "{", "!")


def extract_var_map(commands: list[Command]) -> dict[str, str]:
    """Names with exactly one literal value across the whole script.

    Only plain assignment commands count (`VAR=x`, `export VAR=x`, quoted or
    not). The map ignores order and control flow, so a name assigned two
    different values (on two `if` branches, or reassigned after the write)
    has no single literal form and is left unresolved rather than resolved
    to whichever came last. So is a name ever assigned a command
    substitution.
    """
    values: dict[str, set[str]] = {}
    for cmd in commands:
        words = cmd.words
        # `then F=x`, `else F=y`, `do F=z`: the keyword starts the command.
        while words and words[0] in RESERVED_PREFIX_WORDS:
            words = words[1:]
        if words and words[0] in DECLARE_WORDS:
            words = words[1:]
        if not words or not all(ASSIGNMENT_WORD_RE.match(w) for w in words):
            continue
        for w in words:
            name, value = ASSIGNMENT_WORD_RE.match(w).groups()
            values.setdefault(name, set()).add(value)
    return {
        name: next(iter(vals))
        for name, vals in values.items()
        if len(vals) == 1 and not any(SUBST in v for v in vals)
    }


def resolve_literal(text: str, var_map: dict[str, str], depth: int = 3) -> str:
    """Substitute known ${VAR}/$VAR references, leaving tenant markers alone.

    Bounded recursion (default enough for one level of nesting, e.g.
    DB_FILE="${CNPG_DIR}/databases.yaml" where CNPG_DIR was itself a literal
    assignment) — never used to expand the tenant markers themselves, which
    are excluded by name so they remain visible to the marker check below.
    """
    if depth <= 0:
        return text

    def repl(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name in TENANT_VARS:
            return m.group(0)
        if name in var_map:
            return resolve_literal(var_map[name], var_map, depth - 1)
        return m.group(0)

    return VARREF_RE.sub(repl, text)


# Variables whose value is never inside the gitops checkout.
OUTSIDE_REPO_VARS = ("HOME", "TMPDIR")


# Any unescaped `$` still in a path after the allowed references are taken
# out: `${F:?}`, `${F%x}`, `$1`, `$@`, `$*`, `$$`, ... None of these has a
# literal value here, so where the write lands is unknown.
UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)\$")


def unresolved(path: str) -> bool:
    """True when the path still holds an expansion with no literal value."""
    if SUBST in path:
        return True
    for m in VARREF_RE.finditer(path):
        name = m.group(1) or m.group(2)
        if name not in TENANT_VARS and name not in OUTSIDE_REPO_VARS:
            return True
    return bool(UNESCAPED_DOLLAR_RE.search(VARREF_RE.sub("", path)))


def verdict(path: str) -> str | None:
    """None when the write is safe, else the reason it fails."""
    if TENANT_MARKER_RE.search(path):
        return None
    if unresolved(path):
        # Where this write lands is unknown, so it cannot be shown to be
        # outside platform-gitops/ or tenant-scoped: unknown is not a pass.
        return "write target has no literal value (assign it a literal first)"
    if "platform-gitops/" not in path:
        return None
    if path.endswith(".tmp"):
        return None
    if os.path.normpath(path) in WAIVED_PATHS:
        return None
    return "writes to shared path not parameterized by tenant name and not waived"


def is_pass(path: str) -> bool:
    return verdict(path) is None


def find_write_paths(source: str) -> list[str]:
    """Every resolved path this script writes, removes, or renames into place."""
    commands = tokenize(source)
    var_map = extract_var_map(commands)
    resolved = []
    for cmd in commands:
        for target in write_targets(cmd):
            resolved.append(resolve_literal(target, var_map))
    return resolved


def check_source_reasons(source: str) -> list[tuple[str, str]]:
    """(path, reason) for every failing write in one script.source block.

    Raises ShellParseError when the script cannot be tokenized.
    """
    out = []
    for p in find_write_paths(source):
        reason = verdict(p)
        if reason is not None:
            out.append((p.replace("\\$", "$"), reason))
    return out


def check_source(source: str) -> list[str]:
    """Return every FAILing resolved path found in one script.source block."""
    return [p for p, _ in check_source_reasons(source)]


def check_file(path: Path) -> list[tuple[str, str]]:
    """(path, reason) failures found across every doc/template in a file."""
    failures = []
    for doc in yaml.safe_load_all(path.read_text()):
        if not doc:
            continue
        for source in walk_script_sources(doc):
            failures.extend(check_source_reasons(source))
    return failures


def walk_script_sources(doc):
    """Yield every `script.source` string found anywhere under this YAML doc."""
    if isinstance(doc, dict):
        script = doc.get("script")
        if isinstance(script, dict) and isinstance(script.get("source"), str):
            yield script["source"]
        for v in doc.values():
            yield from walk_script_sources(v)
    elif isinstance(doc, list):
        for item in doc:
            yield from walk_script_sources(item)


OLD_AWK_SOURCE = '''
          # ── Append ArgoCD RBAC entries ──────────────────────────────────────
          ARGOCD_VALUES="platform-gitops/argocd/values.yaml"

          RBAC_BLOCK="
                  # Tenant: ${TENANT}
                  p, role:team-${TENANT}, applications, get, apps/${TENANT}-*, allow
                  g, ${TENANT}, role:team-${TENANT}"

          if grep -q "role:team-${TENANT}," "$ARGOCD_VALUES"; then
            echo "WARNING: already exists, skipping."
          else
            awk -v rbac="$RBAC_BLOCK" '
              /^    secret:/ { print rbac }
              { print }
            ' "$ARGOCD_VALUES" > /tmp/argocd_values_new.yaml
            mv /tmp/argocd_values_new.yaml "$ARGOCD_VALUES"
          fi

          git add \\
            "platform-gitops/tenants/${TENANT}/values.yaml" \\
            "platform-gitops/argocd/values.yaml"
'''

NEW_PER_TENANT_SOURCE = '''
          RBAC_FILE="platform-gitops/argocd/rbac/tenants/${TENANT}.csv"

          if [ -f "$RBAC_FILE" ]; then
            echo "WARNING: already exists, skipping."
          else
            cat > "$RBAC_FILE" <<EOF
          # Tenant: ${TENANT} — generated by wft-create-tenant. No exec (SOC F4).
          p, role:team-${TENANT}, applications, get, apps/${TENANT}-*, allow
          g, ${TENANT}, role:team-${TENANT}
          EOF
          fi

          git add \\
            "platform-gitops/tenants/${TENANT}/values.yaml" \\
            "platform-gitops/tenants/${TENANT}/catalog-info.yaml" \\
            "$RBAC_FILE" \\
            "platform-gitops/argo-workflows/sso-team-${TENANT}.yaml"
'''

AWK_TMP_SOURCE = '''
          CNPG_DIR="platform-gitops/infra-components/data/cnpg/shared"
          if grep -q "name: ${TENANT}-" "${CNPG_DIR}/cluster.yaml" 2>/dev/null; then
            awk -v tenant="${TENANT}-" '
              /^[[:space:]]*- name: / {
                if ($0 ~ "^[[:space:]]*- name: " tenant) { skip=1; next }
                if (skip) { skip=0 }
              }
              skip { next }
              { print }
            ' "${CNPG_DIR}/cluster.yaml" > "${CNPG_DIR}/cluster.yaml.tmp" && mv "${CNPG_DIR}/cluster.yaml.tmp" "${CNPG_DIR}/cluster.yaml"
          fi
'''

SHARED = "platform-gitops/argocd/values.yaml"

# (name, source, path that MUST be reported, or None = must report nothing)
SELFTEST_CASES = (
    ("old awk-into-values.yaml pattern", OLD_AWK_SOURCE, SHARED),
    ("new per-tenant style", NEW_PER_TENANT_SOURCE, None),
    (
        "waived CNPG path via one-level nesting",
        '''
          CNPG_DIR="platform-gitops/infra-components/data/cnpg/shared"
          DB_FILE="${CNPG_DIR}/databases.yaml"
          sed -i "/name: ${TENANT}-/,+8d" "$DB_FILE"
          git add "$DB_FILE"
''',
        None,
    ),
    (
        "unwaived shared path via a variable",
        'SHARED="platform-gitops/some/other/shared.yaml"\ngit add "$SHARED"\n',
        "platform-gitops/some/other/shared.yaml",
    ),
    ("plain echo > FILE redirect", f'echo "not a heredoc" > "{SHARED}"\n', SHARED),
    ("cp into a shared path", f'cp new-fragment.csv "{SHARED}"\n', SHARED),
    ("awk-into-.tmp-then-mv CNPG pattern", AWK_TMP_SOURCE, None),
    ("deploy-key cp outside platform-gitops/", "cp /secrets/deploy-key/ssh-privatekey ~/.ssh/id_ed25519\n", None),
    # gitops bug report ch. 4: the target was taken from the last double-
    # quoted string on the line, i.e. the sed expression itself.
    ("sed -i with an unquoted file", f'sed -i "/${{TENANT}}/d" {SHARED}\n', SHARED),
    ("sed -i, file before a quoted word", f"sed -i -e 's/a/b/' {SHARED}\n", SHARED),
    ("sed -i.bak clustered suffix", f'sed -i.bak "s/a/b/" {SHARED}\n', SHARED),
    ("sed --in-place", f'sed --in-place "s/a/b/" "{SHARED}"\n', SHARED),
    ("sed without -i only reads", f'sed "s/a/b/" {SHARED} | grep x\n', None),
    (
        "sed -i expression naming a shared path, tenant file target",
        'sed -i "s|platform-gitops/argocd/values.yaml|x|" "platform-gitops/tenants/${TENANT}/v.yaml"\n',
        None,
    ),
    # ch. 5: unquoted git add / git rm operands were invisible.
    ("git add unquoted", f"git add {SHARED}\n", SHARED),
    ("git add mixed quoted and unquoted", f'git add "platform-gitops/tenants/$TENANT/x" {SHARED}\n', SHARED),
    ("git rm -rf unquoted", f"git rm -rf {SHARED}\n", SHARED),
    ("git -C platform-gitops add", "git -C platform-gitops add argocd/values.yaml\n", SHARED),
    # ch. 6: `$TENANTS_FILE` is not `$TENANT`.
    ("$TENANTS_FILE is not a tenant marker", 'echo x > "platform-gitops/argocd/$TENANTS_FILE"\n', "platform-gitops/argocd/$TENANTS_FILE"),
    ("${TENANT}s is still tenant-scoped", 'echo x > "platform-gitops/argocd/${TENANT}s.csv"\n', None),
    ("single-quoted $TENANT is literal text", "echo x > 'platform-gitops/argocd/$TENANT.csv'\n", "platform-gitops/argocd/$TENANT.csv"),
    # Found while validating the report: two more write forms.
    ("| tee into a shared path", f"echo x | tee {SHARED} >/dev/null\n", SHARED),
    ("tee -a into a shared path", f"echo x | tee -a /tmp/log {SHARED}\n", SHARED),
    ("yq -i expression then shared file", f"yq -i '.a = 1' {SHARED}\n", SHARED),
    ("yq eval -i with -o value flag", f'yq eval -o yaml -i ".a = 1" "{SHARED}"\n', SHARED),
    ("yq without -i only reads", f"yq '.a' {SHARED} > /tmp/out\n", None),
    ("write inside $(...)", f'X=$(echo y > {SHARED}; echo z)\n', SHARED),
    ("write after && on one line", f'true && echo y >> {SHARED}\n', SHARED),
    (
        "heredoc body text is not a command",
        f"cat > /tmp/x <<'EOF'\necho y > {SHARED}\ngit add {SHARED}\nEOF\n",
        None,
    ),
    ("comment is not a command", f"# git add {SHARED}\n", None),
    ("stderr dup is not a file", 'echo err >&2\necho err 2>&1\nexec 3>&-\n', None),
    (">& with a file word", f"echo x >& {SHARED}\n", SHARED),
    ("unquoted assignment resolves", f"F={SHARED}\nsed -i 's/a/b/' $F\n", SHARED),
    # A target with no literal value cannot be proven tenant-scoped.
    ("unresolved variable target", 'git add "$UNKNOWN_FILE"\n', "$UNKNOWN_FILE"),
    ("command-substitution target", 'F=$(mktemp -p platform-gitops)\necho x > "$F"\n', "$F"),
    ("unresolved dir plus tenant marker", 'echo x > "$BASE/${TENANT}.csv"\n', None),
    ("$HOME target", 'echo x > "$HOME/.netrc"\n', None),
    # Expansions with operators and positional parameters have no literal
    # value either (PR #2614 review).
    ("${F:?} guard target", f'F={SHARED}\nsed -i "/x/d" "${{F:?}}"\n', "${F:?}"),
    ("${F%x} target", f'F={SHARED}\necho x >> "${{F%.bak}}"\n', "${F%.bak}"),
    ("positional target", f'w() {{ echo x > "$1"; }}\nw {SHARED}\n', "$1"),
    ("$@ target", 'git add "$@"\n', "$@"),
    # A name with two values has no single literal value.
    ("assigned on two branches",
     f'if [ "$M" = a ]; then F={SHARED}\nelse F="platform-gitops/tenants/${{TENANT}}/r.csv"; fi\n'
     'echo x >> "$F"\n', "$F"),
    ("assigned on two && paths",
     f'F={SHARED}\n[ -n "$M" ] && F="platform-gitops/tenants/${{TENANT}}/r.csv"\n'
     'echo x >> "$F"\n', "$F"),
    ("assignment after then resolves",
     f'if true; then F={SHARED}; fi\necho x >> "$F"\n', SHARED),
    ("reassigned after the write", f'F={SHARED}\necho x >> "$F"\nF=/tmp/x\n', "$F"),
    ("same value twice resolves", f'F={SHARED}\nF={SHARED}\necho x >> "$F"\n', SHARED),
)

PARSE_ERROR_CASES = (
    ("unterminated double quote", 'git add "platform-gitops/argocd/values.yaml\n'),
    ("unterminated single quote", "sed -i 's/a/b/ platform-gitops/argocd/values.yaml\n"),
    ("unterminated heredoc", "cat > /tmp/x <<EOF\nno end\n"),
    ("unterminated $(", "X=$(echo y\n"),
    ("process substitution", "while read -r l; do :; done < <(cat platform-gitops/a)\n"),
)


def selftest() -> int:
    """Prove the detector fires on every write form and is silent on clean ones."""
    failed = 0
    for name, source, expected in SELFTEST_CASES:
        try:
            got = check_source(source)
        except ShellParseError as exc:
            print(f"FAIL selftest [{name}]: unexpected parse error: {exc}", file=sys.stderr)
            failed += 1
            continue
        if expected is None and got:
            print(f"FAIL selftest [{name}]: false positive {got}", file=sys.stderr)
            failed += 1
        elif expected is not None and expected not in got:
            print(f"FAIL selftest [{name}]: expected {expected!r}, got {got}", file=sys.stderr)
            failed += 1
    for name, source in PARSE_ERROR_CASES:
        try:
            got = check_source(source)
        except ShellParseError:
            continue
        print(f"FAIL selftest [{name}]: parsed without error, got {got}", file=sys.stderr)
        failed += 1
    if failed:
        return 1
    print(
        f"OK selftest: {len(SELFTEST_CASES)} write-form cases and "
        f"{len(PARSE_ERROR_CASES)} unparseable scripts behave as expected"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not TEMPLATES_DIR.is_dir():
        print(f"::error::{TEMPLATES_DIR} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    any_failure = False
    unknown = False
    for fname in TEMPLATE_FILES:
        path = TEMPLATES_DIR / fname
        if not path.is_file():
            print(f"::error::{path} not found", file=sys.stderr)
            any_failure = True
            continue
        try:
            failures = check_file(path)
        except ShellParseError as exc:
            # Could not observe the writes: that is not "no shared writes".
            print(
                f"::error file={fname}::could not tokenize a script.source "
                f"block ({exc}); its writes are unknown",
                file=sys.stderr,
            )
            unknown = True
            continue
        for bad_path, reason in failures:
            print(f"::error file={fname}::{reason}: {bad_path}", file=sys.stderr)
            any_failure = True

    if unknown:
        return 2
    if any_failure:
        return 1

    print(
        f"OK: every write in {', '.join(TEMPLATE_FILES)} is tenant-scoped or waived"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
