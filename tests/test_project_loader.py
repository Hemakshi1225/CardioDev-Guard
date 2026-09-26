"""
tests/test_project_loader.py — Unit tests for core/project_loader.py

Covers:
- Valid project directory returns correct AnalysisRequest
- Non-existent path raises ValueError
- File-path raises ValueError (not a directory)
- Empty directory returns empty file lists
- Mixed file types are categorised correctly
- test_*.py / *_test.py separated from source_files
- Ignored directories (.git, __pycache__, .venv, node_modules)
- All returned paths are absolute
- Relative paths are resolved to absolute
"""

import os
import tempfile

import pytest

from core.project_loader import load_project


def _touch(path: str) -> None:
    """Create an empty file, making any intermediate directories."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestInvalidPaths:
    def test_nonexistent_path_raises_value_error(self):
        with pytest.raises(ValueError, match="does not exist"):
            load_project("/nonexistent/path/that/cannot/exist/xyz123")

    def test_file_path_raises_value_error(self):
        with tempfile.NamedTemporaryFile(suffix=".py") as f:
            with pytest.raises(ValueError, match="not a directory"):
                load_project(f.name)


# ---------------------------------------------------------------------------
# Empty directory
# ---------------------------------------------------------------------------

class TestEmptyDirectory:
    def test_empty_dir_returns_empty_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = load_project(tmp)
            assert req.model_files   == []
            assert req.data_files    == []
            assert req.test_files    == []
            assert req.source_files  == []
            assert req.doc_files     == []

    def test_project_input_name_is_directory_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = load_project(tmp)
            assert req.project_input.name == os.path.basename(tmp)

    def test_project_input_path_is_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = load_project(tmp)
            assert os.path.isabs(req.project_input.path)


# ---------------------------------------------------------------------------
# File categorisation
# ---------------------------------------------------------------------------

class TestFileCategorisation:
    def test_model_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ext in (".pkl", ".h5", ".pt", ".joblib", ".onnx"):
                _touch(os.path.join(tmp, f"model{ext}"))
            req = load_project(tmp)
            assert len(req.model_files) == 5

    def test_data_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ext in (".csv", ".json", ".parquet", ".xlsx"):
                _touch(os.path.join(tmp, f"data{ext}"))
            req = load_project(tmp)
            assert len(req.data_files) == 4

    def test_doc_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ext in (".md", ".txt", ".rst"):
                _touch(os.path.join(tmp, f"doc{ext}"))
            req = load_project(tmp)
            assert len(req.doc_files) == 3

    def test_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "main.py"))
            _touch(os.path.join(tmp, "utils.py"))
            req = load_project(tmp)
            assert len(req.source_files) == 2

    def test_unknown_extensions_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "image.png"))
            _touch(os.path.join(tmp, "script.sh"))
            _touch(os.path.join(tmp, "archive.zip"))
            req = load_project(tmp)
            assert req.model_files  == []
            assert req.data_files   == []
            assert req.source_files == []
            assert req.doc_files    == []

    def test_mixed_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "model.pkl"))
            _touch(os.path.join(tmp, "data", "train.csv"))
            _touch(os.path.join(tmp, "tests", "test_model.py"))
            _touch(os.path.join(tmp, "tests", "model_test.py"))
            _touch(os.path.join(tmp, "src", "train.py"))
            _touch(os.path.join(tmp, "README.md"))
            req = load_project(tmp)
            assert len(req.model_files)  == 1
            assert len(req.data_files)   == 1
            assert len(req.test_files)   == 2
            assert len(req.source_files) == 1
            assert len(req.doc_files)    == 1


# ---------------------------------------------------------------------------
# Test file separation
# ---------------------------------------------------------------------------

class TestTestFileSeparation:
    def test_test_prefix_goes_to_test_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "test_model.py"))
            req = load_project(tmp)
            assert len(req.test_files)   == 1
            assert len(req.source_files) == 0

    def test_test_suffix_goes_to_test_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "model_test.py"))
            req = load_project(tmp)
            assert len(req.test_files)   == 1
            assert len(req.source_files) == 0

    def test_regular_py_goes_to_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "train.py"))
            req = load_project(tmp)
            assert len(req.source_files) == 1
            assert len(req.test_files)   == 0

    def test_test_and_source_sets_are_disjoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "test_a.py"))
            _touch(os.path.join(tmp, "b_test.py"))
            _touch(os.path.join(tmp, "main.py"))
            req = load_project(tmp)
            assert set(req.test_files).isdisjoint(set(req.source_files))


# ---------------------------------------------------------------------------
# Ignored directories
# ---------------------------------------------------------------------------

class TestIgnoredDirectories:
    def _setup_ignored(self, tmp: str) -> None:
        for ignored in (".git", "__pycache__", ".venv", "node_modules"):
            _touch(os.path.join(tmp, ignored, "should_be_ignored.py"))
        _touch(os.path.join(tmp, "real_src", "main.py"))

    def test_ignored_dirs_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._setup_ignored(tmp)
            req = load_project(tmp)
            assert len(req.source_files) == 1
            assert req.source_files[0].endswith("main.py")

    def test_git_dir_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, ".git", "config.py"))
            req = load_project(tmp)
            assert req.source_files == []

    def test_pycache_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "__pycache__", "mod.cpython-310.pyc"))
            req = load_project(tmp)
            assert req.source_files == []

    def test_venv_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, ".venv", "site.py"))
            req = load_project(tmp)
            assert req.source_files == []

    def test_node_modules_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "node_modules", "index.js"))
            req = load_project(tmp)
            assert req.source_files == []


# ---------------------------------------------------------------------------
# Absolute paths
# ---------------------------------------------------------------------------

class TestAbsolutePaths:
    def test_all_paths_are_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "model.pkl"))
            _touch(os.path.join(tmp, "data.csv"))
            _touch(os.path.join(tmp, "test_x.py"))
            _touch(os.path.join(tmp, "main.py"))
            _touch(os.path.join(tmp, "README.md"))
            req = load_project(tmp)
            all_paths = (
                req.model_files + req.data_files + req.test_files
                + req.source_files + req.doc_files
            )
            for p in all_paths:
                assert os.path.isabs(p), f"Not absolute: {p}"

    def test_relative_path_resolved_to_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "a.csv"))
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                req = load_project(".")
                assert os.path.isabs(req.project_input.path)
                assert len(req.data_files) == 1
            finally:
                os.chdir(original_cwd)
