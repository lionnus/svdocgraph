"""Reads the documentation comment above each unit.

slang keeps each comment as trivia of the token that follows it. The elaboration
already parsed each file, thus this module reads the comments from that parse and
not with a regular expression. A `/** */` block, a `//` run, `///` and `//!` all
give a comment, and a comment before an `import` or an `include` still belongs to
the module.

`markup` turns the text into HTML.
"""

from __future__ import annotations

import os
import re
import textwrap

_LICENCE = re.compile(r"(copyright|spdx|licen[cs]e|https?:|www\.)", re.I)


def clean_comment(raw: str) -> str:
    """The text of a comment, without the markers of the comment.

    `textwrap.dedent` removes only the indentation that each line shares. Thus
    the deeper indentation stays, which reStructuredText needs for the body of a
    directive.
    """
    text = raw.strip()
    if text.startswith("/*"):
        # `/*`, `/**` and `/*!` all start a documentation block.
        text = re.sub(r"^/\*[*!]?", "", text)
        if text.endswith("*/"):
            text = text[:-2]
        lines = [re.sub(r"^\s*\*\s?", "", ln) for ln in text.splitlines()]
    else:
        # `//`, `///`, `//!` and `///<` all start a documentation line.
        lines = [re.sub(r"^\s*//+[!<]*\s?", "", ln) for ln in text.splitlines()]
    return textwrap.dedent("\n".join(lines)).strip("\n").rstrip()


def _file_of(sm, loc) -> str | None:
    """The file of a source location, or None if it is not known."""
    if sm is None or loc is None:
        return None
    try:
        return os.path.realpath(sm.getFileName(loc))
    except Exception:
        return None


def _trivia_files(trivia, sm) -> list:
    """The file of each trivia, or None if it is not known.

    An `include` puts the text of another file before the module. slang marks
    the change of the file on the trivia that ends a run, thus the mark applies
    to the trivia before it.
    """
    files: list = [None] * len(trivia)
    current = None
    for i in range(len(trivia) - 1, -1, -1):
        loc = trivia[i].getExplicitLocation()
        if loc is not None:
            current = _file_of(sm, loc)
        files[i] = current
    return files


def _directive_trivia(triv, sm) -> tuple:
    """The trivia inside a preprocessor directive, with the file of each one.

    A comment that comes before an `include` or a `define` belongs to that
    directive, and not to the module. Thus this function opens the directive.
    """
    try:
        token = triv.syntax().getFirstToken()
        items = list(token.trivia)
    except Exception:
        return [], []
    here = _file_of(sm, token.location)
    files = _trivia_files(items, sm) if sm is not None else [None] * len(items)
    return items, [f if f is not None else here for f in files]


def _comment_blocks(trivia, sm=None, own_file: str = "") -> list:
    """The comment blocks before a token, in sequence.

    Line comments that follow each other are one block. An empty line between
    them starts a new block. A comment from an `include` file is not the
    documentation of this module, thus it is not in the result.
    """
    blocks: list = []
    run: list = []          # The line comments that follow each other
    gap = 0                 # The end-of-line trivia after the last comment

    def flush():
        if run:
            blocks.append("\n".join(run))
            run.clear()

    def walk(items, files, depth):
        nonlocal gap
        for triv, from_file in zip(items, files):
            kind = str(triv.kind)
            if "Directive" in kind:
                if depth < 3:
                    walk(*_directive_trivia(triv, sm), depth + 1)
                continue
            if "Comment" in kind and from_file is not None and from_file != own_file:
                flush()
                continue
            if "LineComment" in kind:
                if gap > 1:
                    flush()
                run.append(str(triv.getRawText()))
                gap = 0
            elif "BlockComment" in kind:
                flush()
                blocks.append(str(triv.getRawText()))
                gap = 0
            elif "EndOfLine" in kind:
                gap += 1

    items = list(trivia)
    files = (_trivia_files(items, sm) if sm is not None and own_file
             else [None] * len(items))
    walk(items, files, 0)
    flush()
    return blocks


#: A line that names a person: `Authors:`, or `Name <mail@example.com>`.
_AUTHOR_LINE = re.compile(
    r"^\s*(authors?|maintainers?)\s*:|^\s*\S[^<>]*<[^@<>\s]+@[^<>\s]+>[.,]?\s*$", re.I
)


def _strip_authors(text: str) -> str:
    """Removes the lines that name the authors.

    Many PULP files put the authors above the module. The name of a person is
    not a description of the function.
    """
    kept = [ln for ln in text.splitlines() if not _AUTHOR_LINE.match(ln)]
    return "\n".join(kept).strip("\n").rstrip()


def _is_licence(text: str) -> bool:
    """True if the comment gives the licence, not the function of the module."""
    head = "\n".join(text.splitlines()[:6])
    return bool(_LICENCE.search(head)) and len(_LICENCE.findall(head)) >= 2


def summary(text: str) -> str:
    """The first sentence of a comment, for a list or a card."""
    plain = " ".join(
        ln for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith((".. ", ":", "|", "+--", "==="))
    )
    # Remove the emphasis marks, but not the underscore: it is in each name.
    plain = re.sub(r"[*`]+", "", plain).strip()
    m = re.search(r"^(.{20,200}?[.!?])\s", plain + " ")
    return (m.group(1) if m else plain)[:300].strip()


def doc_comments(trees) -> dict:
    """The documentation comment of each unit, from the parsed files.

    slang attaches a comment to the token that comes after it. A file often has
    a licence comment, then the documentation comment, then an import, then the
    module. Thus this function collects the comments of each member and gives
    the last one to the next module.
    """
    out: dict = {}
    for tree in trees:
        root = tree.root
        sm = getattr(tree, "sourceManager", None)
        # A file gives a compilation unit. A single declaration gives that
        # declaration, and then `members` holds the body of the module.
        members = (root.members if type(root).__name__ == "CompilationUnitSyntax"
                   else [root])
        pending: list = []
        for member in members:
            try:
                first = member.getFirstToken()
            except Exception:
                continue
            own = _file_of(sm, first.location) or ""
            for block in _comment_blocks(first.trivia, sm, own):
                text = clean_comment(block)
                if text and not _is_licence(text):
                    text = _strip_authors(text)
                    if text:
                        pending.append(text)
            header = getattr(member, "header", None)
            name_tok = getattr(header, "name", None) if header is not None else None
            name = getattr(name_tok, "valueText", "") if name_tok is not None else ""
            if name:
                if pending:
                    out.setdefault(name, pending[-1])
                pending = []
    return out
