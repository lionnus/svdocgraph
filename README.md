# SVDocGraph

[![ci](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/ci.yml)
[![integration](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml/badge.svg)](https://github.com/lionnus/svdocgraph/actions/workflows/integration.yml)
[![codecov](https://codecov.io/gh/lionnus/svdocgraph/graph/badge.svg)](https://codecov.io/gh/lionnus/svdocgraph)
[![python](https://img.shields.io/badge/python-3.9%20%E2%80%93%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

SVDocGraph makes documentation for SystemVerilog designs that use
[Bender](https://github.com/pulp-platform/bender).

The tool reads a Bender project and writes a static web site. The site shows the
design hierarchy, the ports and the parameters of each module, and a block diagram
of the contents of each module.

The tool uses [slang](https://github.com/MikePopoloski/slang), through `pyslang`,
to elaborate the design. Thus the tool expands the macros, resolves the parameter
values, calculates the port widths, and reads the instance tree from the elaborated
design. The tool does not guess this data from the source text.

## Features

- **Block diagram for each module.** The diagram shows the child instances and the
  signals between them. Interfaces and buses are included.
- **Module pages.** Each page shows the ports in groups by direction. Each port has
  its resolved type and width. Each page also shows the parameter values, the child
  instances, the clocks, the resets, and the parent modules.
- **Hierarchy graph.** The graph shows the instance tree. Click on a module to open
  its page.
- **Package graph.** The graph shows the Bender dependencies with their versions,
  their locked revisions and their sources.
- **Search.** Push `/` or Ctrl-K to search for a module, a port or a package.
- **Offline output.** The site contains only HTML, CSS, JavaScript and SVG. A server
  is not necessary. Copy the directory to any static web host.

## Requirements

| Item | Function | Necessary | Installation |
| --- | --- | --- | --- |
| [`bender`](https://github.com/pulp-platform/bender) | Gives the source files, the include directories, the macro definitions and the package of each file | Yes | `curl https://pulp-platform.github.io/bender/init -sSf \| sh` |
| [Graphviz](https://graphviz.org/) (`dot`) | Calculates the layout of each graph | Recommended | `apt install graphviz` or `brew install graphviz` |
| `pyslang` 11 | Elaborates the design | Yes | Installed with the tool |
| `Jinja2`, `PyYAML` | Makes the HTML pages and reads the Bender files | Yes | Installed with the tool |

A simulator or a licence is not necessary. The slang compiler is included in the
`pyslang` package.

The `pyslang` version limit is a requirement. In version 11 the `Driver` class moved
to `pyslang.driver`. With an older version the tool finds no modules.

To show the status of each item, run this command:

```sh
svdocgraph doctor
```

If `bender` is not available, the tool stops with exit code 3. If Graphviz is not
available, the tool gives a warning and writes the pages without the graphs.

## Installation

Install the tool one time. Then use it in each Bender project. The tool does not add
files to the project.

```sh
uv tool install svdocgraph      # or: pipx install svdocgraph
```

To use the tool without installation, run `uvx svdocgraph gen`.

## Usage

Run the tool in a Bender project. The tool finds the project root. The project root
is the nearest parent directory that contains a `Bender.yml` file.

```sh
cd my-bender-project
svdocgraph gen --open
```

The tool elaborates the design, writes the documentation to `.svdocgraph/`, and opens
the documentation in the web browser.

| Command | Function |
| --- | --- |
| `svdocgraph gen` | Makes the documentation in `.svdocgraph/` |
| `svdocgraph gen --open` | Makes the documentation and opens it |
| `svdocgraph open` | Opens the last documentation. Makes it first if it is not available |
| `svdocgraph serve` | Makes the documentation and serves it on `http://localhost:8080` |
| `svdocgraph gen -o public` | Writes the documentation to a different directory |
| `svdocgraph init` | Writes `svdocgraph.yml` and a `.gitignore` rule |
| `svdocgraph doctor` | Shows the status of the necessary programs |
| `svdocgraph dump -o design.json` | Writes only the design data as JSON |

The name `build` is an alternative for `gen`.

Configuration is not necessary. The tool asks `bender` for the source files, the
include directories, the macro definitions and the package of each file. The tool
then elaborates each module of the root package. Use `--top NAME` to add a module
that only a testbench instantiates.

### Output

The tool writes the documentation to `.svdocgraph/` in the project root. This
directory has one owner: the tool. Thus the project needs only one `.gitignore` rule,
and the output cannot mix with a manual `docs/` directory. The first `gen` command
adds the rule to the `.gitignore` file of the repository.

To read the documentation, open `.svdocgraph/index.html` in a web browser. The
search function, the graphs and the theme operate offline.

The `gen` command does not write into a directory that contains other files. To
replace such a directory, use the `--force` option.

### Configuration

The `svdocgraph init` command writes an `svdocgraph.yml` file. Then the `svdocgraph
gen` command, and a `make` rule that calls it, do not need options. Each key is
optional.

```yaml
output: .svdocgraph        # Directory for the documentation
tops: [my_testbench_top]   # Additional top modules to elaborate
name: My Design            # Title in the page header
```

### Integration in a project

To make the documentation from `make`, add this rule:

```makefile
.PHONY: docs
docs:
	svdocgraph gen -q
```

To publish the documentation from GitLab CI, add this job:

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

## Operation

```
Bender.yml / Bender.lock
        |  bender script flist-plus   (sources, include dirs, defines)
        |  bender sources -f          (file -> package)
        v
   slang / pyslang    elaborates each module of the root package
        v
   design model       modules, ports, parameters, instances, connections
        v
   Graphviz + Jinja   block diagrams, hierarchy, package graph -> static site
```

## Development

```sh
uv sync --extra dev
uv run pytest                  # 160 tests
uv run pytest --cov            # tests with the coverage report
uv run ruff check .
```

The tests use a small design in `tests/fixtures/demo` and a substitute for `bender`.
Thus an installation of `bender` is not necessary, and the tests operate on each
platform.

Coverage is 97% of the statements and the branches. There are two controls:

- `fail_under` in `pyproject.toml` stops a local run and a CI job that goes below
  the agreed minimum. Do not decrease this value to make a failed job pass.
- Codecov shows the coverage of each pull request, and which new lines have no
  test. The settings are in `codecov.yml`.

The tests were examined with a mutation experiment: 31 faults were put into the
code on purpose, one at a time. The tests found each of them.

Two workflows operate in CI:

- **`ci`** — runs `ruff`, then the tests on Python 3.9 to 3.13, then the coverage
  measurement. The last job builds the wheel, installs it in an empty environment,
  and runs the installed command. The templates, the style sheet, the JavaScript and
  the fonts must be in the wheel.
- **`integration`** — makes documentation for two
  [PULP Platform](https://github.com/pulp-platform) designs with the true `bender`.

  | Design | Type | Result |
  | --- | --- | --- |
  | [`opope`](https://github.com/pulp-platform/opope) | Outer-product engine with 14 dependencies | 41 units, 2 interfaces, 0 diagnostics |
  | [`datamover`](https://github.com/pulp-platform/datamover) | HWPE accelerator with stream and HCI interfaces | 20 units, 3 interfaces, 0 diagnostics |

  Each job makes sure that the tool found the expected modules, the expected
  interfaces and no diagnostics. `scripts/check_site.py` contains these tests. Each
  job also keeps the documentation as an artifact. You can download the artifact and
  read it.

Each design has a fixed tag or commit. Thus a change in a design cannot cause a
failure in a pull request. The weekly job finds a failure that a new version of
`bender`, `pyslang`, Graphviz or the runner image causes. To change a version, make
a commit.

## License

Apache-2.0. See [LICENSE](LICENSE).

The IBM Plex fonts in `svdocgraph/assets/fonts` have the SIL Open Font License 1.1.
See `svdocgraph/assets/fonts/OFL.txt`.
