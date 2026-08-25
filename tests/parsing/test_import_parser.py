from riskagent.parsing.import_parser import parse_imports, build_dependency_edges


def test_parse_imports_plain_import():
    source = "import os\nimport pkg.mod\n"
    assert parse_imports(source) == ["os", "pkg.mod"]


def test_parse_imports_from_import():
    source = "from pkg import mod\nfrom pkg.sub import thing\n"
    assert parse_imports(source) == ["pkg", "pkg.sub"]


def test_parse_imports_ignores_relative_imports():
    source = "from . import sibling\n"
    assert parse_imports(source) == []


def test_build_dependency_edges_resolves_within_repo():
    files = {
        "pkg/a.py": "from pkg import b\n",
        "pkg/b.py": "import os\n",
        "pkg/__init__.py": "",
    }
    edges = build_dependency_edges(files)
    assert len(edges) == 1
    assert edges[0].importer == "pkg/a.py"
    assert edges[0].imported == "pkg/__init__.py"


def test_build_dependency_edges_resolves_submodule_import():
    files = {
        "pkg/a.py": "import pkg.sub.mod\n",
        "pkg/sub/mod.py": "",
    }
    edges = build_dependency_edges(files)
    assert len(edges) == 1
    assert edges[0].importer == "pkg/a.py"
    assert edges[0].imported == "pkg/sub/mod.py"


def test_build_dependency_edges_ignores_self_and_external():
    files = {
        "pkg/a.py": "import requests\nimport pkg.a\n",
    }
    edges = build_dependency_edges(files)
    assert edges == []
