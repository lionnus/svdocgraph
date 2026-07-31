"""The written documentation of the repository: discovery, HTML and links."""

from __future__ import annotations

import os

import pytest

from svdocgraph import docs

pytestmark = pytest.mark.skipif(not docs.HAVE_MARKDOWN, reason="markdown-it-py absent")


# -- discovery -------------------------------------------------------------


def test_the_readme_and_the_doc_directory_are_found(project_dir):
    found = docs.find_files(str(project_dir))
    assert found[0] == "README.md", "the README of the root comes first"
    assert os.path.join("doc", "demo_adder.md") in found


def test_a_project_without_documentation_gives_no_pages(tmp_path):
    assert docs.find_files(str(tmp_path)) == []


def test_a_directory_from_the_settings_is_also_read(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "guide.md").write_text("# Guide\n")
    assert docs.find_files(str(tmp_path), ["manual"]) == [os.path.join("manual", "guide.md")]


def test_a_very_large_file_is_not_documentation(tmp_path):
    d = tmp_path / "doc"
    d.mkdir()
    (d / "big.md").write_text("x" * (docs._MAX_BYTES + 1))
    assert docs.find_files(str(tmp_path)) == []


def test_the_slug_keeps_the_module_name(project_dir):
    assert docs._slug("doc/axi_xbar.md") == "doc-axi_xbar"
    assert docs._slug("README.md") == "doc-readme"
    assert docs._slug("docs/guide/intro.md") == "doc-guide-intro"


def test_two_files_with_the_same_name_get_different_pages(tmp_path):
    (tmp_path / "README.md").write_text("# Root\n")
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "README.md").write_text("# Inner\n")
    pages, _ = docs.build_pages(str(tmp_path), docs.find_files(str(tmp_path)))
    assert len(pages) == 2
    assert len({p.slug for p in pages.values()}) == 2


# -- rendering -------------------------------------------------------------


@pytest.fixture
def built(project_dir):
    rel = docs.find_files(str(project_dir))
    pages, media = docs.build_pages(str(project_dir), rel)
    return pages, media


def test_the_title_comes_from_the_first_heading(built):
    pages, _ = built
    assert pages["doc-readme"].title == "Demo IP"
    assert pages["doc-demo_adder"].title == "The registered adder"


def test_the_markdown_becomes_html(built):
    pages, _ = built
    html = pages["doc-readme"].html
    assert "<h1" in html and "<table>" in html and "<td>" in html


def test_html_in_the_source_does_not_reach_the_page(built):
    """A dependency must not put a script element in the site."""
    pages, _ = built
    html = pages["doc-demo_adder"].html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_each_heading_has_an_identifier(built):
    pages, _ = built
    page = pages["doc-demo_adder"]
    assert 'id="parameters"' in page.html
    assert ("2", "Parameters") == (str(page.headings[1][0]), page.headings[1][1])


def test_a_link_to_another_page_points_at_the_new_name(built):
    pages, _ = built
    assert 'href="doc-demo_adder.html"' in pages["doc-readme"].html


def test_a_link_to_an_external_address_does_not_change(tmp_path):
    (tmp_path / "README.md").write_text("[x](https://example.com/a.md) [y](#anchor)\n")
    pages, _ = docs.build_pages(str(tmp_path), ["README.md"])
    html = pages["doc-readme"].html
    assert 'href="https://example.com/a.md"' in html
    assert 'href="#anchor"' in html


def test_an_image_is_copied_and_the_address_changes(built, tmp_path):
    pages, media = built
    assert 'src="assets/docmedia/doc/adder.png"' in pages["doc-demo_adder"].html
    assert os.path.join("doc", "adder.png") in media
    docs.copy_media(media, str(tmp_path))
    assert (tmp_path / "assets" / docs.MEDIA_DIR / "doc" / "adder.png").is_file()


def test_an_image_outside_the_project_is_not_copied(tmp_path):
    (tmp_path / "README.md").write_text("![x](../../etc/passwd.png)\n")
    pages, media = docs.build_pages(str(tmp_path), ["README.md"])
    assert media == {}
    assert "assets/docmedia" not in pages["doc-readme"].html


# -- the connection to the design ------------------------------------------


