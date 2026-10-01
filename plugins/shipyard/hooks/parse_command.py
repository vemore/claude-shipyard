"""Read a Bash command line the way the guard needs it, without being a shell.

Usage: ``parse(command, cwd, conf) -> dict`` (library), or for a quick look:
``python3 "$CLAUDE_PLUGIN_ROOT/hooks/parse_command.py" 'git -C /x commit -m y'`` prints the
verdict as JSON.

Guarantees: finds every ``git commit``, ``git push``, ``git config`` write, staging command
(``git add/rm/mv``) and ``gh pr create|merge`` / ``gh api`` call on the line, with the
repository directory each one runs in, following ``cd``, ``pushd``, ``git -C``, literal
variables, subshells, ``bash -c`` and ``eval``. Quoted text, ``echo`` arguments and heredoc
bodies are data, never commands. Rules that need no repository state become ``blocks``, each
with the directory its command runs in (``cwd``, None when unknown), so the guard can stay inert
in a repository that shipyard has not bootstrapped.

Does not cover: inherited environment variables, ``$(...)`` output, globs, aliases, shell
functions, backquotes, or the inside of a script it launches (``bash scripts/x.sh``). When it
cannot tell which repository a command runs in, it says so (``cwd: null``) instead of guessing.

Why it exists: splitting on ``&&`` and grepping cried wolf on every quoted message and on the
very heredoc that documents a forbidden command (annex 04 section 3).
"""

import json
import os
import re
import shlex
import sys
from typing import Dict, List, Optional, Tuple

MAX_DEPTH = 3

OPERATORS = [";;", "&&", "||", "|&", ">>", "<<<", "<<", ">&", "&>", ">|",
             ";", "&", "|", "(", ")", "<", ">"]
SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}
REDIRECTIONS = {">", ">>", "<", "<<", "<<<", ">&", "&>", ">|"}
PUNCT = set("();<>|&")

HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\2")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
UNKNOWN_VALUE_CHARS = set("$`*?[(")
SHELLS = {"bash", "sh", "zsh", "dash"}
HEAD_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for",
                 "!", "{", "}", "time", "nohup", "command", "exec", "builtin"}
XARGS_UNKNOWN = "$__XARGS_INPUT__"

# git global options that take a separate argument (the --opt=value forms take none).
GIT_GLOBAL_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
                  "--config-env", "--exec-path"}

COMMIT_SHORT_ARG = set("mFCct")      # argument attached or in the next token
COMMIT_SHORT_ATTACHED = set("Su")    # argument attached only
COMMIT_LONG_ARG = {"--message", "--file", "--reuse-message", "--reedit-message", "--template",
                   "--author", "--date", "--fixup", "--squash", "--cleanup", "--trailer",
                   "--pathspec-from-file"}
PUSH_LONG_ARG = {"--repo", "--receive-pack", "--exec", "--push-option"}

GH_CREATE_SHORT_ARG = "tbFHalmprRTB"
GH_CREATE_LONG_ARG = {"title", "body", "body-file", "head", "assignee", "label", "milestone",
                      "project", "reviewer", "repo", "template", "base", "recover"}
GH_MERGE_SHORT_ARG = "bFtAR"
GH_MERGE_LONG_ARG = {"body", "body-file", "subject", "author-email", "match-head-commit", "repo"}
GH_API_SHORT_ARG = "XHfFqtp"
GH_API_LONG_ARG = {"method", "header", "raw-field", "field", "input", "jq", "template",
                   "hostname", "cache", "preview"}
MERGE_API_PATH_RE = re.compile(r"(^|/)pulls/\d+/merge/?$")


# --------------------------------------------------------------------------- lexing

def strip_heredocs(text: str) -> str:
    """Drop heredoc bodies and their terminator lines; keep the opening line."""
    out = []  # type: List[str]
    pending = []  # type: List[Tuple[str, bool]]
    for line in text.split("\n"):
        if pending:
            delimiter, dash = pending[0]
            if (line.lstrip("\t") if dash else line) == delimiter:
                pending.pop(0)
            continue
        out.append(line)
        for match in HEREDOC_RE.finditer(line):
            pending.append((match.group(3), bool(match.group(1))))
    return "\n".join(out)


