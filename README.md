# SVDocGraph

A Bender-aware SystemVerilog design map and documentation generator.

SVDocGraph reads a [Bender](https://github.com/pulp-platform/bender) project and
generates a static website: a clickable hierarchy, per-module port and parameter
tables with resolved widths, and an internal block diagram for every module that
shows the submodules inside it and the signals connecting them.

It uses [slang](https://github.com/MikePopoloski/slang) (through `pyslang`) to
elaborate the RTL, so macros are expanded, parameters are resolved, port widths are
computed, and the instance hierarchy is taken from the elaborated design rather than
inferred from text.

## Features

- **Internal connectivity diagrams.** Per module, the submodules instantiated inside
  it and the named signals (including SV interface streams and buses) that wire them
  together, laid out automatically inside the module boundary.
- **Module pages.** Ports grouped by direction with resolved types and bit widths,
  interface ports with modports, resolved parameter values, the submodule list,
  declared interface instances, clocks and resets, and where the module is used.
- **Design hierarchy graph.** The instantiation tree; click a node to open it.
- **Package dependency graph.** From `Bender.yml` and `Bender.lock`, with versions,
  locked revisions and sources for provenance.
- **Search.** A command palette (`/` or Ctrl/Cmd-K) over modules, ports and packages.
- **Self-contained output.** Static HTML, CSS, JS and inline SVG. No server and no
  network needed to view it; host the folder on GitLab or GitHub Pages as-is.

## Install

SVDocGraph is a standalone tool, the same way `bender`, `morty` or `svase` are: you
install it once and run it inside any Bender project.

```sh
# with uv (recommended)
uv tool install svdocgraph

# or with pipx
pipx install svdocgraph

# or from source
git clone <this-repo> && cd svdocgraph && uv tool install .
```

It needs [Graphviz](https://graphviz.org/) (`dot`) on the `PATH` to render graphs.
Everything else (the slang compiler) ships with the `pyslang` dependency.

## Use

Run it from the root of a Bender project (where `Bender.yml` lives):

```sh
svdocgraph build            # generate ./svdocgraph_site
svdocgraph build --open     # ...and open it in a browser
svdocgraph serve            # build, then serve at http://localhost:8080
svdocgraph dump -o design.json   # just the extracted model as JSON
```

Zero configuration: SVDocGraph asks `bender` for the source set, include
directories, macro defines, and the package each file belongs to, then elaborates
every module declared by the root package. Use `--top NAME` to force extra top
modules if some are only reachable from a testbench target.

## How it fits into a project

Think of it the way software projects use MkDocs, Sphinx or `cargo doc`.

1. **As a standalone tool (recommended).** Installed once on your machine or in CI,
   run in any Bender repository. Nothing is vendored into the project.

2. **As a documentation target in your build.** Add a target to the project that
   already drives `bender`:

   ```makefile
   .PHONY: docs
   docs:
   	svdocgraph build -o docs/design
   ```

3. **As a CI job that publishes to Pages.** For example, GitLab CI:

   ```yaml
   pages:
     image: python:3.12
     script:
       - pip install svdocgraph
       - apt-get update && apt-get install -y graphviz bender
       - svdocgraph build -o public
     artifacts:
       paths: [public]
   ```

The generated site is just files, so it drops into any static host. Add the output
directory (`svdocgraph_site/`, `public/`, ...) to `.gitignore`.

## How it works

```
Bender.yml / Bender.lock
        |  bender script flist-plus   (sources + incdirs + defines)
        |  bender sources -f          (file  ->  owning package)
        v
   slang / pyslang   elaborate every module of the root package
        v
   design model      modules, ports, params, instances, connections, provenance
        v
   Graphviz + Jinja  internal netlists, hierarchy, package graph -> static site
```

## License

Apache-2.0. Bundled IBM Plex fonts are licensed under the SIL Open Font License 1.1
(see `svdocgraph/assets/fonts/OFL.txt`).