def test_a_page_attaches_to_the_module_with_the_same_name(built):
    pages, _ = built
    docs.attach_to_modules(pages, ["demo_adder", "demo_top"])
    assert pages["doc-demo_adder"].module == "demo_adder"
    assert pages["doc-readme"].module == ""


def test_the_name_of_a_unit_becomes_a_link(built):
    pages, _ = built
    html = docs.link_names(pages["doc-readme"].html,
                           {"demo_top": "module-demo_top.html"})
    assert '<a class="xref" href="module-demo_top.html"><code>demo_top</code></a>' in html
    assert "<code>demo_adder</code>" in html, "an unknown name stays as it is"


def test_the_page_keeps_its_text_for_the_search(built):
    pages, _ = built
    text = pages["doc-demo_adder"].text
    assert "adds two numbers" in text
    assert "<" not in text


def test_the_readme_is_first_in_the_sequence(built):
    pages, _ = built
    assert docs.order_pages(pages)[0].slug == "doc-readme"


# -- reStructuredText ------------------------------------------------------

rst = pytest.mark.skipif(not docs.HAVE_RST, reason="docutils absent")

RST_PAGE = """\
=================
The stream engine
=================

``demo_adder`` moves the data.

The protocol
------------

Each transfer needs a handshake.

.. wavedrom::

   { "signal": [{ "name": "clk" }] }

.. figure:: img/stream.png

   A diagram.
"""


@rst
def test_a_restructuredtext_page_becomes_html(tmp_path):
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "stream.rst").write_text(RST_PAGE)
    pages, _ = docs.build_pages(str(tmp_path), [os.path.join("doc", "stream.rst")])
    page = pages["doc-stream"]
    assert page.title == "The stream engine"
    assert "<h2>" in page.html or 'id="the-protocol"' in page.html
    assert "handshake" in page.html


@rst
def test_a_directive_of_a_sphinx_extension_does_not_break_the_page(tmp_path):
    """`wavedrom` comes from an extension. docutils cannot read it, but the rest
    of the page must still appear, with no error block."""
    (tmp_path / "a.rst").write_text(RST_PAGE)
    pages, _ = docs.build_pages(str(tmp_path), ["a.rst"])
    html = pages["doc-a"].html
    assert "handshake" in html
    assert "system-message" not in html
    assert "wavedrom" not in html.lower()


@rst
def test_a_raw_directive_does_not_reach_the_page(tmp_path):
    """The rule for reStructuredText is the rule for Markdown: no raw HTML."""
    (tmp_path / "a.rst").write_text(
        "Title\n=====\n\n.. raw:: html\n\n   <script>alert(1)</script>\n"
    )
    pages, _ = docs.build_pages(str(tmp_path), ["a.rst"])
    assert "<script>" not in pages["doc-a"].html


@rst
def test_an_include_directive_cannot_read_another_file(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("the password is 1234")
    (tmp_path / "a.rst").write_text(f"Title\n=====\n\n.. include:: {secret}\n")
    pages, _ = docs.build_pages(str(tmp_path), ["a.rst"])
    assert "password" not in pages["doc-a"].html


@rst
def test_a_heading_keeps_the_identifier_that_docutils_made(tmp_path):
    """Two elements with the same identifier would make the anchor ambiguous."""
    (tmp_path / "a.rst").write_text(RST_PAGE)
    pages, _ = docs.build_pages(str(tmp_path), ["a.rst"])
    html = pages["doc-a"].html
    assert html.count('id="the-protocol"') == 1
    assert ("the-protocol") in [h[2] for h in pages["doc-a"].headings]


@rst
def test_the_name_of_a_module_becomes_a_link_in_a_rst_page(tmp_path):
    """docutils gives another element than Markdown for an inline literal."""
    (tmp_path / "a.rst").write_text(RST_PAGE)
    (tmp_path / "b.rst").write_text("T\n=\n\n`demo_adder` with one backtick.\n")
    pages, _ = docs.build_pages(str(tmp_path), ["a.rst", "b.rst"])
    targets = {"demo_adder": "module-demo_adder.html"}
    assert 'href="module-demo_adder.html"' in docs.link_names(pages["doc-a"].html, targets)
    assert 'href="module-demo_adder.html"' in docs.link_names(pages["doc-b"].html, targets)


# -- the Read the Docs settings --------------------------------------------


def test_the_read_the_docs_settings_give_the_directory(tmp_path):
    (tmp_path / ".readthedocs.yaml").write_text(
        "version: 2\nsphinx:\n  configuration: docs/source/conf.py\n"
    )
    assert docs.read_rtd_dirs(str(tmp_path)) == [os.path.join("docs", "source")]


def test_a_configuration_in_the_root_gives_the_root(tmp_path):
    """hwpe-doc keeps `conf.py` and the pages in the root of the repository."""
    (tmp_path / ".readthedocs.yml").write_text("version: 2\nsphinx:\n  configuration: conf.py\n")
    assert docs.read_rtd_dirs(str(tmp_path)) == ["."]


def test_pages_in_the_root_are_found_but_not_the_whole_repository(tmp_path):
    (tmp_path / ".readthedocs.yml").write_text("version: 2\nsphinx:\n  configuration: conf.py\n")
    (tmp_path / "index.rst").write_text("Title\n=====\n")
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "notes.md").write_text("# Not documentation\n")
    assert docs.find_files(str(tmp_path)) == ["index.rst"]


