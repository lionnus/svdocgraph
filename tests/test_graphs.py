"""The graphs: what the DOT contains, and what it does not contain."""

from __future__ import annotations

import pytest
from conftest import needs_dot

from svdocgraph import dot as dotlib
from svdocgraph import graphs
from svdocgraph.dot import (
    C_DEP,
    C_IFACE,
    C_IN,
    C_OWNED,
    C_TOP,
    edge,
    render_dot,
)
from svdocgraph.model import BenderPackage, Design, Instance, Module, Port, PortConn


@pytest.fixture
def design() -> Design:
    """A design with two levels. The net `mid` connects the two adders."""
    d = Design(root_package="demo_ip", project_root="/demo", tops=["top"])
    d.modules["adder"] = Module(
        name="adder", package="demo_ip",
        ports=[Port("clk_i", "in"), Port("rst_ni", "in"), Port("a_i", "in", width=8),
               Port("sum_o", "out", width=8)],
    )
    d.modules["top"] = Module(
        name="top", package="demo_ip",
        ports=[Port("clk_i", "in"), Port("x_i", "in", width=8),
               Port("y_o", "out", width=8)],
        instances=[
            Instance(name="i_a", module="adder", conns=[
                PortConn("clk_i", "clk_i"), PortConn("a_i", "x_i"),
                PortConn("sum_o", "mid"),
            ]),
            Instance(name="i_b", module="adder", conns=[
                PortConn("clk_i", "clk_i"), PortConn("a_i", "mid"),
                PortConn("sum_o", "y_o"),
            ]),
        ],
    )
    d.packages["demo_ip"] = BenderPackage(name="demo_ip", root=True, deps=["common_cells"])
    d.packages["common_cells"] = BenderPackage(name="common_cells", version="1.40.0")
    return d


def test_internal_graph_shows_instances_and_the_net_between_them(design):
    dot = graphs.internal_dot(design, "top")
    assert "i__i_a" in dot and "i__i_b" in dot
    assert "mid" in dot, "the net joining the two instances must appear"
    assert "p__x_i" in dot and "p__y_o" in dot, "boundary ports become pins"


def test_internal_graph_omits_clocks_and_resets(design):
    """A clock net touches each instance. It would hide the data flow."""
    dot = graphs.internal_dot(design, "top")
    assert "clk_i" not in dot
    assert "rst_ni" not in dot


def test_internal_graph_is_empty_for_a_leaf_module(design):
    assert graphs.internal_dot(design, "adder") == ""


def test_internal_graph_drops_single_endpoint_nets(design):
    """A net with one end is not a connection. The graph does not show it."""
    design.modules["top"].instances[0].conns.append(PortConn("b_i", "dangling"))
    assert "dangling" not in graphs.internal_dot(design, "top")


def test_hierarchy_graph_links_parent_to_child(design):
    dot = graphs.hierarchy_dot(design)
    assert '"top"' in dot and '"adder"' in dot
    assert '"top" -> "adder"' in dot
    assert "module-top.html" in dot, "nodes must be clickable"


def test_hierarchy_graph_respects_the_node_budget(design):
    dot = graphs.hierarchy_dot(design, max_nodes=1)
    assert dot.count("module-") <= 1


def test_package_graph_marks_the_root_and_its_dependencies(design):
    dot = graphs.package_dot(design)
    assert "package-demo_ip.html" in dot
    assert '"demo_ip" -> "common_cells"' in dot
    assert C_OWNED in dot, "the root package uses the accent colour"


def test_net_base_strips_selects_and_concatenations():
    assert graphs._net_base("data[7:0]") == "data"
    assert graphs._net_base("bus.payload") == "bus"
    assert graphs._net_base("1'b0") == ""
    assert graphs._net_base("") == ""


@needs_dot
def test_render_dot_produces_svg(design):
    svg = render_dot(graphs.hierarchy_dot(design))
    assert svg is not None
    assert svg.lstrip().startswith("<svg")
    assert "adder" in svg


def test_render_dot_returns_none_without_graphviz(monkeypatch, design):
    monkeypatch.setattr(dotlib.shutil, "which", lambda _: None)
    assert render_dot(graphs.hierarchy_dot(design)) is None


