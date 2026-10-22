"""Tiny S-expression reader/writer for KiCad files."""

import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """An unquoted atom (keyword or number), as opposed to a quoted string."""


def parse(text):
    stack, cur = [], []
    for m in _TOKEN.finditer(text):
        lp, rp, s, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done, cur = cur, stack.pop()
            cur.append(done)
        elif s is not None:
            cur.append(re.sub(r"\\(.)", r"\1", s) if "\\" in s else s)
        elif atom is not None:
            cur.append(Sym(atom))
    return cur[0]


def dump(node, indent=0):
    if not isinstance(node, list):
        if isinstance(node, Sym):
            return str(node)
        if isinstance(node, (int, float)):
            return fmt_num(node)
        return '"' + str(node).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    simple = all(not isinstance(x, list) for x in node)
    if simple:
        return "(" + " ".join(dump(x) for x in node) + ")"
    pad = "  " * (indent + 1)
    head = [dump(x) for x in node if not isinstance(x, list)]
    out = "(" + " ".join(head)
    for x in node:
        if isinstance(x, list):
            out += "\n" + pad + dump(x, indent + 1)
    return out + "\n" + "  " * indent + ")"


def fmt_num(v):
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def find(node, key):
    """First child list whose head is `key`."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
