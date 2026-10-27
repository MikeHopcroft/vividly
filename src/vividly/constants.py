"""Shared defaults for Vividly."""

from pathlib import Path

DEFAULT_SITE_ROOT = Path("site")
DEFAULT_PORT = 8080

SITE_INDEX_NAME = "index.html"
PROJECT_CONFIG_NAME = "vividly.yaml"

# Identifies projects created with the superseded managed-file layout.
BASELINE_NAME = "vividly-baseline.json"

EXISTING_FILE_LIST_LIMIT = 10

IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "__pycache__"})
IGNORED_SUFFIXES = (".egg-info",)

STARTER_PROJECT_PACKAGE = "vividly.resources"
STARTER_PROJECT_NAME = "starter-project"
RUNTIME_RESOURCE_NAME = "runtime"
REFERENCE_RESOURCE_NAME = "reference"