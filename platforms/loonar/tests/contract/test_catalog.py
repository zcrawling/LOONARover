#!/usr/bin/env python3
"""Contract tests for the interface catalog generator."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


def load_generator(repo_root: Path):
    path = repo_root / "common" / "tools" / "gen_catalog.py"
    spec = importlib.util.spec_from_file_location("gen_catalog", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogContractTest(unittest.TestCase):
    repo_root: Path
    generator: object

    def test_checked_in_outputs_are_current(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.repo_root / "common" / "tools" / "gen_catalog.py"),
                "--root",
                str(self.repo_root),
                "--check",
            ],
            check=False,
        )
        self.assertEqual(completed.returncode, 0)

    def test_duplicate_id_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.generator.load_all(self.repo_root)[0])
        catalog["entries"][1]["id"] = catalog["entries"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            self.generator.validate_catalog(catalog)

    def test_reserved_id_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.generator.load_all(self.repo_root)[2])
        catalog["entries"][0]["id"] = "0x00"
        with self.assertRaisesRegex(ValueError, "reserved"):
            self.generator.validate_catalog(catalog)

    def test_generation_is_deterministic(self) -> None:
        catalogs = self.generator.load_all(self.repo_root)
        self.assertEqual(self.generator.emit_c(catalogs), self.generator.emit_c(catalogs))
        self.assertEqual(self.generator.emit_cpp(catalogs), self.generator.emit_cpp(catalogs))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    CatalogContractTest.repo_root = args.repo_root.resolve()
    CatalogContractTest.generator = load_generator(CatalogContractTest.repo_root)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CatalogContractTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