def test_render_dot_returns_none_on_bad_dot(monkeypatch):
    monkeypatch.setattr(dotlib.shutil, "which", lambda _: "/usr/bin/dot")
    assert render_dot("this is not dot at all {{{") is None


# -- node styling and connection roles --------------------------------------


def test_node_style_tells_the_module_classes_apart(design):
    design.modules["dep_mod"] = Module(name="dep_mod", package="common_cells")
    top = graphs._mod_node(design, "top")
    owned = graphs._mod_node(design, "adder")
    dep = graphs._mod_node(design, "dep_mod")
    unknown = graphs._mod_node(design, "never_elaborated")

    assert C_TOP in top, "a design top gets its own colour"
    assert C_OWNED in owned
    assert C_DEP in dep and "white" not in dep
    assert "dashed" in unknown, "a black box is drawn dashed"
    assert 'href="module-never_elaborated.html"' in unknown


def test_focus_highlights_a_module_that_is_not_a_top(design):
    assert C_OWNED in graphs._mod_node(design, "adder", focus=True)


def test_edges_carry_optional_labels_and_direction():
    assert edge("a", "b") == '  "a" -> "b";'
    assert 'label="net"' in edge("a", "b", label="net")
    assert "dir=none" in edge("a", "b", directed=False)


def test_connection_role_follows_the_child_port_direction(design):
    child = design.modules["adder"]
    assert graphs._role(child, "a_i") == "load"
    assert graphs._role(child, "sum_o") == "driver"
    assert graphs._role(child, "unknown_port") == "both"
    assert graphs._role(None, "a_i") == "both", "a black box has no known directions"


def test_connection_role_follows_the_modport_for_interfaces():
    assert graphs._iface_role("source") == "driver"
    assert graphs._iface_role("SINK") == "load"
    assert graphs._iface_role("monitor") == "both"
    assert graphs._iface_role("") == "both"


def test_interface_connections_use_the_modport_not_the_port_direction(design):
    conn = PortConn("bus", "i_stream", is_interface=True, modport="source")
    assert graphs._conn_role(conn, design.modules["adder"]) == "driver"


def test_a_net_with_three_endpoints_uses_a_hub(design):
    """Two ends connect directly. More ends need a signal node between them."""
    design.modules["top"].instances.append(
        Instance(name="i_c", module="adder", conns=[PortConn("a_i", "mid")])
    )
    dot = graphs.internal_dot(design, "top")
    assert '"n__mid"' in dot, "the shared net becomes its own node"


def test_hierarchy_visits_a_repeated_module_one_time(design):
    design.modules["top"].instances.append(
        Instance(name="i_c", module="adder", conns=[])
    )
    dot = graphs.hierarchy_dot(design)
    assert dot.count('"adder" [') == 1


def test_a_black_box_connection_has_no_direction(design):
    """The ports of a black box are unknown. Thus the edge has no arrow."""
    design.modules["top"].instances.append(
        Instance(name="i_x", module="unknown_cell", conns=[PortConn("p", "mid")])
    )
    assert "dir=none" in graphs.internal_dot(design, "top")


def test_hierarchy_skips_a_top_that_was_not_extracted(design):
    design.tops.append("absent_top")
    dot = graphs.hierarchy_dot(design)
    assert '"absent_top" ->' not in dot


# -- the file graph --------------------------------------------------------


def test_the_file_graph_joins_the_files_of_the_design(design):
    design.modules["top"].rel_file = "rtl/top.sv"
    design.modules["adder"].rel_file = "rtl/adder.sv"
    dot = graphs.file_dot(design)
    assert '"rtl/top.sv" -> "rtl/adder.sv"' in dot
    assert "top.sv" in dot and "adder.sv" in dot


def test_the_file_graph_marks_a_file_of_a_dependency(design):
    design.modules["top"].rel_file = "rtl/top.sv"
    design.modules["adder"].rel_file = "deps/adder.sv"
    design.modules["adder"].package = "common_cells"
    dot = graphs.file_dot(design)
    assert C_DEP in dot, "a file of a dependency has another colour"


def test_the_file_graph_needs_a_file_for_each_module(design):
    """Without the file of any module there is nothing to draw."""
    assert graphs.file_dot(design) == ""


