/*
 * demo_top.sv
 * Copyright (C) 2026 ETH Zurich
 * Licensed under the Solderpad Hardware License
 */

/**
 * The **demo_top** module wires two adders in series. The net between them is
 * ``mid``. It also declares one **demo_bus_if** interface.
 *
 * .. figure:: img/demo_top.png
 *
 *   The structure of the top module.
 */
module demo_top
  import demo_pkg::*;
#(
  parameter int unsigned W = DataWidth
) (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic [W-1:0] x_i,
  output logic [W-1:0] y_o
);
  logic [W-1:0] mid;

  demo_bus_if #(.DW(W)) i_bus (.clk_i);

  demo_adder #(.W(W)) i_adder_a (
    .clk_i, .rst_ni, .a_i(x_i), .b_i(x_i), .sum_o(mid)
  );

  demo_adder #(.W(W)) i_adder_b (
    .clk_i, .rst_ni, .a_i(mid), .b_i(x_i), .sum_o(y_o)
  );

  assign i_bus.data  = y_o;
  assign i_bus.valid = 1'b1;
endmodule
