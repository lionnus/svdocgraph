"""The library interface: two functions that do what the commands do.

`cli` gives the same two steps to a person at a terminal. Another program calls
these functions. Each one takes a path, thus the caller needs no other object.
"""

from __future__ import annotations

import os
import tempfile

from . import bender, extract, project
from .model import Design
from .render import render_site


class BenderFailed(Exception):
    """bender could not describe the project. The message comes from bender."""


def _no_log(message: str) -> None:
    pass


def extract_design(project_root: str, tops=None, log=_no_log) -> Design:
    """Reads the project with bender, then elaborates it with slang.

    Gives the design model. Raises `BenderFailed` if bender cannot resolve the
    dependencies, because then there is no source set to read. *log* takes one
    message, for a caller that shows the progress.
    """
    info = bender.collect(project_root)
    if info.failure:
        raise BenderFailed(info.failure)
    if info.root_package:
        log(f"Bender root package: {info.root_package} "
            f"({len(info.root_files)} source files, {len(info.packages)} deps)")
    with tempfile.TemporaryDirectory() as tmp:
        cmd_file = bender.write_command_file(info, os.path.join(tmp, "sources.f")) or ""
        log("Elaboration with slang …")
        return extract.extract_design(
            project_root, info, cmd_file, extra_tops=list(tops or [])
        )


def build_documentation(project_root: str = ".", outdir: str | None = None,
                        tops=None, log=_no_log) -> Design:
    """Makes the documentation of a project. Gives the design that it wrote.

    *outdir* is relative to the project root. The default comes from
    `svdocgraph.yml`, and then from `project.DEFAULT_OUTPUT`.
    """
    root, _ = project.find_project_root(project_root)
    config = project.load_config(root)
    out = outdir or config.output
    out = out if os.path.isabs(out) else os.path.join(root, out)
    design = extract_design(
        root, tops=list(config.tops) + list(tops or []), log=log
    )
    render_site(
        design, out, title=config.name,
        doc_dirs=config.doc_dirs if config.docs_enabled else None,
        with_docs=config.docs_enabled, with_sources=config.sources_enabled,
    )
    return design