def test_the_file_graph_has_no_edge_from_a_file_to_itself(design):
    design.modules["top"].rel_file = "rtl/all.sv"
    design.modules["adder"].rel_file = "rtl/all.sv"
    assert '"rtl/all.sv" -> "rtl/all.sv"' not in graphs.file_dot(design)


def test_the_file_graph_opens_the_code_of_a_file(design):
    from svdocgraph.model import SourceFile
    design.modules["top"].rel_file = "rtl/top.sv"
    design.modules["adder"].rel_file = "rtl/adder.sv"
    design.sources["src-rtl-top-sv"] = SourceFile(slug="src-rtl-top-sv",
                                                  rel_path="rtl/top.sv")
    dot = graphs.file_dot(design)
    assert 'href="src-rtl-top-sv.html"' in dot
    assert 'href="src-rtl-adder-sv.html"' not in dot, "that file has no page"


# -- interfaces in the internal graph ---------------------------------------


@pytest.fixture
def with_interface(design) -> Design:
    """`top` gets three interface ports and an interface that it declares.

    `bus` has a modport, `data_in` has a name that gives the direction, and
    `tcdm` gives neither.
    """
    d = design
    d.modules["demo_if"] = Module(name="demo_if", kind="interface", package="demo_ip")
    for name, modport in (("bus", "master"), ("data_in", "sink"), ("tcdm", "")):
        d.modules["top"].ports.append(
            Port(name, "interface", is_interface=True, interface="demo_if",
                 modport=modport)
        )
    d.modules["top"].instances.append(
        Instance(name="stream", module="demo_if", is_interface=True)
    )
    for i, inst in enumerate(d.modules["top"].instances[:2]):
        inst.conns += [PortConn("bus_i", "bus"), PortConn("d_i", "data_in"),
                       PortConn("t_io", "tcdm"),
                       PortConn("s_o" if i == 0 else "s_i", "stream")]
    return d


def test_an_interface_port_with_no_direction_is_a_bidirectional_pin(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    assert '"p__tcdm" [shape=hexagon' in dot, "no modport and no name ending"
    assert '"p__x_i" [shape=cds' in dot, "`input` gives the direction"


def test_the_name_of_an_interface_port_gives_the_direction(with_interface):
    """`data_in` has the `sink` modport, but the name is what a person reads."""
    dot = graphs.internal_dot(with_interface, "top")
    assert "rank=min; \"p__data_in\" [shape=cds, " in dot
    assert "orientation=180" not in dot.split('"p__data_in"')[0].split("rank=min")[-1]


def test_the_modport_gives_the_direction_when_the_name_does_not(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    assert 'rank=max; "p__bus" [shape=cds, height=0.37, margin="0.16,0.0", orientation=180' in dot


def test_each_interface_port_keeps_the_colour_of_an_interface(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    for pin in ("p__bus", "p__data_in", "p__tcdm"):
        attrs = dot.split(f'"{pin}" [')[1].split("]")[0]
        assert C_IFACE in attrs, f"{pin} must have the interface colour"
    logic = dot.split('"p__x_i" [')[1].split("]")[0]
    assert C_IN in logic and C_IFACE not in logic


def test_each_pin_and_signal_has_the_same_height(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    assert "shape=cds, height=0.37" in dot
    assert "shape=hexagon, height=0.25" in dot
    assert "shape=box, height=0.25" in dot


def test_an_interface_port_opens_its_declaration(with_interface):
    assert 'href="module-demo_if.html"' in graphs.internal_dot(with_interface, "top")


def test_a_signal_that_carries_an_interface_opens_its_declaration(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    assert '"n__stream" [shape=box, height=0.25, margin="0.10,0.0", href="module-demo_if.html"' in dot
    assert C_IFACE in dot, "the interface has its own colour"


def test_a_signal_that_is_not_an_interface_has_no_link(with_interface):
    dot = graphs.internal_dot(with_interface, "top")
    assert '"n__mid" [shape=box, height=0.25, margin="0.10,0.0", label=' in dot


def test_a_link_needs_a_unit_that_the_tool_found(design):
    assert graphs._link(design, "") == ""
    assert graphs._link(design, "not_extracted") == ""
