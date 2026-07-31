"""The data rules: the port direction, the clocks, the resets and the counts."""

from __future__ import annotations

import pytest

from svdocgraph.model import (
    Design,
    Instance,
    Module,
    Port,
    graph_dir,
    interface_dir,
    name_direction,
    reset_polarity,
)


@pytest.mark.parametrize(
    ("modport", "expected"),
    [
        ("source", "out"), ("master", "out"), ("mst", "out"), ("producer", "out"),
        ("sink", "in"), ("slave", "in"), ("slv", "in"), ("consumer", "in"),
        ("", "inout"), ("monitor", "inout"), ("SOURCE", "out"),
    ],
)
def test_modport_maps_to_a_direction(modport, expected):
    assert interface_dir(modport) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("rst_ni", "active-low"), ("rst_n", "active-low"), ("reset_n", "active-low"),
        ("arstn", "active-low"), ("rst_b", "active-low"),
        ("rst", "active-high"), ("reset", "active-high"), ("rst_i", "active-high"),
    ],
)
def test_reset_polarity_from_the_name(name, expected):
    assert reset_polarity(name) == expected


def test_interface_port_direction_comes_from_the_modport():
    plain = Port(name="a_i", direction="in")
    iface = Port(name="bus", direction="interface", is_interface=True, modport="master")
    assert plain.eff_dir == "in"
    assert iface.eff_dir == "out", "an interface port groups by its modport"


def test_module_counts_and_classification():
    mod = Module(
        name="m",
        ports=[
            Port("clk_i", "in"), Port("rst_ni", "in"), Port("a_i", "in"),
            Port("y_o", "out"),
            Port("bus", "interface", is_interface=True, modport="sink"),
        ],
        instances=[
            Instance(name="i_sub", module="sub"),
            Instance(name="i_bus", module="my_if", is_interface=True),
        ],
    )
    # The interface port is an input, because its modport is a sink.
    assert mod.n_inputs == 4
    assert mod.n_outputs == 1
    assert [p.name for p in mod.clocks] == ["clk_i"]
    assert [p.name for p in mod.resets] == ["rst_ni"]
    assert [i.name for i in mod.module_instances] == ["i_sub"]
    assert [i.name for i in mod.interface_instances] == ["i_bus"]


def test_design_is_json_serialisable():
    import json

    d = Design(root_package="p", project_root="/x")
    d.modules["m"] = Module(name="m", ports=[Port("a", "in", width=8)])
    payload = d.to_json()
    assert json.loads(json.dumps(payload))["modules"]["m"]["ports"][0]["width"] == 8


# -- the direction that a name gives ----------------------------------------


def test_the_name_of_a_port_can_give_the_direction():
    assert name_direction("data_i") == "in"
    assert name_direction("data_in") == "in"
    assert name_direction("flags_o") == "out"
    assert name_direction("data_out") == "out"
    assert name_direction("tcdm") == ""
    assert name_direction("rst_ni") == "", "a reset is not an input by name"


def test_the_declaration_gives_the_direction_of_a_logic_port():
    assert graph_dir(Port("data_o", "in")) == "in", "the language wins"
    assert graph_dir(Port("bus", "inout")) == ""
    assert graph_dir(Port("bus_i", "inout")) == "in"


def test_an_interface_port_takes_the_direction_from_the_name_first():
    port = Port("data_in", "interface", is_interface=True, modport="source")
    assert interface_dir("source") == "out", "the modport says the other way"
    assert graph_dir(port) == "in"


def test_an_interface_port_with_no_name_ending_uses_the_modport():
    port = Port("bus", "interface", is_interface=True, modport="slave")
    assert graph_dir(port) == "in"


def test_an_interface_port_with_no_direction_at_all():
    port = Port("tcdm", "interface", is_interface=True, modport="")
    assert graph_dir(port) == ""
