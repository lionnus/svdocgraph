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
