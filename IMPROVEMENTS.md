# SVDocGraph: verification and future work

## Verification

Tested end to end against a real Bender project (a HWPE accelerator with 17
dependencies). The following works today:

- `bender script flist-plus` and `bender sources -f` are read for the source set,
  include directories, defines, and the package each file belongs to.
- slang elaborates every module declared by the root package, including modules
  with macro-defined parameters and SV interface ports that do not elaborate as
  plain tops. 70 modules were extracted (37 owned by the root package), 0 errors.
- Also verified against upstream PULP repositories: `opope` (41 units, 14
  dependency packages) and `datamover` (20 units, 3 HWPE/HCI interfaces) run in
  CI; `cv32e40p` vega_v1.3.4 (26 units), `common_cells` v1.40.0 (117 units) and
  `axi` v0.39.10 (144 units, 7 interfaces) were verified by hand - all with zero
  diagnostics. Recent `cv32e40p` tags are not usable: their `Bender.yml` has an
  unresolvable `tech_cells_generic` requirement and lists two files that no
  longer exist.
- `bender` failures (an unresolvable dependency, a stale `sources` list) are
  reported with bender's own message and exit code 4, instead of being reduced to
  "no modules extracted". cv32e40p's `master` is an example of both.
- Elaborated units keep their declaration kind, so interfaces (`AXI_BUS`,
  `AXI_LITE`, ...) are presented and coloured as interfaces rather than modules.
- Ports carry resolved direction, type and bit width; parameters carry resolved
  values; instances are collected through generate blocks and arrays; interface
  connections resolve to the connected stream/bus instance and its modport.
- The static site builds: hierarchy graph, package graph, per-module internal
  connectivity diagrams, search index, light and dark themes.
- Packaging is verified: `uv build` produces a wheel that bundles the templates,
  CSS, JS and fonts; installing the wheel into a clean environment and running
  `svdocgraph build` from the installed entry point reproduces the full site.

### Building the docs

`svdocgraph gen` is the supported way to generate the documentation. It requires
`bender` and Graphviz (`dot`) on the `PATH`; the slang compiler ships with the
`pyslang` dependency. To wire it into a project, add a target that runs it (see
the `docs` example in the README) or run it as a CI job that publishes the output
directory to Pages.

`svdocgraph check <dir>` examines the result and gives exit code 1 if it is not
complete. A design that no longer elaborates gives a site with no module and no
error, thus a pipeline that only runs `gen` cannot see the failure. The two
workflows of this repository use the same command as a user does.

### Project ergonomics

- The project root is found by walking up to the nearest `Bender.yml`, so the tool
  works from any subdirectory.
- Output defaults to `.svdocgraph/` in the project root, and the first build adds
  that directory to the repository `.gitignore`.
- A build marks its output directory with `.svdocgraph-build.json`; `gen` refuses to
  clean a non-empty directory without that marker unless `--force` is given, and
  only removes files matching its own naming scheme.
- The search index is a script that each page loads, thus the search works over
  `file://` too, where a page cannot `fetch()` a file. It was in each page: on
  pulp-platform/axi that is 47 kB in each of 220 pages, which made the site 10 MB
  larger than it is now.
- The graphs answer to a pinch and to a drag with two fingers. The CSS gives one
  finger to the browser (`touch-action: pan-x pan-y`), thus the page still scrolls
  and a tap still opens a node.
- Below 860 px the side bar goes away and each column gets `min-width: 0`. Without
  that, a grid column keeps the width of its widest content and the page scrolls
  to the side. A wide table scrolls in its own box.
- `svdocgraph.yml` (optional, written by `svdocgraph init`) sets the output
  directory, extra tops and the display name, so `make docs` needs no flags.

### Dependencies

- `bender` and Graphviz are external programs; `svdocgraph doctor` reports both,
  and `gen` fails fast (exit 3) when bender is missing instead of rendering an
  empty site.
- `pyslang` is pinned to `>=11,<12`. Releases 8-10 expose `pyslang.Driver` with a
  different command-line API and silently extract zero modules; 11 moved it to
  `pyslang.driver`. The floor is enforced in `pyproject.toml` and reported by
  `doctor`.
- Python 3.9-3.13 are exercised in CI, matching the versions pyslang ships wheels
  for.

### Automated testing

- `tests/` drives the CLI end to end against a fixture design with a stub bender,
  so the suite needs no bender installation and runs anywhere.
