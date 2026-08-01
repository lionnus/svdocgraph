// Registered adder: resolved parameters, clocks/resets, sized ports.
module demo_adder #(
  parameter int unsigned W = 8
) (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic [W-1:0] a_i,
  input  logic [W-1:0] b_i,
  output logic [W-1:0] sum_o
);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) sum_o <= '0;
    else         sum_o <= a_i + b_i;
  end
endmodule
