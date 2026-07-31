# SVDocGraph

[![ci](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml)
[![integration](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml)
[![codecov](https://codecov.io/gh/lionnus/svdocgraph/graph/badge.svg)](https://codecov.io/gh/lionnus/svdocgraph)
[![python](https://img.shields.io/badge/python-3.9%20%E2%80%93%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Documentation for SystemVerilog projects that use
[Bender](https://github.com/pulp-platform/bender).** Run one command in your
repository. The tool writes a web site that joins the text a person wrote with
the facts that the RTL gives.

**[Open the example site](https://lionnus.github.io/svdocgraph/)** — the
documentation of the
[datamover](https://github.com/pulp-platform/datamover) accelerator.

## What you get

- **A block diagram for each module**, with the child instances and the signals
  between them. Interfaces are included.
- **A page for each module**: the ports with their resolved type and width, the
  parameter values, the clocks, the resets, and the parent modules.
- **The comment above the module**, as text on its page. A name in that comment
  becomes a link to the module.
- **The Markdown and the reStructuredText of the repository**, in the same site.
  A page with the name of a module attaches to that module.
- **The code of each file of the repository**, with the colours and a line
  number. The page of a module opens the code at its line.
- **Graphs of the hierarchy, the source files and the Bender packages.**
- **One search** over the modules, the ports, the packages and the text.

Nothing is guessed from the source text.
[slang](https://github.com/MikePopoloski/slang) elaborates the design, thus the
macros are expanded, the parameters are resolved and the widths are calculated.

## Start

`bender` and [Graphviz](https://graphviz.org/) must be on the `PATH`. A simulator
is not necessary.

```sh
uv tool install svdocgraph      # or: pipx install svdocgraph
cd my-bender-project
svdocgraph gen --open
```

The tool writes the documentation to `.svdocgraph/` and opens it in the browser.
It adds that directory to your `.gitignore`. Later, `svdocgraph open` opens the
documentation again.

| Command | Function |
| --- | --- |
| `svdocgraph gen` | Makes the documentation in `.svdocgraph/` |
| `svdocgraph open` | Opens it. Makes it first if it is not available |
| `svdocgraph serve` | Makes it, then serves it on `http://localhost:8080` |
| `svdocgraph gen -o public` | Writes it to another directory, for a web host |
| `svdocgraph doctor` | Shows the status of the necessary programs |
| `svdocgraph init` | Writes an optional `svdocgraph.yml` |

For `make`, add a rule that calls `svdocgraph gen -q`.

Settings are not necessary. `svdocgraph.yml` can give the output directory, more
top modules, the title, and more directories with documentation:

```yaml
output: .svdocgraph
tops: [my_testbench_top]
name: My Design
docs: [manual]             # `false` reads no written documentation
sources: false             # Makes no page for the code
```

The tool shows the code of the root package only. The code of a dependency has
another licence, thus it stays in its own repository.

If a run fails, `svdocgraph doctor` shows which program is missing. `gen` stops
with exit code 3 when `bender` is not available, and with 4 when `bender` cannot
resolve the dependencies. It then shows the message from `bender`.

## Contribute

```sh
git clone https://github.com/lionnus/svdocgraph && cd svdocgraph
uv sync --extra dev
uv run pytest          # A substitute for bender, thus the tests run anywhere
uv run ruff check .
```

Then open a pull request. CI runs `ruff`, the tests on Python 3.9 to 3.13, and
the coverage measurement. It then makes the documentation of two real designs,
[`opope`](https://github.com/pulp-platform/opope) and
[`datamover`](https://github.com/pulp-platform/datamover), with the true
`bender`, and examines the result. New code needs tests: `pyproject.toml` gives
the minimum coverage, and CI stops below it.

[`IMPROVEMENTS.md`](IMPROVEMENTS.md) gives the design of the tool, the known
limitations, and the ideas for later work.

## License

Apache-2.0. See [LICENSE](LICENSE).

The IBM Plex fonts in `svdocgraph/assets/fonts` have the SIL Open Font License
1.1. See `svdocgraph/assets/fonts/OFL.txt`.
