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

## Quick start

SVDocGraph is a standalone tool, the same way `bender`, `morty` or `svase` are: you
install it once and run it inside any Bender project. Nothing is vendored into the
project and there is nothing to configure.

```sh
uv tool install svdocgraph      # or: pipx install svdocgraph
cd my-bender-project
svdocgraph gen --open
```

That elaborates the design, writes the docs to `.svdocgraph/` in the project root,
and opens them in your browser. Later, `svdocgraph open` reopens them without
rebuilding.

To try it without installing anything: `uvx svdocgraph gen --open`.

## Dependencies

Two things must be on your `PATH`; everything else is a Python dependency that
`pip`/`uv` installs for you.

| What | Why | Required | Install |
| --- | --- | --- | --- |
| [`bender`](https://github.com/pulp-platform/bender) | source set, include dirs, defines, package map | yes | `curl https://pulp-platform.github.io/bender/init -sSf \| sh` or `cargo install bender` |
| [Graphviz](https://graphviz.org/) (`dot`) | lays out every diagram | strongly recommended | `apt install graphviz` / `brew install graphviz` |
| `pyslang` >= 11 | the slang elaborator, as a wheel | yes | installed automatically |
| `Jinja2`, `PyYAML` | templating, `Bender.yml` parsing | yes | installed automatically |

No SystemVerilog simulator or license is needed: slang ships as a binary wheel
inside `pyslang`, so there is nothing to compile.

```sh
svdocgraph doctor    # prints what is found, what is missing, and how to install it
```

`gen` refuses to run without `bender` (exit code 3) rather than producing an empty
site, and warns when Graphviz is missing (the site still builds, minus the
diagrams).

The `pyslang` floor is a hard requirement, not a preference: `Driver` moved to
`pyslang.driver` in 11.0, and on older releases the extractor finds nothing and
would silently produce an empty design. Python 3.9 through 3.13 are tested in CI.

## Commands

Run from anywhere inside a Bender project; the project root is the nearest
directory above you containing a `Bender.yml`.

```sh
svdocgraph gen              # generate the docs into ./.svdocgraph
svdocgraph gen --open       # ...and open them
svdocgraph open             # open the last build (generates it if missing)
svdocgraph serve            # generate, then serve at http://localhost:8080
svdocgraph gen -o public    # write somewhere else, e.g. for CI / Pages
svdocgraph init             # optional: write svdocgraph.yml + .gitignore rule
svdocgraph dump -o design.json   # just the extracted model as JSON
```

`build` is kept as an alias for `gen`.

Zero configuration: SVDocGraph asks `bender` for the source set, include
directories, macro defines, and the package each file belongs to, then elaborates
every module declared by the root package. Use `--top NAME` to force extra top
modules if some are only reachable from a testbench target.

### Where the output goes

The docs land in a single tool-owned directory, `.svdocgraph/`, next to `Bender.yml`
— one entry to ignore, no chance of colliding with a hand-written `docs/`. The first
`gen` adds it to the repository's `.gitignore` for you. The site is plain static
files: open `.svdocgraph/index.html` straight from disk (search, graphs and theme
all work offline, no server needed), or point any static host at the directory.

`gen` refuses to write into a non-empty directory it did not generate itself, so
`-o docs` cannot silently eat your handwritten documentation; pass `--force` if you
really mean it.

### Optional config

`svdocgraph init` writes an `svdocgraph.yml` so that a plain `svdocgraph gen` — and
therefore `make docs` — needs no flags:

```yaml
output: .svdocgraph      # where the docs go
tops: [my_testbench_top] # extra tops to elaborate
name: My Design          # title in the site header
```

## How it fits into a project

Think of it the way software projects use MkDocs, Sphinx or `cargo doc`.

1. **As a standalone tool (recommended).** Installed once on your machine or in CI,
   run in any Bender repository.

2. **As a documentation target in your build.** Add a target to the project that
   already drives `bender`:

   ```makefile
   .PHONY: docs docs-open
   docs:
   	svdocgraph gen

   docs-open:
   	svdocgraph gen --open
   ```

   `make docs` is quiet enough for CI with `svdocgraph gen -q`.

3. **As a CI job that publishes to Pages.** For example, GitLab CI:

   ```yaml
   pages:
     image: python:3.12
     script:
       - pip install svdocgraph
       - apt-get update && apt-get install -y graphviz bender
       - svdocgraph gen -o public
     artifacts:
       paths: [public]
   ```

The generated site is just files, so it drops into any static host.

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

## Development

```sh
uv sync --extra dev
uv run pytest          # unit + end-to-end tests, no bender installation needed
uv run ruff check .
```

The tests drive the CLI against a small fixture design in `tests/fixtures/demo`
using a stub `bender`, so they run anywhere.

Two workflows run in CI:

- **`ci`** — lint, the test suite on Python 3.9-3.13, and a packaging job that
  builds the wheel, installs it into a clean environment and drives the installed
  entry point (the templates, CSS, JS and fonts must ship inside it).
- **`integration`** — generates documentation for two real
  [PULP Platform](https://github.com/pulp-platform) designs with a real `bender`:

  | design | why | extracted |
  | --- | --- | --- |
  | [`cv32e40p`](https://github.com/pulp-platform/cv32e40p) @ `vega_v1.3.4` | a processor core: deep hierarchy from core through the pipeline stages to ALU, LSU and register file | 26 units, 0 diagnostics |
  | [`datamover`](https://github.com/pulp-platform/datamover) @ `f14d4db` | an HWPE accelerator: hwpe-stream, HCI and hwpe-ctrl interfaces wiring an engine to a streamer | 20 units, 3 interfaces, 0 diagnostics |

  Each run asserts a floor on what was extracted — module and interface counts,
  named units such as `riscv_core` and `hci_core_intf`, zero diagnostics, graphs
  actually rendered — and uploads the generated site as a build artifact you can
  download and browse. It runs on every push and pull request, plus weekly.

The designs are pinned to a tag or commit, so upstream RTL changes cannot turn a
pull request red; the weekly run is what catches breakage from the things that do
float (a new bender, pyslang, Graphviz or runner image). Bumping a pin is a
deliberate commit. `scripts/check_site.py` holds the assertions and can be pointed
at any generated site by hand.

`cv32e40p` is pinned to `vega_v1.3.4` because that is the newest tag whose
`Bender.yml` still resolves. On `master` — and on the openhwgroup fork, up to and
including `cv32e40p_v1.8.3` — `bender` fails with a `tech_cells_generic`
requirement conflict, and two files listed under `sources` no longer exist in the
tree. Both designs are used exactly as published; nothing is patched.

## License

Apache-2.0. Bundled IBM Plex fonts are licensed under the SIL Open Font License 1.1
(see `svdocgraph/assets/fonts/OFL.txt`).
