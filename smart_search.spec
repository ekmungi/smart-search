# PyInstaller spec for smart-search desktop app bundle.
#
# Builds a one-directory distribution with all dependencies.
# Usage: pyinstaller smart_search.spec
# Output: dist/smart-search/smart-search.exe
#
# The ONNX embedding model is NOT bundled -- it downloads on first run
# via HuggingFace cache (~250MB). This keeps the installer small.

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Collect native extensions and data files ─────────────────────────
datas = []
binaries = []
hiddenimports = []

# Packages with native C/C++ extensions or bundled data files
_collect_packages = [
    "lancedb",
    "pyarrow",
    "onnxruntime",
    "sentence_transformers",
    "transformers",
    "tokenizers",
    "markitdown",
]

for pkg in _collect_packages:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# ── Hidden imports: lazy-loaded modules inside functions ─────────────
# server.py and http.py defer these imports for fast MCP startup.
# PyInstaller's static analysis cannot detect them.
hiddenimports += [
    # smart-search internal modules (lazy-loaded)
    "smart_search.embedder",
    "smart_search.search",
    "smart_search.store",
    "smart_search.indexer",
    "smart_search.markdown_chunker",
    "smart_search.markitdown_parser",
    "smart_search.watcher",
    "smart_search.ephemeral_registry",
    "smart_search.ephemeral_store",
    "smart_search.reader",
    "smart_search.http",
    "smart_search.http_routes",
    "smart_search.http_models",
    "smart_search.server",
    # FastAPI / uvicorn internals (dynamic module loading)
    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "starlette",
    "starlette.middleware",
    "starlette.middleware.cors",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # ML/embedding stack
    "einops",
    "numpy",
    "scipy",
    "sklearn",
    "sklearn.utils",
    # File watching
    "watchdog",
    "watchdog.observers",
    "watchdog.observers.polling",
    # FastMCP (MCP server framework)
    "fastmcp",
    # Pydantic
    "pydantic",
    "pydantic_settings",
    # Other deps
    "tqdm",
    "httptools",
    "websockets",
]

# ── Exclude unnecessary packages to reduce bundle size ───────────────
excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "docutils",
    # markitdown pulls these in but we only use document conversion
    "speech_recognition",
    "pydub",
    "audioop",
]

# ── Analysis ─────────────────────────────────────────────────────────
a = Analysis(
    ["src/smart_search/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Bundle ───────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="smart-search",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="smart-search",
)
