// Minimal package so the extractor sees package-scoped parameters.
package demo_pkg;
  parameter int unsigned DataWidth = 32;
  typedef logic [DataWidth-1:0] data_t;
endpackage
