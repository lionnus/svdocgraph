"""The rules that read the name of a port."""

from __future__ import annotations

from rtldoc.model import Port
from rtldoc.naming import interface_dir, name_direction


def test_the_name_of_a_port_can_give_the_direction():
    assert name_direction("data_i") == "in"
    assert name_direction("data_in") == "in"
    assert name_direction("flags_o") == "out"
    assert name_direction("data_out") == "out"
    assert name_direction("tcdm") == ""
    assert name_direction("rst_ni") == "", "a reset is not an input by name"


def test_the_declaration_gives_the_direction_of_a_logic_port():
    assert Port("data_o", "in").graph_dir == "in", "the language wins"
    assert Port("bus", "inout").graph_dir == ""
    assert Port("bus_i", "inout").graph_dir == "in"


def test_an_interface_port_takes_the_direction_from_the_name_first():
    port = Port("data_in", "interface", is_interface=True, modport="source")
    assert interface_dir("source") == "out", "the modport says the other way"
    assert port.graph_dir == "in"


def test_an_interface_port_with_no_name_ending_uses_the_modport():
    port = Port("bus", "interface", is_interface=True, modport="slave")
    assert port.graph_dir == "in"


def test_an_interface_port_with_no_direction_at_all():
    port = Port("tcdm", "interface", is_interface=True, modport="")
    assert port.graph_dir == ""
