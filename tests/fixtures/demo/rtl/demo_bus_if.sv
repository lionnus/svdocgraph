// Interface with a modport, to exercise interface-port extraction.
interface demo_bus_if #(
  parameter int unsigned DW = 32
) (
  input logic clk_i
);
  logic [DW-1:0] data;
  logic          valid;
  logic          ready;

  modport master (output data, output valid, input  ready);
  modport slave  (input  data, input  valid, output ready);
endinterface
