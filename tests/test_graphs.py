"""The graphs: what the DOT contains, and what it does not contain."""

from __future__ import annotations

import pytest
from conftest import needs_dot

from svdocgraph import graphs
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
    assert graphs.C_OWNED in dot, "the root package uses the accent colour"


def test_net_base_strips_selects_and_concatenations():
    assert graphs._net_base("data[7:0]") == "data"
    assert graphs._net_base("bus.payload") == "bus"
    assert graphs._net_base("1'b0") == ""
    assert graphs._net_base("") == ""


@needs_dot
def test_render_dot_produces_svg(design):
    svg = graphs.render_dot(graphs.hierarchy_dot(design))
    assert svg is not None
    assert svg.lstrip().startswith("<svg")
    assert "adder" in svg


def test_render_dot_returns_none_without_graphviz(monkeypatch, design):
    monkeypatch.setattr(graphs.shutil, "which", lambda _: None)
    assert graphs.render_dot(graphs.hierarchy_dot(design)) is None


def test_render_dot_returns_none_on_bad_dot(monkeypatch):
    monkeypatch.setattr(graphs.shutil, "which", lambda _: "/usr/bin/dot")
    assert graphs.render_dot("this is not dot at all {{{") is None


# -- node styling and connection roles --------------------------------------


def test_node_style_tells_the_module_classes_apart(design):
    design.modules["dep_mod"] = Module(name="dep_mod", package="common_cells")
    top = graphs._mod_node(design, "top")
    owned = graphs._mod_node(design, "adder")
    dep = graphs._mod_node(design, "dep_mod")
    unknown = graphs._mod_node(design, "never_elaborated")

    assert graphs.C_TOP in top, "a design top gets its own colour"
    assert graphs.C_OWNED in owned
    assert graphs.C_DEP in dep and "white" not in dep
    assert "dashed" in unknown, "a black box is drawn dashed"
    assert 'href="module-never_elaborated.html"' in unknown


def test_focus_highlights_a_module_that_is_not_a_top(design):
    assert graphs.C_OWNED in graphs._mod_node(design, "adder", focus=True)


def test_edges_carry_optional_labels_and_direction():
    assert graphs._edge("a", "b") == '  "a" -> "b";'
    assert 'label="net"' in graphs._edge("a", "b", label="net")
    assert "dir=none" in graphs._edge("a", "b", directed=False)


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
