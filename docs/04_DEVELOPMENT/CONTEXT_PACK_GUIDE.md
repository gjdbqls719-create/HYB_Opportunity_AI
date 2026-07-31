# HYB Context Pack Guide

## Purpose

Context Packs preserve the minimum project handoff context and a filtered
repository snapshot for review or a new AI collaboration session.

## Create

Run from the repository root:

```powershell
.\scripts\create_context_pack.ps1
```

If the local execution policy blocks direct script execution, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\create_context_pack.ps1
```

The command first removes the previous generated Context Pack artifacts, then
creates:

- `context/HYB_QUICK_CONTEXT.zip`
- `context/HYB_FULL_CONTEXT.zip`
- `context/CONTEXT_MANIFEST.md`

Quick Context contains the six current-context documents recorded in
`AI_DEVELOPMENT_LOG.md`. Full Context contains the repository while excluding
`.git`, `.venv`, `__pycache__`, `.pytest_cache`, `htmlcov`, Python bytecode,
local databases, local environment files, and existing `context/*.zip` files.

## Clean

```powershell
.\scripts\cleanup_context_pack.ps1
```

Cleanup removes only the two generated Context ZIPs and
`context/CONTEXT_MANIFEST.md`. The `context` directory and `.gitkeep` remain.

Generated Context Pack artifacts are ignored by Git.