def test_a_broken_read_the_docs_file_is_ignored(tmp_path):
    (tmp_path / ".readthedocs.yaml").write_text("sphinx: [not, a, mapping\n")
    assert docs.read_rtd_dirs(str(tmp_path)) == []


def test_no_read_the_docs_file_gives_no_directory(tmp_path):
    assert docs.read_rtd_dirs(str(tmp_path)) == []


# -- the documentation comment of a module ---------------------------------


def test_a_comment_with_a_directive_is_restructuredtext():
    html = docs.render_comment("The module moves data.\n\n.. figure:: img/a.png\n")
    assert "<p>The module moves data.</p>" in html


def test_a_comment_without_a_directive_is_markdown():
    html = docs.render_comment("The **module** moves `data`.\n")
    assert "<strong>module</strong>" in html and "<code>data</code>" in html


def test_an_empty_comment_gives_no_html():
    assert docs.render_comment("   \n") == ""


def test_a_name_in_bold_becomes_a_link():
    """The comments in the PULP repositories put the name of a module in bold."""
    html = docs.render_comment("The **demo_adder** adds. **Name** is not a module.")
    linked = docs.link_names(html, {"demo_adder": "module-demo_adder.html"})
    assert '<a class="xref" href="module-demo_adder.html"><code>demo_adder</code></a>' in linked
    assert "<strong>Name</strong>" in linked


# -- the Doxygen commands ---------------------------------------------------


def test_a_comment_with_the_doxygen_commands():
    """Doxygen has no parser for SystemVerilog, but the commands are common."""
    html = docs.render_comment(
        "@brief A round-robin arbiter.\n\n"
        "@param NumIn The number of inputs.\n"
        "@param DataWidth The width of the data.\n"
        "@note Set @c LockIn to hold the grant.\n"
        "@return The index of the winner.\n"
    )
    assert "<p>A round-robin arbiter.</p>" in html
    assert "<code>NumIn</code> — The number of inputs." in html
    assert "<code>DataWidth</code>" in html
    assert "<strong>Note:</strong>" in html and "<code>LockIn</code>" in html
    assert "<strong>Returns:</strong> The index of the winner." in html
    assert "@" not in html, "each command must become Markdown"


def test_the_doxygen_commands_also_start_with_a_backslash():
    html = docs.render_comment("\\brief A counter.\n\\warning It has no reset.\n")
    assert "<p>A counter.</p>" in html or "A counter." in html
    assert "<strong>Warning:</strong>" in html


def test_the_doxygen_marks_for_emphasis():
    md = docs.doxygen_to_markdown("@b bold @a italic @p code @c also_code")
    assert md == "**bold** *italic* `code` `also_code`"


def test_a_comment_without_a_command_is_not_doxygen():
    """A mail address has an `@`, but it is not a command."""
    html = docs.render_comment("Ask anna@example.com about the **timing**.")
    assert "anna@example.com" in html and "<strong>timing</strong>" in html