- The `integration` workflow runs the real thing against `pulp-platform/opope`
  (an outer-product engine with 14 dependencies) and `pulp-platform/datamover`
  (an HWPE accelerator), pinned to commits, and asserts a floor on what is
  extracted (module and interface counts, named units, zero diagnostics, graphs
  rendered). Building it caught the interface-classification bug below and the
  swallowed bender errors.
- Coverage is measured with pytest-cov (statements and branches). It is 97%; the
  minimum is in `pyproject.toml` and CI enforces it. Codecov reports the coverage
  of each pull request.
- The tests were examined with a mutation experiment: 31 faults were put into the
  code on purpose, one at a time, and the tests found all of them. The first
  round of that experiment found six gaps (the side-bar order, the search index,
  the interface instances, the pages of a dependency module, the localparam
  filter and the comment length), which now have tests.
- A project in a directory with a space in its name now works: slang divides a
  command file at each space, so each entry gets quotation marks.

### The comment above a module

- `driver.syntaxTrees` gives the parsed files that the elaboration already made.
  Thus the tool reads the comments from the parser, and not with a regular
  expression: a `/** */` block, a `//` block, and a comment before an `import`
  each work.
- slang attaches a comment to the token that follows it. A PULP file has the
  licence block, then the documentation block, then often an import, then the
  module. The extractor collects the blocks of each member and gives the last
  one to the next module. A block that gives the licence is left out.
- A comment with a directive or a role is reStructuredText. A comment with a
  command that starts with `@` or with a backslash is Doxygen: `@brief`, `@param`
  and `@note` become Markdown, then the usual renderer makes the HTML. Doxygen
  has no parser for SystemVerilog, thus only its comment style is common: `///`
  and `//!` open a documentation line, and `/*!` opens a block.
  On pulp-platform/hwpe-stream, 33 of the 41 modules give a comment, and
  `hwpe_stream_source` gives 5.7 kB of reStructuredText.
- A name of a module in the comment becomes a link. The PULP comments write the
  name in bold, Markdown writes it in backticks; both work.