def strip_comments(text: str) -> str:
    """Remove ``# ...`` comments that start a word outside quotes (as bash does)."""
    out = []
    quote = ""
    i = 0
    prev = "\n"
    while i < len(text):
        ch = text[i]
        if quote == "'":
            if ch == "'":
                quote = ""
        elif quote == '"':
            if ch == "\\" and i + 1 < len(text):
                out.append(ch)
                i += 1
                ch = text[i]
            elif ch == '"':
                quote = ""
        else:
            if ch == "\\" and i + 1 < len(text):
                out.append(ch)
                i += 1
                ch = text[i]
            elif ch in "'\"":
                quote = ch
            elif ch == "#" and (prev.isspace() or prev in PUNCT):
                while i < len(text) and text[i] != "\n":
                    i += 1
                prev = "\n"
                continue
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


def _lex(chunk: str) -> List[str]:
    lexer = shlex.shlex(strip_comments(chunk), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def split_punct(token: str) -> List[str]:
    """Split a run of operator characters (``);``, ``)&&``) into known operators."""
    if not token or any(ch not in PUNCT for ch in token):
        return [token]
    parts = []
    i = 0
    while i < len(token):
        for op in OPERATORS:
            if token.startswith(op, i):
                parts.append(op)
                i += len(op)
                break
        else:  # pragma: no cover - every PUNCT character is an operator
            parts.append(token[i])
            i += 1
    return parts


def tokenize(text: str) -> Optional[List[str]]:
    """Tokens with ``;`` at each line end; None when a quote never closes."""
    text = re.sub(r"\\\n", "", strip_heredocs(text))
    lines = text.split("\n")
    tokens = []  # type: List[str]
    i = 0
    while i < len(lines):
        chunk = lines[i]
        j = i
        while True:
            try:
                raw = _lex(chunk)
                break
            except ValueError:
                j += 1
                if j >= len(lines):
                    return None
                chunk += "\n" + lines[j]
        for token in raw:
            tokens.extend(split_punct(token))
        tokens.append(";")
        i = j + 1
    return tokens


# --------------------------------------------------------------------------- state

class State:
    def __init__(self, cwd: Optional[str], variables: Optional[Dict[str, Optional[str]]] = None):
        self.cwd = cwd
        self.vars = dict(variables or {})  # type: Dict[str, Optional[str]]
        self.stack = []  # type: List[Tuple[Optional[str], Dict[str, Optional[str]]]]

    def push(self) -> None:
        self.stack.append((self.cwd, dict(self.vars)))

    def pop(self) -> None:
        if self.stack:
            self.cwd, self.vars = self.stack.pop()


def substitute(value: str, variables: Dict[str, Optional[str]]) -> Optional[str]:
    """Replace ``$NAME`` / ``${NAME}`` bound to literals; None if anything stays unknown."""
    def repl(match):
        name = match.group(1) or match.group(2)
        bound = variables.get(name)
        if bound is None:
            raise KeyError(name)
        return bound
    try:
        result = VAR_RE.sub(repl, value)
    except KeyError:
        return None
    if "$" in result or "`" in result:
        return None
    return result


def resolve_dir(arg: Optional[str], base: Optional[str],
                variables: Dict[str, Optional[str]]) -> Optional[str]:
    """Where ``cd arg`` lands, starting from ``base``; None when it cannot be known."""
    if arg is None:
        return os.path.expanduser("~")
    if arg == "-":
        return None
    value = substitute(arg, variables)
    if value is None or any(ch in value for ch in "*?["):
        return None
    if value == "~" or value.startswith("~/"):
        value = os.path.expanduser(value)
    if os.path.isabs(value):
        return os.path.normpath(value)
    if base is None:
        return None
    return os.path.normpath(os.path.join(base, value))


# --------------------------------------------------------------------------- parser

class Parser:
    def __init__(self, conf: Dict[str, str]):
        self.conf = conf
        self.default = conf.get("DEFAULT_BRANCH") or "main"
        ns = (conf.get("GIT_CONFIG_NS") or "project").lower()
        self.user_only_keys = {ns + ".allowstackedpr", ns + ".deliveryacknowledged"}
        self.ns = conf.get("GIT_CONFIG_NS") or "project"
        self.result = {"parse_ok": True, "blocks": [], "commits": [], "pushes": [],
                       "config_writes": [], "stages": []}  # type: Dict
        self.seq = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    # -- blocks ---------------------------------------------------------------------------
    def block(self, rule: str, message: str, cwd: Optional[str]) -> None:
        """Record a refusal; ``cwd`` is where its command runs (None: cannot be told)."""
        entry = {"rule": rule, "message": message, "cwd": cwd}
        if entry not in self.result["blocks"]:
            self.result["blocks"].append(entry)

    # -- driver ---------------------------------------------------------------------------
    def run(self, text: str, state: State, depth: int = 0) -> None:
        tokens = tokenize(text)
        if tokens is None:
            raise ValueError("unbalanced quotes")
        segment = []  # type: List[str]
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in REDIRECTIONS:
                if segment and segment[-1].isdigit():
                    segment.pop()
                nxt = tokens[i + 1] if i + 1 < len(tokens) else None
                i += 2 if nxt is not None and nxt not in SEPARATORS else 1
                continue
            if token in SEPARATORS:
                self.segment(segment, state, depth)
                segment = []
                if token == "(":
                    state.push()
                elif token == ")":
                    state.pop()
                i += 1
                continue
            segment.append(token)
            i += 1
        self.segment(segment, state, depth)

    def segment(self, tokens: List[str], state: State, depth: int) -> None:
        if not tokens:
            return
        # A segment made only of NAME=value (optionally after `export`) binds variables.
        body = tokens[1:] if tokens[0] in ("export", "local", "declare", "readonly") else tokens
        if body and all(ASSIGN_RE.match(t) for t in body):
            for assignment in body:
                name, _, value = assignment.partition("=")
                if value.startswith("~"):
                    value = os.path.expanduser(value)
                state.vars[name] = None if any(c in value for c in UNKNOWN_VALUE_CHARS) else value
            return
        tokens, xargs_repl = self.normalize_head(tokens)
        if not tokens:
            return
        if xargs_repl is not None:
            tokens = [tokens[0]] + [t.replace(xargs_repl, XARGS_UNKNOWN) if xargs_repl else t
                                    for t in tokens[1:]]
        head = os.path.basename(tokens[0])
        args = tokens[1:]
        if head in ("cd", "pushd"):
            positional = [a for a in args if not (a.startswith("-") and a != "-")]
            state.cwd = resolve_dir(positional[0] if positional else None, state.cwd, state.vars)
        elif head == "popd":
            state.cwd = None
        elif head in SHELLS:
            script = self.shell_script(args)
            if script is not None and depth < MAX_DEPTH:
                self.nested(script, State(state.cwd, state.vars), depth + 1)
        elif head == "eval":
            if args and depth < MAX_DEPTH:
                self.nested(" ".join(args), state, depth + 1)
        elif head == "git":
            self.git(args, state, xargs=xargs_repl is not None)
        elif head == "gh":
            self.gh(args, state)

    def nested(self, text: str, state: State, depth: int) -> None:
        """Parse a ``bash -c`` / ``eval`` script; an unreadable one falls back like a line."""
        try:
            self.run(text, state, depth)
        except ValueError:
            self.result["commits"].extend(fallback_commits(text, state.cwd))

    @staticmethod
    def normalize_head(tokens: List[str]) -> Tuple[List[str], Optional[str]]:
        """Strip prefix assignments, keywords and launchers; (tokens, xargs replace-str)."""
        tokens = list(tokens)
        xargs_repl = None  # type: Optional[str]
        changed = True
        while tokens and changed:
            changed = False
            while tokens and ASSIGN_RE.match(tokens[0]):
                tokens.pop(0)
                changed = True
            if not tokens:
                break
            head = os.path.basename(tokens[0])
            if head in HEAD_KEYWORDS:
                tokens.pop(0)
                if head == "time" and tokens and tokens[0] == "-p":
                    tokens.pop(0)
                changed = True
            elif head == "env":
                tokens.pop(0)
                while tokens:
                    t = tokens[0]
                    if ASSIGN_RE.match(t) or t in ("-i", "-", "--ignore-environment", "-0",
                                                   "--null", "-v", "--debug"):
                        tokens.pop(0)
                    elif t in ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"):
                        del tokens[:2]
                    elif t.startswith("--") and "=" in t:
                        tokens.pop(0)
                    else:
                        break
                changed = True
            elif head == "sudo":
                tokens.pop(0)
                while tokens and tokens[0].startswith("-"):
                    t = tokens.pop(0)
                    if t == "--":
                        break
                    if t in ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U", "-R"):
                        if tokens:
                            tokens.pop(0)
                changed = True
            elif head == "timeout":
                tokens.pop(0)
                while tokens and tokens[0].startswith("-"):
                    t = tokens.pop(0)
                    if t in ("-s", "-k", "--signal", "--kill-after") and tokens:
                        tokens.pop(0)
                if tokens:
                    tokens.pop(0)  # the duration
                changed = True
            elif head == "nice":
                tokens.pop(0)
                while tokens and tokens[0].startswith("-"):
                    t = tokens.pop(0)
                    if t in ("-n", "--adjustment") and tokens:
                        tokens.pop(0)
                changed = True
            elif head == "xargs":
                tokens.pop(0)
                xargs_repl = xargs_repl or ""
                while tokens and tokens[0].startswith("-"):
                    t = tokens.pop(0)
                    if t == "--":
                        break
                    if t in ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"):
                        value = tokens.pop(0) if tokens else ""
                        if t == "-I":
                            xargs_repl = value
                    elif t.startswith("-I") and len(t) > 2:
                        xargs_repl = t[2:]
                    elif t.startswith("--replace="):
                        xargs_repl = t.split("=", 1)[1]
                    elif t in ("-i", "--replace"):
                        xargs_repl = "{}"
                changed = True
        return tokens, xargs_repl

    @staticmethod
    def shell_script(args: List[str]) -> Optional[str]:
        """The script of ``bash -c SCRIPT`` (options may come first); None otherwise."""
        has_c = False
        i = 0
        while i < len(args):
            t = args[i]
            if t in ("-o", "+o", "-O", "+O"):
                i += 2
                continue
            if t.startswith("--"):
                i += 1
                continue
            if len(t) > 1 and t[0] in "-+" and t[1:].isalpha():
                if t[0] == "-" and "c" in t[1:]:
                    has_c = True
                i += 1
                continue
            return t if has_c else None
        return None

    # -- git ------------------------------------------------------------------------------
    def git(self, args: List[str], state: State, xargs: bool = False) -> None:
        gcwd = state.cwd
        unknown = False
        i = 0
        while i < len(args):
            t = args[i]
            if t in GIT_GLOBAL_ARG:
                value = args[i + 1] if i + 1 < len(args) else None
                if t == "-C" and value is not None:
                    gcwd = resolve_dir(value, gcwd, state.vars) if value else gcwd
                if t in ("--git-dir", "--work-tree"):
                    unknown = True
                i += 2
                continue
            if t.startswith("--git-dir=") or t.startswith("--work-tree="):
                unknown = True
            if t.startswith("-"):
                i += 1
                continue
            break
        if i >= len(args):
            return
        sub, rest = args[i], args[i + 1:]
        cwd = None if unknown else gcwd
        if sub == "commit":
            self.commit(rest, cwd, xargs)
        elif sub == "push":
            self.push(rest, cwd, xargs)
        elif sub == "config":
            self.config(rest, cwd, state)
        elif sub in ("add", "stage", "rm", "mv"):
            self.stage(sub, rest, cwd)

    def commit(self, rest: List[str], cwd: Optional[str], xargs: bool) -> None:
        all_files = xargs
        amend = False
        pathspecs = []  # type: List[str]
        i = 0
        while i < len(rest):
            t = rest[i]
            if t == "--":
                pathspecs.extend(rest[i + 1:])
                break
            if t in ("--dry-run", "-h", "--help"):
                return
            if t.startswith("--"):
                name, eq, _ = t.partition("=")
                if name == "--all":
                    all_files = True
                elif name == "--amend":
                    amend = True
                elif name == "--pathspec-from-file":
                    all_files = True
                if name in COMMIT_LONG_ARG and not eq:
                    i += 1
                i += 1
                continue
            if t.startswith("-") and len(t) > 1:
                for j in range(1, len(t)):
                    c = t[j]
                    if c == "a":
                        all_files = True
                    if c in COMMIT_SHORT_ARG:
                        if j + 1 == len(t):
                            i += 1
                        break
                    if c in COMMIT_SHORT_ATTACHED:
                        break
                i += 1
                continue
            pathspecs.append(t)
            i += 1
        self.result["commits"].append({"all": all_files, "amend": amend,
                                       "pathspecs": pathspecs, "cwd": cwd,
                                       "seq": self.next_seq()})

    def push(self, rest: List[str], cwd: Optional[str], xargs: bool) -> None:
        force = dry = help_ = all_refs = delete = tags = False
        positional = []  # type: List[str]
        i = 0
        while i < len(rest):
            t = rest[i]
            if t == "--":
                positional.extend(rest[i + 1:])
                break
            if t.startswith("--"):
                name, eq, _ = t.partition("=")
                if name in ("--force", "--force-with-lease", "--force-if-includes", "--mirror"):
                    force = True
                elif name == "--dry-run":
                    dry = True
                elif name == "--help":
                    help_ = True
                elif name in ("--all", "--branches"):
                    all_refs = True
                elif name == "--delete":
                    delete = True
                elif name == "--tags":
                    tags = True
                elif name in PUSH_LONG_ARG and not eq:
                    i += 1
                i += 1
                continue
            if t.startswith("-") and len(t) > 1:
                for j in range(1, len(t)):
                    c = t[j]
                    if c == "f":
                        force = True
                    elif c == "n":
                        dry = True
                    elif c == "h":
                        help_ = True
                    elif c == "d":
                        delete = True
                    elif c == "o":
                        if j + 1 == len(t):
                            i += 1
                        break
                i += 1
                continue
            positional.append(t)
            i += 1
        if dry or help_:
            return
        refspecs = positional[1:]
        if any(r.startswith("+") for r in refspecs):
            force = True
        if force:
            self.block("force-push",
                       "Rewriting a pushed branch destroys commits that another "
                       "session (agent or orchestrator) may have built on, and the review "
                       "history. Remedy: push without force; to bring a branch up to date, "
                       "merge {d} into it (`gh api -X PUT repos/{{owner}}/{{repo}}/pulls/<n>/"
                       "update-branch`) instead of rebasing.".format(d=self.default), cwd)
        to_default = all_refs
        for refspec in refspecs:
            spec = refspec.lstrip("+")
            dest = spec if delete or ":" not in spec else spec.split(":", 1)[1]
            if dest.startswith("refs/heads/"):
                dest = dest[len("refs/heads/"):]
            if dest == self.default:
                to_default = True
        if to_default:
            self.block_push_main(cwd)
        head_ref = any(":" not in r and r.lstrip("+") in ("HEAD", "@") for r in refspecs)
        bare = not refspecs and not tags and not all_refs
        self.result["pushes"].append({"refspecs": refspecs, "bare": bare, "head_ref": head_ref,
                                      "cwd": cwd})

    def block_push_main(self, cwd: Optional[str]) -> None:
        self.block("push-main", push_main_message(self.default), cwd)

    def config(self, rest: List[str], cwd: Optional[str], state: State) -> None:
        reads = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color",
                 "--get-colorbool", "--list", "-l", "--edit", "-e"}
        unsets = {"--unset", "--unset-all", "--remove-section", "--rename-section"}
        with_arg = {"--file", "-f", "--blob", "--type", "--default", "--comment", "--value"}
        is_read = is_unset = write_flag = False
        positional = []  # type: List[str]
        i = 0
        while i < len(rest):
            t = rest[i]
            name = t.split("=", 1)[0]
            if t in reads:
                is_read = True
            elif t in unsets:
                is_unset = True
            elif t in ("--add", "--replace-all", "--append"):
                write_flag = True
            elif name in with_arg and "=" not in t:
                i += 1
            elif t.startswith("-"):
                pass
            else:
                positional.append(t)
            i += 1
        sub = None
        if positional and "." not in positional[0]:
            sub = positional.pop(0)
        if is_read or is_unset or not positional:
            return
        if sub is not None and sub != "set":
            return
        if sub == "set" or len(positional) >= 2 or write_flag:
            key = positional[0].lower()
            value = positional[1] if len(positional) > 1 else "<value>"
            self.result["config_writes"].append({"key": key, "cwd": cwd})
            if key in self.user_only_keys:
                where = "git -C {} ".format(cwd) if cwd else "git "
                self.block("user-only-config",
                           "{key} switches off a guard or silences a lost-work "
                           "warning; that is the user's decision, taken in their own terminal. "
                           "Remedy: ask the user to run it themselves: `{where}config {flag}{key} "
                           "{value}`.".format(key=positional[0], where=where,
                                              flag="--add " if write_flag else "", value=value),
                           cwd)

    def stage(self, sub: str, rest: List[str], cwd: Optional[str]) -> None:
        """Record git add/rm/mv so the commit later on the same line sees their paths."""
        flags = set()
        pathspecs = []  # type: List[str]
        i = 0
        while i < len(rest):
            t = rest[i]
            if t == "--":
                pathspecs.extend(rest[i + 1:])
                break
            if t.startswith("--"):
                name = t.split("=", 1)[0]
                flags.add(name)
                if name == "--pathspec-from-file":
                    flags.add("--all")
                if name in ("--chmod", "--pathspec-from-file") and "=" not in t:
                    i += 1
            elif t.startswith("-") and len(t) > 1:
                for c in t[1:]:
                    flags.add("-" + c)
            else:
                pathspecs.append(t)
            i += 1
        if "-n" in flags or "--dry-run" in flags or "-h" in flags or "--help" in flags:
            return
        entry = {"op": "add" if sub == "stage" else sub, "cwd": cwd, "pathspecs": pathspecs,
                 "all": bool(flags & {"-A", "--all", "--no-ignore-removal"}),
                 "update": bool(flags & {"-u", "--update"}),
                 "force": bool(flags & {"-f", "--force"}), "seq": self.next_seq()}
        self.result["stages"].append(entry)

    # -- gh -------------------------------------------------------------------------------
    def gh(self, args: List[str], state: State) -> None:
        if len(args) >= 2 and args[0] == "pr" and args[1] in ("create", "new"):
            opts, _ = pflag_scan(args[2:], GH_CREATE_SHORT_ARG, GH_CREATE_LONG_ARG)
            if any(name in ("h", "help") for name, _ in opts):
                return
            base = None
            for name, value in opts:
                if name in ("B", "base"):
                    base = value
            if base:
                short = base[len("refs/heads/"):] if base.startswith("refs/heads/") else base
                if short != self.default:
                    self.block("stacked-pr",
                               "A pull request based on {b} instead of {d} can be "
                               "merged into a parent that was already squashed, and its work then"
                               " reaches nowhere while both read as merged and green. Remedy: "
                               "`gh pr create --base {d}` — wait for the other branch to merge, "
                               "or put both changes in one pull request. Only the user can allow "
                               "stacking (`git config {ns}.allowStackedPr true`, in their own "
                               "terminal).".format(b=short, d=self.default, ns=self.ns),
                               cwd=state.cwd)
        elif len(args) >= 2 and args[0] == "pr" and args[1] == "merge":
            opts, _ = pflag_scan(args[2:], GH_MERGE_SHORT_ARG, GH_MERGE_LONG_ARG)
            names = {name for name, _ in opts}
            if names & {"h", "help"}:
                return
            if "admin" in names:
                self.block("merge-admin",
                           "`--admin` bypasses the required checks. Remedy: wait "
                           "for the checks to pass, then `gh pr merge <n> --squash "
                           "--match-head-commit <sha>`.", state.cwd)
            strategy = names & {"s", "squash", "m", "merge", "r", "rebase"}
            if "disable-auto" in names and not strategy:
                return
            if not (names & {"s", "squash"}) or names & {"m", "merge", "r", "rebase"}:
                self.block("merge-squash",
                           "Pull requests are squash-merged only — one commit per "
                           "change on {d}, revertible at once, and what a deploy keys on. "
                           "Remedy: `gh pr merge <n> --squash --match-head-commit <sha>`."
                           .format(d=self.default), state.cwd)
        elif args and args[0] == "api":
            opts, positional = pflag_scan(args[1:], GH_API_SHORT_ARG, GH_API_LONG_ARG)
            method = ""
            for name, value in opts:
                if name in ("X", "method"):
                    method = value or ""
            path = positional[0].split("?", 1)[0] if positional else ""
            if method.upper() == "PUT" and MERGE_API_PATH_RE.search(path):
                self.block("merge-api",
                           "Merging through `gh api .../pulls/<n>/merge` bypasses the "
                           "squash-only and required-checks rules. Remedy: `gh pr merge <n> "
                           "--squash --match-head-commit <sha>`.", state.cwd)


