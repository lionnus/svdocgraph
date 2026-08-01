# SVDocGraph

[![ci](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml)
[![integration](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml)
[![codecov](https://codecov.io/gh/lionnus/svdocgraph/graph/badge.svg)](https://codecov.io/gh/lionnus/svdocgraph)
[![python](https://img.shields.io/badge/python-3.9%20%E2%80%93%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Documentation for SystemVerilog projects that use
[Bender](https://github.com/pulp-platform/bender).** One command makes a web site
that joins the text a person wrote with the facts that the RTL gives.

**[Open the example site](https://lionnus.github.io/svdocgraph/)** — the
documentation of the
[datamover](https://github.com/pulp-platform/datamover) accelerator.

## What you get

- **A block diagram of each module**, with the child instances, the interfaces
  and the signals between them.
- **A page for each module**: the ports with the resolved type and width, the
  parameter values, the clocks, the resets and the parent modules.
- **The comment above the module.** Markdown, reStructuredText and the Doxygen
  commands each render. A name in the comment becomes a link to that module.
- **The Markdown and the reStructuredText of the repository**, in the same site.
  A page with the name of a module attaches to that module.
- **The code of each file**, with the colours and a line number.
- **Graphs of the hierarchy, the source files and the Bender packages**, and one
  search over all of them.

[slang](https://github.com/MikePopoloski/slang) elaborates the design: the macros
expand, the parameters resolve and the widths are calculated. Nothing is guessed
from the source text.

## 1. Read a repository that you do not know

Copy this into a terminal. Remove the lines for the tools that you have.

```sh
# The tools. Graphviz is the only line that changes with the operating system.
curl -LsSf https://astral.sh/uv/install.sh | sh              # uv
curl https://pulp-platform.github.io/bender/init -sSf | sh   # bender
sudo apt install -y graphviz                                 # macOS: brew install graphviz

uv tool install svdocgraph          # or: pipx install svdocgraph

# The design. Use the path of any repository that has a Bender.yml.
cd ~/my-bender-project
bender checkout                     # only if the dependencies are not there yet
svdocgraph gen --open
```

The tool finds the nearest `Bender.yml`, elaborates each module of the root
package, writes `.svdocgraph/` and opens it in the browser. It adds that
directory to your `.gitignore`. A simulator is not necessary.

`uv tool upgrade svdocgraph` gets a later version. To read or change the code,
clone this repository and install that directory:
`uv tool install --force ~/svdocgraph`.

In the site: **Overview** gives the tops, **Hierarchy** gives the structure,
**Files** gives the compile order and the code, and a module page gives the ports
and the block diagram. Push `/` to search.

| Command | Function |
| --- | --- |
| `svdocgraph gen` | Makes the documentation in `.svdocgraph/` |
| `svdocgraph open` | Opens it. Makes it first if it is not available |
| `svdocgraph serve` | Makes it, then serves it on `http://localhost:8080` |
| `svdocgraph doctor` | Shows the status of the necessary programs |
| `svdocgraph init` | Writes an optional `svdocgraph.yml` |

If a run fails, `svdocgraph doctor` shows which program is missing. `gen` stops
with exit code 3 when `bender` is not available, and with 4 when `bender` cannot
resolve the dependencies. It then shows the message from `bender`.

## 2. Publish the documentation of your repository

Write the site to a directory that your host serves:

```make
.PHONY: docs
docs:
	svdocgraph gen -o public
	svdocgraph check public --min-modules 20 --require-graphs
```

`check` gives exit code 1 if the result is not complete. Use it in your pipeline,
because a design that no longer elaborates gives an empty site and no error.
`--want-module`, `--min-interfaces` and `--max-diagnostics` make the condition
stronger. `svdocgraph check --help` gives each option.

In Python, the same two steps are `svdocgraph.build_documentation(root, out)`
and `svdocgraph.check_site(out)`.

Then let your CI job run `make docs` and publish `public/`. Each CI system
publishes in a different way, thus this repository gives no configuration. The
[`pages` workflow](.github/workflows/pages.yml) of this repository is one example
for GitHub Pages.

Settings are not necessary. `svdocgraph.yml` in the project root can give:

```yaml
output: .svdocgraph
name: My Design           # The title. The default is the directory name
tops: [my_testbench_top]  # More top modules
docs: [manual]            # More directories with text. `false` reads none
sources: false            # Makes no page for the code
```

The tool shows the code of the root package only. The code of a dependency has
another licence, thus it stays in its own repository.

## Contribute

```sh
git clone https://github.com/lionnus/svdocgraph && cd svdocgraph
uv sync --extra dev
uv run pytest          # A substitute for bender, thus the tests run anywhere
uv run ruff check .
```

Each module has one subject: `bender` reads the project, `extract` elaborates it,
`comments` and `markup` read the text, `graphs` and `dot` draw, `render` writes
the site. A module imports from a lower layer only;
[`tests/test_architecture.py`](tests/test_architecture.py) holds that rule and
the docstring of [`svdocgraph/__init__.py`](svdocgraph/__init__.py) gives the
layers.

A tag makes a release: `svdocgraph/__init__.py` gives the version, and
`git tag v0.2.0 && git push origin v0.2.0` starts the
[`release` workflow](.github/workflows/release.yml). That workflow runs the tests
again, builds the wheel, and publishes it to PyPI. PyPI trusts the workflow
through OpenID Connect, thus there is no token.

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
