"""Verify that a file changed only in comments and string literals (e.g. after a translation).

Usage:  python dev/check_text_only.py <old_file> <new_file>
Works for Python (.py) and MAXScript (.ms / .mse). Exit code 0 = code identical, 1 = code differs.
"""
import io, sys, tokenize, difflib


def py_code_tokens(src):
    skip = {tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.ENCODING}
    skip |= {getattr(tokenize, n) for n in ("FSTRING_MIDDLE",) if hasattr(tokenize, n)}
    out = []
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type in skip:
            out.append("<STR>") if t.type in (tokenize.STRING,) else None
            continue
        out.append(t.string if t.type not in (tokenize.INDENT, tokenize.DEDENT) else tokenize.tok_name[t.type])
    return out


def ms_code_tokens(src):
    """Strip MAXScript comments (-- …, /* … */) and strings ("…", @"…"), keep everything else."""
    out, i, n, buf = [], 0, len(src), []
    def flush():
        if buf:
            out.extend("".join(buf).split()); buf.clear()
    while i < n:
        c = src[i]
        if src.startswith("--", i):
            j = src.find("\n", i); i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2
        elif c == '"' or (c == "@" and i + 1 < n and src[i + 1] == '"'):
            verbatim = c == "@"
            i += 2 if verbatim else 1
            while i < n:
                if not verbatim and src[i] == "\\":
                    i += 2; continue
                if src[i] == '"':
                    i += 1; break
                i += 1
            flush(); out.append("<STR>")
        else:
            buf.append(c); i += 1
    flush()
    return out


def py_strings(src):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.STRING]


def ms_strings(src):
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("--", i):
            j = src.find("\n", i); i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2
        elif src[i] == '"' or (src[i] == "@" and i + 1 < n and src[i + 1] == '"'):
            start, verbatim = i, src[i] == "@"
            i += 2 if verbatim else 1
            while i < n:
                if not verbatim and src[i] == "\\":
                    i += 2; continue
                if src[i] == '"':
                    i += 1; break
                i += 1
            out.append(src[start:i])
        else:
            i += 1
    return out


def read(path):
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def key_like_changes(old_path, new_path):
    """Changed string literals whose OLD value has no spaces — may be data keys / identifiers."""
    fn = py_strings if old_path.lower().endswith(".py") else ms_strings
    a, b = fn(read(old_path)), fn(read(new_path))
    if len(a) != len(b):
        return None
    flagged = []
    for x, y in zip(a, b):
        inner = x.strip("@").strip("rbuRBUfF").strip("'\"")
        if x != y and inner and not any(ch.isspace() for ch in inner):
            flagged.append((x, y))
    return flagged


def code_tokens(path):
    raw = open(path, "rb").read()
    try:
        src = raw.decode("utf-8")
    except UnicodeDecodeError:
        src = raw.decode("cp1252")
    return py_code_tokens(src) if path.lower().endswith(".py") else ms_code_tokens(src)


if __name__ == "__main__":
    a, b = code_tokens(sys.argv[1]), code_tokens(sys.argv[2])
    if a == b:
        print(f"OK  code identical ({len(a)} tokens) — only comments/strings changed")
        flagged = key_like_changes(sys.argv[1], sys.argv[2]) or []
        for x, y in flagged:
            print(f"  REVIEW single-word string changed (data key?):  {x}  ->  {y}")
        sys.exit(0)
    print("CODE DIFFERS:")
    for line in list(difflib.unified_diff(a, b, lineterm="", n=3))[:60]:
        print("  ", line)
    sys.exit(1)