def push_main_message(default: str) -> str:
    return ("{d} only moves through a squash-merged pull request with green checks."
            " Remedy: push your work branch (`git push -u origin <type>/<topic>`) and open a "
            "pull request with `gh pr create --base {d}`.".format(d=default))


def pflag_scan(tokens: List[str], short_arg: str,
               long_arg: set) -> Tuple[List[Tuple[str, Optional[str]]], List[str]]:
    """Scan Go-style (pflag) options: grouped short flags, -Xvalue, -X=value, --long=value."""
    opts = []  # type: List[Tuple[str, Optional[str]]]
    positional = []  # type: List[str]
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            positional.extend(tokens[i + 1:])
            break
        if t.startswith("--"):
            name, eq, value = t[2:].partition("=")
            if eq:
                opts.append((name, value))
            elif name in long_arg:
                opts.append((name, tokens[i + 1] if i + 1 < len(tokens) else ""))
                i += 1
            else:
                opts.append((name, None))
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            j = 1
            while j < len(t):
                c = t[j]
                if c in short_arg:
                    rest = t[j + 1:]
                    if rest.startswith("="):
                        rest = rest[1:]
                    if not rest and j + 1 == len(t):
                        rest = tokens[i + 1] if i + 1 < len(tokens) else ""
                        i += 1
                    opts.append((c, rest))
                    break
                opts.append((c, None))
                j += 1
            i += 1
            continue
        positional.append(t)
        i += 1
    return opts, positional


