#!/usr/bin/env python3
"""Fail when a shell variable is interpolated into a yq expression.

yq's expression language is not data. A value that closes the string literal
keeps executing, against a file the pipeline holds write access to:

    DOMAIN='a.example.com")) | .image.tag = "pwned" # '
    yq eval -i "del(.ingress.hosts[] | select(. == \\"${DOMAIN}\\"))" values.yaml
    # → .image.tag is now "pwned"

The fix is to pass values through the environment, where yq treats them as
data no matter what they contain:

    export DOMAIN
    yq eval -i '.ingress.hosts += [strenv(DOMAIN)]' values.yaml

strenv() substitutes in value and comparison positions but NOT in an
expression *path*: `.env.${key}` cannot be parameterised, so a key is
additionally shape-checked at the point it enters the loop and written via the
`.env[strenv(KEY)]` subscript instead.

This is a ratchet. BASELINE records the sites that legitimately still carry a
variable; the check fails on anything not listed, so the count can go down and
never up. Companion to validate-shell-param-interpolation.py, which guards the
neighbouring invariant (Argo parameters interpolated into shell text,
gitops#992). See gitops#990, #995, #997.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "platform-gitops/argo-workflows/cluster-templates"

# (file, template, expression) that may keep a variable, each with a reason.
# Shrink this list, never grow it.
BASELINE: set[tuple[str, str, str]] = {
    # config_patch IS the expression, not a value in one — there is no
    # strenv() shape for a caller-supplied yq *program*. It is defended
    # differently: mctl-api drops parameters an operation does not declare
    # (config_patch is not declared on deploy-service, mctlhq/mctl-api#246),
    # and the call site checks every `|`-separated segment against the
    # roots its only intended producer writes (.resources, .env,
    # .configMaps), rejecting `(`, `)` and `,` because those re-root the
    # expression regardless of the prefix a segment carries.
    ("tpl-git-commit.yaml", "commit-service", '"$CONFIG_PATCH"'),
}


# Options that CONSUME the next word (or take it attached: `-ojson`,
# `--output-format=json`). Treating one of these as a plain switch makes
# `yq eval -o json "$EXPR" f.yaml` report `json` as the expression — which
# contains no `$`, so the real one is never inspected (agy P2 on
# gitops#1025). Treating a plain switch as one of these does the opposite:
# `-C` is `--colors` and takes no value, so listing it here made
# `yq -C ".a = \"$X\"" f` skip the expression and inspect `f` (gitops bug
# report ch. 9). `-f` is `--front-matter` (PR #2616 review). Source:
# `yq --help` (mikefarah/yq v4.47): -f -I -o -p -s take a value; -C -e -i
# -M -N -n -P -r -v do not.
SHORT_VALUE_FLAGS = "fopIs"
LONG_VALUE_FLAGS = {
    "--output-format", "--input-format", "--indent", "--split-exp",
    "--expression", "--from-file", "--front-matter", "--lua-prefix",
    "--lua-suffix", "--properties-separator", "--split-exp-file", "--csv-separator",
    "--tsv-separator", "--xml-attribute-prefix", "--xml-content-name",
    "--xml-proc-inst-prefix", "--xml-directive-name",
    "--string-interpolation-prefix", "--string-interpolation-suffix",
    "--shell-key-separator",
}
# Flags whose value is itself a yq expression, so it is inspected too.
EXPRESSION_FLAGS = {"--expression", "-s", "--split-exp"}
SUBCOMMANDS = {"eval", "e", "eval-all", "ea"}

# Words that operate on a whole segment, so `yq` after them is still the
# command being run.
SEGMENT_SEPARATORS = ("&&", "||", "|&", ";;", "|", ";", "&", "(", ")")


class ShellParseError(ValueError):
    """The script could not be split; its yq calls are unknown."""


class Splitter:
    """Split a shell script into simple-command segments of raw words.

    A segment ends at `|`, `||`, `&&`, `;`, `&`, a newline or a subshell
    paren outside quotes, so every `yq` in a pipeline or `&&` chain is its
    own segment (gitops bug report ch. 10). The body of a `$(...)` or
    backtick substitution is split as segments of its own as well, while the
    word that holds it keeps its raw text. Words keep their quotes, so the
    check below can tell `'$i'` (yq's own variable) from `"$X"` (a shell
    expansion). Heredoc bodies are data and are skipped. An unterminated
    quote, substitution or heredoc raises ShellParseError.
    """

    def __init__(self, src: str) -> None:
        self.src = src
        self.pos = 0
        self.segments: list[list[str]] = []
        self.heredocs: list[tuple[str, bool, bool, bool]] = []
        # Heredoc bodies fed to a shell are code, not data: (body, quoted).
        self.code_bodies: list[tuple[str, bool]] = []
        # First segment of the current line: a heredoc opened on this line
        # feeds a shell when any segment on the line names one, which covers
        # `cat <<EOF | sh` where the shell is in the next pipeline stage.
        self.line_start = 0

    def peek(self, n: int = 0) -> str:
        i = self.pos + n
        return self.src[i] if i < len(self.src) else ""

    def error(self, msg: str) -> ShellParseError:
        line = self.src.count("\n", 0, self.pos) + 1
        return ShellParseError(f"line {line}: {msg}")

    def skip_heredoc_bodies(self) -> None:
        line_shell = any(feeds_shell(seg) for seg in self.segments[self.line_start:])
        for delim, strip_tabs, quoted, to_shell in self.heredocs:
            to_shell = to_shell or line_shell
            start = self.pos
            while True:
                if self.pos >= len(self.src):
                    raise self.error(f"unterminated heredoc <<{delim}")
                end = self.src.find("\n", self.pos)
                end = len(self.src) if end == -1 else end
                line = self.src[self.pos:end]
                self.pos = min(end + 1, len(self.src))
                if (line.lstrip("\t") if strip_tabs else line).strip() == delim:
                    if to_shell:
                        body_end = self.pos - len(line) - (1 if self.src[self.pos - 1:self.pos] == "\n" else 0)
                        self.code_bodies.append((self.src[start:max(start, body_end)], quoted))
                    break
        self.heredocs = []

    def read_single(self) -> None:
        end = self.src.find("'", self.pos + 1)
        if end == -1:
            raise self.error("unterminated single quote")
        self.pos = end + 1

    def read_double(self) -> None:
        self.pos += 1
        while True:
            c = self.peek()
            if c == "":
                raise self.error("unterminated double quote")
            if c == "\\":
                self.pos += 2
            elif c == '"':
                self.pos += 1
                return
            elif c == "$" and self.peek(1) == "(":
                self.read_substitution()
            elif c == "`":
                self.read_backtick()
            else:
                self.pos += 1

    def read_substitution(self) -> None:
        """`$(...)` / `$((...))`: split the body as segments of its own."""
        self.pos += 2
        self.parse(until=")")

    def read_backtick(self) -> None:
        end = self.pos + 1
        while True:
            if end >= len(self.src):
                raise self.error("unterminated backtick substitution")
            if self.src[end] == "\\":
                end += 2
                continue
            if self.src[end] == "`":
                break
            end += 1
        inner = Splitter(self.src[self.pos + 1:end].replace("\\`", "`"))
        inner.parse()
        self.segments.extend(inner.segments)
        self.pos = end + 1

    def read_word(self) -> str:
        start = self.pos
        while True:
            c = self.peek()
            if c == "" or c in " \t\n;&|()":
                break
            if c == "\\":
                self.pos += 2
            elif c == "'":
                self.read_single()
            elif c == '"':
                self.read_double()
            elif c == "$" and self.peek(1) == "(":
                self.read_substitution()
            elif c == "`":
                self.read_backtick()
            else:
                self.pos += 1
        return self.src[start:self.pos].replace("\\\n", "")

    def parse(self, until: str | None = None) -> None:
        words: list[str] = []

        def flush() -> None:
            nonlocal words
            if words:
                self.segments.append(words)
            words = []

        depth = 0  # bare `(` inside a $( ... ), e.g. a `case` pattern list
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
                if self.heredocs:
                    self.skip_heredoc_bodies()
                self.line_start = len(self.segments)
                continue
            if until is not None and c == until and depth == 0:
                self.pos += 1
                flush()
                return
            sep = next((op for op in SEGMENT_SEPARATORS if self.src.startswith(op, self.pos)), None)
            if sep:
                if until is not None and sep == "(":
                    depth += 1
                elif until is not None and sep == ")":
                    depth -= 1
                self.pos += len(sep)
                flush()
                continue
            word = self.read_word()
            m = re.fullmatch(r"\d*<<(-?)", word)
            if m or word in ("<<", "<<-"):
                strip = word.endswith("-")
                while self.peek() in (" ", "\t"):
                    self.pos += 1
                delim = self.read_word()
                self.heredocs.append(
                    (unquote(delim), strip, unquote(delim) != delim, feeds_shell(words))
                )
                words.extend([word, delim])
                continue
            m = re.match(r"^\d*<<(-?)(.+)$", word)
            if m and not word.startswith("<<<") and "<<<" not in word:
                d = m.group(2)
                self.heredocs.append((unquote(d), m.group(1) == "-", unquote(d) != d, feeds_shell(words)))
            words.append(word)


# A word that names a shell makes the rest of the segment code run as a
# string: `sh -c "yq ..."`, `bash <<EOF`, `kubectl exec ... -- sh <<EOF`.
SHELLS = {"sh", "bash", "dash", "ash", "zsh", "ksh"}
RAW_EXPANSION = re.compile(r"(?<!\\)[$`]")
YQ_WORD = re.compile(r"(?<![\w./-])yq(?![\w.-])")


def feeds_shell(words: list[str]) -> bool:
    return any(unquote(w).rsplit("/", 1)[-1] in SHELLS for w in words)


def unquote(word: str) -> str:
    return word.replace("'", "").replace('"', "").replace("\\", "")


def split_source(source: str) -> Splitter:
    splitter = Splitter(source)
    splitter.parse()
    if splitter.heredocs:
        raise splitter.error("unterminated heredoc at end of script")
    return splitter


def segments_of(source: str) -> list[list[str]]:
    return split_source(source).segments


def has_expansion(word: str) -> bool:
    """True when the shell would expand something in this raw word.

    `$` and backticks expand outside single quotes only, so yq's own
    variables (`'.items[] as $i | $i.name'`) are not shell interpolation
    (gitops bug report ch. 23).
    """
    quote = None
    i = 0
    while i < len(word):
        c = word[i]
        if quote == "'":
            if c == "'":
                quote = None
        elif c == "\\":
            i += 2
            continue
        elif c == '"':
            quote = None if quote == '"' else '"'
        elif c == "'" and quote is None:
            quote = "'"
        elif c in "$`":
            return True
        i += 1
    return False


REDIRECT_WORD = re.compile(r"^\d*(?:[<>]|&>)")


def expressions_of(words: list[str]) -> list[str]:
    """Every yq expression argument in one segment (raw, quotes kept)."""
    idx = next(
        (i for i, w in enumerate(words) if unquote(w) == "yq" or unquote(w).endswith("/yq")),
        None,
    )
    if idx is None:
        return []
    args = []
    rest = words[idx + 1:]
    i = 0
    while i < len(rest):
        w = rest[i]
        if REDIRECT_WORD.match(w):
            # `> out`, `2>/dev/null`: skip the target too when it is separate.
            if re.fullmatch(r"\d*(?:[<>]{1,2}|&>{1,2}|[<>]&)", w):
                i += 1
            i += 1
            continue
        args.append(w)
        i += 1

    exprs: list[str] = []
    expression_given = False
    subcommand_seen = False
    i = 0
    while i < len(args):
        a = args[i]
        bare = unquote(a)
        if bare == "--":
            ops = args[i + 1:]
            if not expression_given and ops:
                exprs.append(ops[0])
            break
        if bare.startswith("--") and len(bare) > 2:
            name, eq, _ = bare.partition("=")
            if eq:
                value = a.split("=", 1)[1]
            elif name in LONG_VALUE_FLAGS and i + 1 < len(args):
                i += 1
                value = args[i]
            else:
                i += 1
                continue
            if name in EXPRESSION_FLAGS:
                exprs.append(value)
            if name in ("--expression", "--from-file"):
                expression_given = True
            i += 1
            continue
        if bare.startswith("-") and len(bare) > 1:
            for j in range(1, len(bare)):
                ch = bare[j]
                if ch in SHORT_VALUE_FLAGS:
                    if j + 1 < len(bare):
                        value = bare[j + 1:]
                    elif i + 1 < len(args):
                        i += 1
                        value = args[i]
                    else:
                        value = ""
                    if "-" + ch in EXPRESSION_FLAGS and value:
                        exprs.append(value)
                    break
            i += 1
            continue
        if not subcommand_seen and not exprs and bare in SUBCOMMANDS:
            subcommand_seen = True
            i += 1
            continue
        if not expression_given:
            exprs.append(a)
            expression_given = True
        i += 1
    return exprs


def scan_source(source: str):
    """Yield every interpolated yq expression in one script source.

    Code run as a string is not split again, so it fails closed instead
    (PR #2616 review): in a segment that names a shell, any later word that
    mentions yq and holds a `$` or backtick is reported whole -- even inside
    single quotes, since the inner shell parses that text again; a heredoc
    fed to a shell is scanned as code, and when its delimiter is unquoted
    (so the outer shell expands the body first) any line that mentions yq
    and holds a `$` or backtick is reported.
    """
    splitter = split_source(source)
    for words in splitter.segments:
        for expr in expressions_of(words):
            if has_expansion(expr):
                yield expr.strip()
        shell_at = next(
            (i for i, w in enumerate(words) if unquote(w).rsplit("/", 1)[-1] in SHELLS), None
        )
        if shell_at is not None:
            for w in words[shell_at + 1:]:
                if YQ_WORD.search(w) and RAW_EXPANSION.search(w):
                    yield w.strip()
    for body, quoted in splitter.code_bodies:
        if quoted:
            yield from scan_source(body)
        else:
            # The outer shell joins continuations and turns `\$X` into `$X`
            # before the inner shell runs the body, so both count here.
            for line in body.replace("\\\n", " ").splitlines():
                if YQ_WORD.search(line) and re.search(r"[$`]", line):
                    yield line.strip()


def scan(directory: Path):
    """Yield (file, template, expression) for every interpolated yq call.

    Raises ShellParseError (with the file and template named) when a script
    cannot be split: a call the check could not see is not a clean call.
    """
    for path in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc:
                continue
            for tmpl in (doc.get("spec") or {}).get("templates") or []:
                source = (tmpl.get("script") or {}).get("source")
                if not source:
                    continue
                try:
                    for expr in scan_source(source):
                        yield path.name, tmpl.get("name"), expr
                except ShellParseError as exc:
                    raise ShellParseError(f"{path.name} / {tmpl.get('name')}: {exc}") from None


# (name, script source, must the check fire?)
SELFTEST_CASES = (
    ("double-quoted interpolation", 'yq eval -i ".ingress.hosts += [\\"${DOMAIN}\\"]" values.yaml', True),
    ("strenv() shape", "export DOMAIN\nyq eval -i '.ingress.hosts += [strenv(DOMAIN)]' \"${DIR}/values.yaml\"", False),
    # An escaped quote must not end the word early (agy P2).
    ("escaped quote", 'yq eval -i ".foo == \\" ${INJECT} \\"" values.yaml', True),
    # `-o json` consumes its argument (agy P2 on gitops#1025).
    ("-o value flag", 'yq eval -o json ".image.tag = \\"${TAG}\\"" values.yaml', True),
    ("-ojson attached value", 'yq -ojson ".a = \\"$X\\"" f', True),
    ("--output-format=json", 'yq --output-format=json ".a = \\"$X\\"" f', True),
    ("line continuation", 'yq eval -i \\\n  ".image.tag = \\"${TAG}\\"" \\\n  values.yaml', True),
    # ch. 9: -C is --colors and takes no value.
    ("-C is a switch", 'yq -C ".a = \\"$X\\"" f', True),
    ("-s takes a value", 'yq -s \'.name\' ".a = \\"$X\\"" f', True),
    ("-s expression interpolated", 'yq -s ".$X" \'.a\' f', True),
    # ch. 10: every yq in a chain is checked.
    ("second yq in a pipe", 'cat f | yq . | yq -i ".a=\\"$X\\"" f', True),
    ("yq after &&", 'true && yq -i ".a=\\"$X\\"" f', True),
    ("yq after ;", 'echo x; yq -i ".a=\\"$X\\"" f', True),
    ("yq inside $(...)", 'V=$(yq ".a.\\"$X\\"" f)', True),
    ("yq inside quoted $(...)", 'V="$(yq ".a.\\"$X\\"" f)"', True),
    ("yq inside backticks", 'V=`yq ".a.$X" f`', True),
    ("clean chain", "cat f | yq '.a' | yq -i '.b = strenv(B)' f && yq '.c' g", False),
    # ch. 11: value flags hide nothing.
    ("--front-matter value", 'yq --front-matter process ".a=\\"$X\\"" f', True),
    ("--expression value", 'yq --expression ".a=\\"$X\\"" f', True),
    ("--expression= value", 'yq --expression=".a=\\"$X\\"" f', True),
    ("--expression, $ only in file", "yq --expression '.a' \"$F\"", False),
    ("--from-file, $ only in file", 'yq --from-file prog.yq "$F"', False),
    # ch. 23: yq's own variables inside single quotes are not shell expansion.
    ("yq variable in single quotes", "yq eval '.items[] as $i | $i.name' f.yaml", False),
    ("yq $__ in single quotes", "yq -i '.x as $v | .y = $v' f", False),
    ("shell var in a file argument only", 'yq -i \'.a = 1\' "$DIR/values.yaml"', False),
    ("unquoted $X expression", "yq $X f", True),
    ("single-then-double concatenation", "yq '.a = \"'\"$X\"'\"' f", True),
    ("multi-line single-quoted expression", "yq -i '\n  .a = 1 |\n  .b = 2\n' f", False),
    ("multi-line double-quoted expression", 'yq -i "\n  .a = 1 |\n  .b = \\"$X\\"\n" f', True),
    ("redirect before expression", 'yq 2>/dev/null ".a.$X" f', True),
    ("stdin only, no expression", "yq -p json -o yaml < in.json > out.yaml", False),
    ("heredoc body is data", "cat > /tmp/x <<'EOF'\nyq \".a.$X\" f\nEOF\nyq '.a' f", False),
    ("comment is not a call", '# yq ".a.$X" f', False),
    ("word mentioning yq in quotes", 'echo "yq $X"', False),
    # PR #2616 review: -f is --front-matter and takes a value.
    ("-f value", 'yq -f process ".a=\\"$X\\"" f', True),
    ("-fprocess attached", 'yq -fprocess ".a=\\"$X\\"" f', True),
    ("-f value, safe expression", "yq -f extract '.a' \"$F\"", False),
    ("--split-exp-file value", 'yq --split-exp-file s.yq ".a.$X" f', True),
    # Code run as a string fails closed.
    ("sh -c with yq and expansion", 'sh -c "yq \\".a.$X\\" f"', True),
    ("bash -c, single-quoted", "bash -c 'yq \".a.$X\" f'", True),
    ("sh -c, yq without $", "sh -c 'yq .a f'", False),
    ("sh -c without yq", 'sh -c "echo $X"', False),
    ("heredoc to sh, unquoted delimiter", 'sh <<EOF\nyq ".a.$X" f\nEOF', True),
    ("heredoc to sh, quoted delimiter", "bash <<'EOF'\nyq \".a.$X\" f\nEOF", True),
    ("heredoc to sh, quoted delimiter, safe", "bash <<'EOF'\nyq '.a' \"$F\"\nEOF", False),
    ("heredoc to kubectl exec sh", 'kubectl exec p -- sh <<EOF\nyq -i ".a=$X" f\nEOF', True),
    ("heredoc to cat stays data", 'cat > /tmp/x <<EOF\nyq ".a.$X" f\nEOF', False),
    ("heredoc piped to sh", 'cat <<EOF | sh\nyq ".a.$X" f\nEOF', True),
    ("heredoc piped to bash, quoted", "cat <<'EOF' | bash\nyq \".a.$X\" f\nEOF", True),
    ("unquoted heredoc to sh, continuation", 'sh <<EOF\nyq -i \\\n  ".a=$X" f\nEOF', True),
    ("unquoted heredoc to sh, escaped $", 'sh <<EOF\nyq ".a=\\$X" f\nEOF', True),
    ("heredoc piped to grep stays data", 'cat <<EOF | grep x\nyq ".a.$X" f\nEOF', False),
)

PARSE_ERROR_CASES = (
    ("unterminated double quote", 'yq ".a = $X f'),
    ("unterminated single quote", "yq '.a f"),
    ("unterminated $(", 'V=$(yq ".a" f'),
    ("unterminated heredoc", "cat <<EOF\nyq x\n"),
)


def selftest() -> int:
    """A checker that has never been seen to fail is not known to work."""
    failed = 0
    for name, source, should_fire in SELFTEST_CASES:
        try:
            found = list(scan_source(source))
        except ShellParseError as exc:
            print(f"❌ selftest [{name}]: unexpected parse error: {exc}", file=sys.stderr)
            failed += 1
            continue
        if bool(found) != should_fire:
            verb = "did not fire" if should_fire else f"fired on a clean call: {found}"
            print(f"❌ selftest [{name}]: detector {verb}", file=sys.stderr)
            failed += 1
    for name, source in PARSE_ERROR_CASES:
        try:
            found = list(scan_source(source))
        except ShellParseError:
            continue
        print(f"❌ selftest [{name}]: split without error, found {found}", file=sys.stderr)
        failed += 1

    # End to end through scan(): template walking and file/template naming.
    doc = """
apiVersion: argoproj.io/v1alpha1
kind: ClusterWorkflowTemplate
metadata: {name: selftest}
spec:
  templates:
    - name: t
      script:
        source: |
          yq eval -i ".ingress.hosts += [\\"${DOMAIN}\\"]" values.yaml
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "bad.yaml").write_text(doc)
        if [k[:2] for k in scan(Path(d))] != [("bad.yaml", "t")]:
            print("❌ selftest: scan() did not report the template", file=sys.stderr)
            failed += 1
    if failed:
        return 1
    print(f"✅ selftest: {len(SELFTEST_CASES)} call shapes and "
          f"{len(PARSE_ERROR_CASES)} unparseable scripts behave as expected")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not TEMPLATES.is_dir():
        print(f"❌ {TEMPLATES} not found — refusing to pass vacuously", file=sys.stderr)
        return 2

    new, stale = [], set(BASELINE)
    try:
        found = list(scan(TEMPLATES))
    except ShellParseError as exc:
        # A script the check could not split has unknown yq calls in it:
        # that is not "no interpolation".
        print(f"❌ could not split a script source ({exc}); its yq calls are unknown",
              file=sys.stderr)
        return 2
    for fname, tname, expr in found:
        key = (fname, tname, expr)
        stale.discard(key)
        if key in BASELINE:
            continue
        new.append(key)

    if new:
        print("❌ Shell variables interpolated into a yq expression:\n", file=sys.stderr)
        for fname, tname, expr in new:
            print(f"   {fname} / {tname}: {expr}", file=sys.stderr)
        print(
            "\n   yq's expression language is not data: a value that closes the\n"
            "   string literal keeps executing against the file. Export the value\n"
            "   and read it with strenv() —\n\n"
            "       export DOMAIN\n"
            "       yq eval -i '.ingress.hosts += [strenv(DOMAIN)]' values.yaml\n\n"
            "   strenv() does not substitute in an expression PATH; write those as\n"
            "   `.env[strenv(KEY)]` and shape-check the key. See gitops#997.\n",
            file=sys.stderr,
        )
        return 1

    if stale:
        print("❌ BASELINE lists sites that no longer exist — remove them:\n", file=sys.stderr)
        for entry in sorted(stale):
            print(f"   {entry}", file=sys.stderr)
        print("\n   A baseline that outlives its sites stops being a ratchet.\n",
              file=sys.stderr)
        return 1

    print(f"✅ No yq expression interpolates a shell variable "
          f"({len(BASELINE)} known site remains, gitops#997)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
