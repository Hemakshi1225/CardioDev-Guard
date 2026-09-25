"""
core/project_loader.py — Project directory ingestion for CardioDev Guard
=========================================================================

Public API
----------
::

    from core.project_loader import load_project
    request = load_project("/path/to/my_ml_project")

The returned :class:`~core.models.AnalysisRequest` is passed unchanged to
every analyzer.  All discovered file paths are **absolute**.

Ignored directories
-------------------
The following directory names are skipped entirely during the tree walk:

* ``.git``
* ``__pycache__``
* ``.venv``
* ``node_modules``

File categorisation
--------------------
Files are placed into exactly one category based on their extension and
(for Python files) their filename pattern:

============  =====================================================
Field         Criteria
============  =====================================================
model_files   ``.pkl``, ``.h5``, ``.pt``, ``.joblib``, ``.onnx``
data_files    ``.csv``, ``.json``, ``.parquet``, ``.xlsx``
test_files    ``.py`` whose name matches ``test_*.py`` or ``*_test.py``
source_files  all other ``.py`` files
doc_files     ``.md``, ``.txt``, ``.rst``
============  =====================================================

Files that match none of the above are silently ignored — they are not
relevant for ML project analysis.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch

from core.models import AnalysisRequest, ProjectInput


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
})

_MODEL_EXTS: frozenset[str] = frozenset({".pkl", ".h5", ".pt", ".joblib", ".onnx"})
_DATA_EXTS: frozenset[str] = frozenset({".csv", ".json", ".parquet", ".xlsx"})
_DOC_EXTS: frozenset[str] = frozenset({".md", ".txt", ".rst"})


def _is_test_file(filename: str) -> bool:
    """Return ``True`` if *filename* follows a test-file naming convention.

    Recognised patterns:

    * ``test_*.py``  — pytest-style prefix
    * ``*_test.py``  — suffix style
    """
    return fnmatch(filename, "test_*.py") or fnmatch(filename, "*_test.py")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_project(path: str) -> AnalysisRequest:
    """Walk *path* and return a fully populated :class:`~core.models.AnalysisRequest`.

    Parameters
    ----------
    path:
        Absolute or relative path to the root directory of the ML project
        being analysed.

    Returns
    -------
    AnalysisRequest
        Contains the original :class:`~core.models.ProjectInput` plus
        categorised lists of absolute file paths discovered inside *path*.

    Raises
    ------
    ValueError
        If *path* does not exist or is not a directory.

    Examples
    --------
    ::

        from core.project_loader import load_project

        request = load_project("./my_ml_project")
        print(request.model_files)   # ['/abs/path/model.pkl', ...]
        print(request.data_files)    # ['/abs/path/train.csv', ...]
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        raise ValueError(
            f"Project path does not exist: {abs_path!r}"
        )
    if not os.path.isdir(abs_path):
        raise ValueError(
            f"Project path is not a directory: {abs_path!r}"
        )

    project_input = ProjectInput(
        path=abs_path,
        name=os.path.basename(abs_path),
    )

    model_files: list[str] = []
    data_files: list[str] = []
    test_files: list[str] = []
    source_files: list[str] = []
    doc_files: list[str] = []

    for dirpath, dirnames, filenames in os.walk(abs_path):
        # Prune ignored directories in-place so os.walk does not descend into them
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            abs_file = os.path.join(dirpath, filename)

            if ext == ".py":
                if _is_test_file(filename):
                    test_files.append(abs_file)
                else:
                    source_files.append(abs_file)
            elif ext in _MODEL_EXTS:
                model_files.append(abs_file)
            elif ext in _DATA_EXTS:
                data_files.append(abs_file)
            elif ext in _DOC_EXTS:
                doc_files.append(abs_file)
            # Files matching none of the above are intentionally ignored

    return AnalysisRequest(
        project_input=project_input,
        model_files=model_files,
        data_files=data_files,
        test_files=test_files,
        source_files=source_files,
        doc_files=doc_files,
    )