# --------------------------------------------------------------------------- entry points

GIT_COMMIT_RE = re.compile(r"\bgit\b.*\bcommit\b", re.S)
CD_RE = re.compile(r"\bcd\b|git\s+-C", re.S)


def parse(command: str, cwd: Optional[str], conf: Dict[str, str]) -> Dict:
    """Verdict for one command line (see the module docstring and annex 04 section 3)."""
    parser = Parser(conf)
    try:
        parser.run(command, State(os.path.normpath(cwd) if cwd else None))
        return parser.result
    except ValueError:
        pass
    # Unreadable line: refuse nothing, but assume the worst about a commit it may contain.
    return {"parse_ok": False, "blocks": [], "commits": fallback_commits(command, cwd),
            "pushes": [], "config_writes": [], "stages": []}


def fallback_commits(text: str, cwd: Optional[str]) -> List[Dict]:
    """Annex 04 section 3.4: a commit is assumed (all + amend); with cd or git -C, no repo."""
    if not GIT_COMMIT_RE.search(text):
        return []
    return [{"all": True, "amend": True, "pathspecs": [],
             "cwd": None if CD_RE.search(text) else cwd}]


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    conf = {"DEFAULT_BRANCH": "main", "GIT_CONFIG_NS": "project"}
    print(json.dumps(parse(" ".join(argv), os.getcwd(), conf), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
