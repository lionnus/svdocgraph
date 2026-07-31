"""The parts of the renderer that the end-to-end tests do not examine."""

from __future__ import annotations

import json

from svdocgraph import render


def test_responsive_svg_drops_the_fixed_size():
    svg = '<svg width="120pt" height="80pt" viewBox="0 0 120 80"><g/></svg>'
    out = render._responsive(svg)
    assert 'width="120pt"' not in out
    assert 'height="80pt"' not in out
    assert 'viewBox="0 0 120 80"' in out, "the viewBox must survive so CSS can scale it"
    assert 'class="svdg-graph"' in out


def test_responsive_passes_through_a_missing_graph():
    assert render._responsive(None) is None


def test_inline_json_cannot_close_the_script_element():
    """A module with the name `</script>` must not close the data element."""
    payload = {"modules": [{"name": "</script><img src=x>"}]}
    out = render._json_for_script(payload)
    assert "</script>" not in out
    assert "<" not in out and ">" not in out
    assert json.loads(out)["modules"][0]["name"] == "</script><img src=x>"


def test_direction_badges_are_short():
    assert render._dirbadge("in") == "in"
    assert render._dirbadge("inout") == "io"
    assert render._dirbadge("interface") == "if"
    assert render._dirbadge("something_else") == "something_else"
