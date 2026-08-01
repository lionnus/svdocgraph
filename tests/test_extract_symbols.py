"""The extractor functions that read the elaborated tree.

These functions read the attributes of the slang symbols. The tests use
substitutes with the same attributes. Thus the tests can examine the interface
handling without a full elaboration.
"""

from __future__ import annotations

from svdocgraph import extract


class InterfacePortSymbol:
    def __init__(self, name, iface, modport=None):
        self.name = name
        self.interfaceDef = iface
        self.modport = modport


class PortSymbol:
    def __init__(self, name, direction, type_=None):
        self.name = name
        self.direction = direction
        self.type = type_


class ModportSymbol:
    def __init__(self, name):
        self.name = name


class Named:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class SVType:
    def __init__(self, text, bit_width=None):
        self.text = text
        self.bitWidth = bit_width

    def __str__(self):
        return self.text


class AssignmentExpression:
    def __init__(self, left=None, right=None):
        self.left = left
        self.right = right


class EmptyArgumentExpression:
    pass


class NamedValueExpression:
    def __init__(self, syntax):
        self.syntax = syntax


class PortConnection:
    def __init__(self, port=None, expression=None, iface_conn=None):
        self.port = port
        self.expression = expression
        self.ifaceConn = iface_conn


# -- ports -----------------------------------------------------------------


def test_interface_port_keeps_its_interface_and_modport():
    p = extract._port_from_symbol(
        InterfacePortSymbol("bus", Named("AXI_BUS"), ModportSymbol("master"))
    )
    assert p.is_interface
    assert p.interface == "AXI_BUS"
    assert p.modport == "master"
    assert p.eff_dir == "out", "a master modport is an output"


def test_interface_port_without_a_modport():
    p = extract._port_from_symbol(InterfacePortSymbol("bus", Named("AXI_BUS")))
    assert p.modport == ""
    assert p.eff_dir == "inout"


def test_ordinary_port_resolves_type_and_width():
    p = extract._port_from_symbol(
        PortSymbol("data_i", "ArgumentDirection.In", SVType("logic[31:0]", 32))
    )
    assert p.direction == "in"
    assert p.type == "logic[31:0]"
    assert p.width == 32
    assert not p.is_interface


def test_single_bit_port_has_no_width():
    p = extract._port_from_symbol(PortSymbol("clk_i", "ArgumentDirection.In", SVType("logic", 1)))
    assert p.width == 1


def test_unknown_symbols_are_skipped():
    assert extract._port_from_symbol(object()) is None


# -- connections -----------------------------------------------------------


def test_interface_connection_prefers_the_source_text():
    """For a boundary port, `ifaceConn` gives the name of the interface type.
    That name makes one net from two different streams."""
    pc = PortConnection(
        port=InterfacePortSymbol("bus", Named("AXI_BUS")),
        expression=NamedValueExpression("i_dma_bus"),
        iface_conn=(Named("AXI_BUS"), ModportSymbol("slave")),
    )
    net, modport, is_iface = extract._conn_info(pc, None)
    assert (net, modport, is_iface) == ("i_dma_bus", "slave", True)


def test_interface_connection_falls_back_to_the_instance_name():
    pc = PortConnection(
        port=InterfacePortSymbol("bus", Named("AXI_BUS")),
        expression=None,
        iface_conn=(Named("i_bus"), ModportSymbol("master")),
    )
    assert extract._conn_info(pc, None) == ("i_bus", "master", True)


def test_ordinary_connection_reads_the_expression():
    pc = PortConnection(port=PortSymbol("a_i", "in"),
                        expression=NamedValueExpression("some_net"))
    assert extract._conn_info(pc, None) == ("some_net", "", False)


def test_output_connection_follows_the_assignment():
    """slang puts the connection of an output port in an assignment. The
    external net is on one side of it."""
    expr = AssignmentExpression(left=NamedValueExpression("result_net"),
                                right=EmptyArgumentExpression())
    assert extract._net_text(expr, None) == "result_net"


def test_empty_assignment_yields_no_net():
    expr = AssignmentExpression(left=EmptyArgumentExpression(),
                                right=EmptyArgumentExpression())
    assert extract._net_text(expr, None) == ""


def test_unconnected_port_yields_no_net():
    assert extract._net_text(None, None) == ""


# -- modules ---------------------------------------------------------------


class Definition:
    def __init__(self, name, kind="Module", location="loc"):
        self.name = name
        self.definitionKind = kind
        self.location = location


