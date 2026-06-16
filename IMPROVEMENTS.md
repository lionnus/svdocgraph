# SVDocGraph: verification and future work

## Verification

Tested end to end against a real Bender project (a HWPE accelerator with 17
dependencies). The following works today:

- `bender script flist-plus` and `bender sources -f` are read for the source set,
  include directories, defines, and the package each file belongs to.
- slang elaborates every module declared by the root package, including modules
  with macro-defined parameters and SV interface ports that do not elaborate as
  plain tops. 70 modules were extracted (37 owned by the root package), 0 errors.
- Ports carry resolved direction, type and bit width; parameters carry resolved
  values; instances are collected through generate blocks and arrays; interface
  connections resolve to the connected stream/bus instance and its modport.
- The static site builds: hierarchy graph, package graph, per-module internal
  connectivity diagrams, search index, light and dark themes.
- Packaging is verified: `uv build` produces a wheel that bundles the templates,
  CSS, JS and fonts; installing the wheel into a clean environment and running
  `svdocgraph build` from the installed entry point reproduces the full site.

### Building the docs

`svdocgraph build` is the supported way to generate the documentation. It requires
`bender` and Graphviz (`dot`) on the `PATH`; the slang compiler ships with the
`pyslang` dependency. To wire it into a project, add a target that runs it (see the
`docs` example in the README) or run it as a CI job that publishes the output
directory to Pages.

## Known limitations

- Clock and reset nets are detected by name pattern, not by tracing clock trees.
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

To show them, each generate block would become a nested Graphviz cluster inside the
existing module-boundary cluster (clusters nest), labelled with the block name and
its condition, for example `for genvar i in [0:N]` or `if (FEATURE_EN)`. The
instances created in that block would be drawn inside its cluster. This reuses the
clustering already used for the module boundary, so the rendering cost is small; the
main work is preserving the generate nesting in the data model instead of flattening
it (a `GenerateBlock` node type between `Module` and `Instance`).

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
- Config file (`svdocgraph.yml`): exclude packages, pick tops, set the theme.
- Package pages with package contents: typedefs and parameters declared in a
  SystemVerilog package, not only the modules that belong to it.
- Incremental builds and parallel graph rendering for very large designs.
