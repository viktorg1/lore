"""The layering rules, enforced: lower layers never import higher ones.

    core         domain: models, storage, resolution            (imports nothing of lore's own)
    discovery    infers rules from code                          (core)
    cli, web, mcpserver   interfaces                             (core, discovery)

The scripts at the repository root only wrap an interface's `main`.
"""
import ast
import unittest
from pathlib import Path

import support

PACKAGES = {"core": set(), "discovery": {"core"}, "cli": {"core", "discovery"},
            "web": {"core", "discovery"}, "mcpserver": {"core", "discovery"}}
ROOT_SCRIPTS = {"memorize.py", "train.py", "discover.py", "review.py", "serve.py", "mcp_server.py"}


def imported_packages(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


class TestLayering(unittest.TestCase):
    def test_packages_only_import_downwards(self):
        for package, allowed in PACKAGES.items():
            for path in (support.ROOT / package).rglob("*.py"):
                bad = (imported_packages(path) & PACKAGES.keys()) - allowed - {package}
                self.assertFalse(bad, f"{path.relative_to(support.ROOT)} imports {sorted(bad)}")

    def test_core_has_no_interface_dependencies(self):
        """No command line, HTTP or browser code in the domain (it may still read files and ask git)."""
        for path in (support.ROOT / "core").rglob("*.py"):
            self.assertFalse(imported_packages(path) & {"argparse", "http", "socket", "webbrowser"}, path.name)

    def test_root_scripts_are_thin_wrappers(self):
        for name in ROOT_SCRIPTS:
            lines = [l for l in (support.ROOT / name).read_text().splitlines() if l.strip()]
            self.assertLessEqual(len(lines), 16, f"{name} should only wrap an interface's main()")
        self.assertEqual({p.name for p in support.ROOT.glob("*.py")}, ROOT_SCRIPTS)

    def test_every_package_is_a_package(self):
        for package in PACKAGES:
            self.assertTrue((support.ROOT / package / "__init__.py").exists(), package)


if __name__ == "__main__":
    unittest.main()