- A comment can come from an `include` file. `hci_helpers.svh` ends with
  ``` `endif /* `ifndef __HCI_HELPERS__ */ ```, and the HCI and common_cells
  modules took that as their description. The extractor now compares the file of
  each comment with the file of the module.
- The comment of an HCI module is above the `include`, and slang puts it in the
  trivia of that directive. Thus the extractor opens each directive. With the two
  corrections, pulp-platform/axi gives 120 comments in place of 97, and the
  datamover gives 12 in place of 6.
- A block that names the authors only is not a description, thus it is left out.

### The code of each file

- Pygments makes the colours and the line numbers. A page shows one file, because
  a file can have thousands of lines. The page of a module opens the code at its
  line, as Sphinx `viewcode`, Doxygen and rustdoc do.
- Only the root package gives pages. `bender checkout` puts the dependencies in
  the project, thus the package decides which file to show, and not the path. The
  code of a dependency has another licence and stays in its own repository.
- A file with more than 6000 lines keeps its page, but without the colours,
  because the lexer is slow on a large file. A file of more than 4 MB gets no page.
- The pages operate without Pygments. The tool then writes the same table, with
  the line numbers but with no colours.

### The graphs

- The colour of a pin gives the kind, and the shape gives the direction. Blue is
  an input, magenta an output, green an interface and orange no direction. These
  are the colours of the port table, thus the graph and the table agree.
- The direction of a logic port comes from the declaration. An interface port has
  no direction in the language: the name gives it (`_i`, `_in`, `_o`, `_out`),
  then the modport. A port that gives neither is a hexagon: the signals go in two
  directions. The name comes before the modport, because a person reads the name.
- `cds` draws about two thirds of the height of its node and `hexagon` draws the
  full height. Each pin gets the height that makes the two the same.
- A node opens what it shows: an instance opens the module, an interface port and
  an interface signal open the interface, and a file opens the code.
- An element of an instance array has no name of its own. The extractor takes the
  name from the array, thus `hci_core_intf virt_tcdm [1:0] (...)` and a module
  array are in the model. Before this, they were not.

### Written documentation

- The tool reads `README.md`, and the Markdown and reStructuredText files in
  `doc/`, `docs/` and `documentation/`. It writes them as pages of the same site.
- `.readthedocs.yaml` gives one more directory. `configuration: conf.py` means the
  root of the repository, and then only the files directly in the root are read.
- docutils reads the reStructuredText. It cannot run a Sphinx extension: a
  `wavedrom`, `svprettyplot` or `toctree` directive gives no output, and a `raw`
  directive is stopped for the same reason as the HTML in a Markdown file.
  Verified against the 8 pages of pulp-platform/hwpe-doc: each one renders, with
  no error block in the output.
- A page with the name of a module attaches to that module. `axi/doc/axi_xbar.md`
  and the module `axi_xbar` link to each other. On pulp-platform/axi, 7 of the 9
  pages attach in this way.
- In the text, a `code` element with the name of a module or a package becomes a
  link. The images are copied into the site. The links between the pages point at
  the new names.
- The HTML in a Markdown file is escaped, not written into the page.
- The file graph shows each source file and the files that it needs.

### The package layout

- 17 modules, each with one subject, and no module above 370 lines. The layers
  are in the docstring of `svdocgraph/__init__.py`, from `naming` and `model` at
  the bottom to `cli` at the top.
- `tests/test_architecture.py` reads the imports of each module and stops a
  module that imports from a higher layer. Before this rule, `deps` imported
  `extract` to find out if pyslang was usable; `deps` now makes that test itself.
- `svdocgraph.build_documentation` and `svdocgraph.check_site` give the two
  commands to another program. `__getattr__` imports on demand, thus
  `svdocgraph --version` does not load pyslang.
- The splits: `naming` (the rules that read a name) out of `model`; `comments`
  (the comment above a unit) out of `extract`; `markup` (Markdown,
  reStructuredText and Doxygen) out of `docs`; `dot` (the colours, the DOT syntax
  and the Graphviz process) out of `graphs`; `api` (the two steps) out of `cli`.

## Known limitations

- Clock and reset nets are detected by name pattern, not by tracing clock trees.
- A Sphinx extension does not run, so the output of `wavedrom`, `svprettyplot` and
  a similar directive is not in the page. A `:ref:` or `:numref:` role gives plain
  text, not a link.
- The `nav` of an `mkdocs.yml`, and the `toctree` of an `index.rst`, are not read.
  The pages are in the sequence of their paths, with the README first.
- `pulp-platform/hwpe-doc` is a repository of documentation only. It has no
  `Bender.yml`, thus this tool cannot run in it. The RTL of `hwpe-stream` and the
  text of `hwpe-doc` are in two repositories.
- Only modules reachable as a top of the root package (or reachable from one) are
  elaborated; dependency modules that are never instantiated appear as black boxes.
- Connection grouping uses the base signal name, so a bit-select and the full
  signal are treated as the same net.

## Future ideas

### Visualising generate blocks (evaluated)

Possible: yes. Sensible: yes, for designs that use generate heavily.

slang exposes the generate structure in the elaborated AST as
`GenerateBlockArraySymbol` (for `for`-generate) and `GenerateBlockSymbol` (for
`if`/`case`-generate), each with a name and the resolved loop range or branch
condition. The extractor currently descends into these blocks and flattens them:
loop copies of an instance are collapsed into a single `name xN` entry, and a
conditional generate is represented by whichever branch elaborated.

To show them, each generate block becomes a Graphviz cluster inside the cluster of
the module boundary, because a cluster can hold another cluster. The label gives the
name of the block and its condition, for example `for genvar i in [0:N]` or
`if (FEATURE_EN)`. Each instance of that block is then in its cluster. The graph
needs no new mechanism, thus the cost is small. The work is in the model: it must
keep the generate blocks, and not make one list of the instances. That needs a
`GenerateBlock` node between `Module` and `Instance`.

Trade-offs: deeper nesting makes the layout busier for designs with many small
generate blocks, and a flat `xN` summary is often easier to read for a simple loop.
Recommendation: add it as a grouping that is applied when a module has named
generate blocks, and keep the `xN` collapse for plain instance arrays. Medium
effort, good payoff for parameterised or conditionally-built modules.

### Other ideas

- Clock and reset domain map: trace clock and reset nets across the hierarchy and
  show domains and crossings, instead of per-module name detection.
- Bit-accurate connectivity: distinguish bit-selects and struct fields so partial
  connections are visible.
- Source links: link each module and port to its line in a repo web view.
- Config file: extend `svdocgraph.yml` with package excludes and a theme setting
  (output, tops and name are supported today).
- Package pages with package contents: typedefs and parameters declared in a
  SystemVerilog package, not only the modules that belong to it.
- Incremental builds and parallel graph rendering for very large designs.
- Read the `nav` of `mkdocs.yml` and the `toctree` of `index.rst`, to give the
  pages the sequence that the author chose.
- One file (`svdocgraph gen --single-file`) that holds the full site, to attach a
  design map to a review or to a mail. The site already operates offline. This step
  puts each module page in one document, and a hash gives the page.
- `svdocgraph serve --watch`, which makes the documentation again when the RTL
  changes.
