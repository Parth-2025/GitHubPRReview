import ast

from riskagent.models import DependencyEdge


def parse_imports(source: str) -> list[str]:
    tree = ast.parse(source)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.append(node.module)
    return modules


def _module_name_for_path(path: str) -> str:
    if path.endswith("/__init__.py"):
        path = path[: -len("/__init__.py")]
    elif path.endswith(".py"):
        path = path[: -len(".py")]
    return path.replace("/", ".")


def build_dependency_edges(files: dict[str, str]) -> list[DependencyEdge]:
    module_to_path = {_module_name_for_path(p): p for p in files}
    edges = []
    for path, source in files.items():
        try:
            imports = parse_imports(source)
        except SyntaxError:
            continue
        for module in imports:
            matched_path = module_to_path.get(module)
            if matched_path is None:
                matching_prefixes = [
                    (mod_name, mod_path)
                    for mod_name, mod_path in module_to_path.items()
                    if module.startswith(mod_name + ".")
                ]
                if matching_prefixes:
                    longest_match = max(matching_prefixes, key=lambda x: len(x[0]))
                    matched_path = longest_match[1]
            if matched_path and matched_path != path:
                edges.append(DependencyEdge(importer=path, imported=matched_path))
    return edges
