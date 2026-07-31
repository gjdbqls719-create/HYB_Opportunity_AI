from pathlib import Path

PROJECT_ROOT = Path.cwd()

IGNORE_DIRS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".coverage",
    "coverage",
    "htmlcov",
    "build",
    "dist",
    "node_modules",
}

IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

CODE_EXTENSIONS = {
    ".py",
}

DOCUMENT_EXTENSIONS = {
    ".md",
}

CONFIG_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
}

ENTRY_POINT_FILES = {
    "main.py",
    "manage.py",
    "run.py",
}

ENTRY_POINT_SUFFIXES = (
    "_cli.py",
    "_main.py",
)

ROOT_SECTIONS = (
    "app",
    "ai",
    "ai_docs",
    "collectors",
    "config",
    "context",
    "data",
    "database",
    "docs",
    "engine",
    "market_data",
    "marketplaces",
    "presentation",
    "scripts",
    "services",
    "storage",
    "templates",
    "tests",
)

DOCUMENT_PRIORITY = (
    "README.md",
    "START_HERE.md",
    "DOCUMENT_INDEX.md",
    "PROJECT_STRUCTURE.md",
    "AGENTS.md",
)

DOMAIN_KEYWORDS = {
    "change": (
        "change",
        "snapshot",
        "history",
    ),
    "canonical": (
        "canonical",
        "identity",
        "normalization",
    ),
    "pricing": (
        "price",
        "pricing",
        "cost",
    ),
    "opportunity": (
        "opportunity",
        "profit",
        "score",
    ),
    "matching": (
        "match",
        "matching",
        "similarity",
    ),
    "discovery": (
        "discover",
        "discovery",
        "finder",
    ),
    "storage": (
        "repository",
        "storage",
        "database",
    ),
    "api": (
        "api",
        "client",
        "adapter",
    ),
}