class WildcardImportSymbol:
    def __init__(self, package):
        self.package = package


class Body:
    """A substitute for an elaborated module."""

    def __init__(self, definition, ports=(), parameters=(), members=()):
        self.definition = definition
        self.name = definition.name
        self.portList = list(ports)
        self.parameters = list(parameters)
        self._members = list(members)

    def __iter__(self):
        return iter(self._members)


class Parameter:
    def __init__(self, name, value, local=False):
        self.name = name
        self.value = value
        self.isLocal = local


class SourceManager:
    def getFileName(self, loc):
        return "/design/rtl/m.sv"

    def getLineNumber(self, loc):
        return 42


class BrokenSourceManager:
    def getFileName(self, loc):
        raise RuntimeError("no such buffer")

    def getLineNumber(self, loc):
        raise RuntimeError("no such buffer")


def test_module_carries_ports_parameters_imports_and_provenance():
    body = Body(
        Definition("my_module"),
        ports=[PortSymbol("a_i", "ArgumentDirection.In", SVType("logic", 1))],
        parameters=[Parameter("W", 8), Parameter("Hidden", 1, local=True)],
        members=[WildcardImportSymbol(Named("my_pkg"))],
    )
    mod = extract._module_from_body(body, SourceManager())
    assert mod.name == "my_module"
    assert mod.kind == "module"
    assert mod.elaborated
    assert [p.name for p in mod.ports] == ["a_i"]
    assert [(p.name, p.value, p.is_localparam) for p in mod.params] == [
        ("W", "8", False), ("Hidden", "1", True)
    ]
    assert mod.imports == ["my_pkg"]
    assert mod.file == "/design/rtl/m.sv"
    assert mod.line == 42


def test_module_without_provenance_still_extracts():
    """The module stays, also if the tool cannot find its file and its line."""
    body = Body(Definition("my_module"), ports=[
        PortSymbol("a_i", "ArgumentDirection.In", SVType("logic", 1))
    ])
    mod = extract._module_from_body(body, BrokenSourceManager())
    assert mod.file == "" and mod.line == 0
    assert [p.name for p in mod.ports] == ["a_i"]


def test_interface_body_keeps_its_kind():
    mod = extract._module_from_body(Body(Definition("my_if", kind="Interface")), None)
    assert mod.kind == "interface"


# -- source text -----------------------------------------------------------


class Range:
    class _Point:
        def __init__(self, offset):
            self.buffer = "buf"
            self.offset = offset

    def __init__(self, start, end):
        self.start = self._Point(start)
        self.end = self._Point(end)


class RangeExpression:
    """An expression that has a source range, but no syntax node."""

    def __init__(self, start, end):
        self.syntax = None
        self.sourceRange = Range(start, end)


class TextSourceManager:
    def getSourceText(self, buffer):
        return "assign x = data_bus[3];"


def test_net_text_falls_back_to_the_source_range():
    assert extract._net_text(RangeExpression(11, 22), TextSourceManager()) == "data_bus[3]"


def test_net_text_survives_a_bad_source_range():
    assert extract._net_text(RangeExpression(11, 9999), BrokenSourceManager()) == ""


class Instance:
    """A substitute for an elaborated instance."""

    def __init__(self, name, body, connections=()):
        self.name = name
        self.body = body
        self.portConnections = list(connections)


def test_instance_keeps_the_parameter_overrides_but_not_the_localparams():
    """A localparam is internal to the module. It is not an override."""
    body = Body(Definition("demo_adder"),
                parameters=[Parameter("W", 32), Parameter("Internal", 7, local=True)])
    inst = extract._instance_from_symbol(Instance("i_a", body), None)
    assert inst.params == {"W": "32"}
    assert inst.module == "demo_adder"
    assert not inst.is_interface


def test_an_instance_of_an_interface_is_marked():
    body = Body(Definition("my_if", kind="Interface"))
    assert extract._instance_from_symbol(Instance("i_bus", body), None).is_interface


def test_instance_connections_are_collected():
    body = Body(Definition("demo_adder"))
    conn = PortConnection(port=PortSymbol("a_i", "in"),
                          expression=NamedValueExpression("x_i"))
    inst = extract._instance_from_symbol(Instance("i_a", body, [conn]), None)
    assert [(c.port, c.net) for c in inst.conns] == [("a_i", "x_i")]
