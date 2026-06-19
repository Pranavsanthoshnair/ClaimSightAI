"""Dependency verification and startup diagnostics.

Provides:
    - check_dependencies() — verifies all critical runtime packages are importable
    - startup_diagnostics() — dumps Python/package version info for log
    - DependencyReport — structured results of the dependency check
"""

from __future__ import annotations

import importlib
import logging
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required packages: (import_name, pip_package_name, min_version, purpose)
# ---------------------------------------------------------------------------
_REQUIRED_PACKAGES: list[tuple[str, str, str, str]] = [
    ("pydantic", "pydantic", "2.7.0", "Pydantic models and settings"),
    ("pandas", "pandas", "2.2.0", "CSV loading and data frames"),
    ("PIL", "pillow", "10.0.0", "Image loading and resizing"),
    ("numpy", "numpy", "1.26.0", "Array operations"),
    ("streamlit", "streamlit", "1.35.0", "Web application UI"),
    ("dotenv", "python-dotenv", "0.19.0", "Load .env files"),
    ("requests", "requests", "2.31.0", "HTTP client for OpenRouter"),
]

_OPTIONAL_PACKAGES: list[tuple[str, str, str, str]] = [
    # No optional vendor SDKs required — OpenRouter and Groq use requests (HTTP).
]


@dataclass
class PackageInfo:
    name: str
    pip_name: str
    version: str = ""
    min_version: str = ""
    installed: bool = False
    meets_minimum: bool = False
    purpose: str = ""


@dataclass
class DependencyReport:
    timestamp: str = ""
    python_version: str = ""
    platform: str = ""
    packages: list[PackageInfo] = field(default_factory=list)
    all_required_met: bool = False
    missing_required: list[str] = field(default_factory=list)
    version_mismatches: list[str] = field(default_factory=list)


def _get_version(import_name: str, pip_name: str = "") -> str:
    """Try to get the version string of an installed package.

    Uses ``importlib.metadata`` as the primary source (works for all
    properly installed packages). Falls back to ``__version__`` or
    other module-level attributes.
    """
    name = pip_name or import_name
    try:
        from importlib.metadata import version as _meta_version
        return _meta_version(name)
    except Exception:
        pass

    try:
        mod = importlib.import_module(import_name)
        raw = getattr(mod, "__version__", None)
        if raw is not None:
            if isinstance(raw, str):
                return raw
            return str(raw)
        v = getattr(mod, "version", None)
        if v is not None:
            if isinstance(v, str):
                return v
            if not callable(v):
                cv = getattr(v, "VERSION", None)
                if cv:
                    return str(cv)
        if import_name == "PIL":
            return getattr(mod, "VERSION", "")
        return ""
    except Exception:
        return ""


def _parse_version(ver: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple."""
    parts = []
    for part in ver.split(".")[:3]:
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_dependencies() -> DependencyReport:
    """Check all required and optional packages.

    Returns a DependencyReport with per-package status and summary fields.
    Never raises — all import errors are caught and recorded.
    """
    report = DependencyReport(
        timestamp=datetime.now(tz=UTC).isoformat(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=sys.platform,
    )
    missing: list[str] = []
    mismatches: list[str] = []

    all_entries = _REQUIRED_PACKAGES + _OPTIONAL_PACKAGES
    for import_name, pip_name, min_ver, purpose in all_entries:
        info = PackageInfo(
            name=import_name,
            pip_name=pip_name,
            min_version=min_ver,
            purpose=purpose,
        )
        try:
            importlib.import_module(import_name)
            info.installed = True
            version = _get_version(import_name, pip_name=pip_name)
            info.version = version
            if version:
                actual = _parse_version(version)
                required = _parse_version(min_ver)
                info.meets_minimum = actual >= required
                if not info.meets_minimum:
                    mismatches.append(
                        f"{pip_name} {version} installed, requires >={min_ver}"
                    )
            else:
                info.meets_minimum = False
                mismatches.append(f"{pip_name} installed but version unknown")
        except ModuleNotFoundError:
            info.installed = False
            info.meets_minimum = False
            if (import_name, pip_name, min_ver, purpose) in _REQUIRED_PACKAGES:
                missing.append(pip_name)

        report.packages.append(info)

    report.missing_required = missing
    report.version_mismatches = mismatches
    report.all_required_met = len(missing) == 0 and len(mismatches) == 0
    return report


def startup_diagnostics(
    repo_root: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    """Collect startup diagnostics into a structured dictionary.

    Safe to call at module level — catches all exceptions.
    """
    info: dict[str, object] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": sys.platform,
        "platform_arch": platform.machine(),
        "hostname": platform.node(),
        "cwd": str(Path.cwd()),
        "argv": sys.argv,
        "repo_root": str(repo_root) if repo_root else None,
        "config_path": str(config_path) if config_path else None,
        "env_keys": sorted(
            k for k in os.environ if not k.lower().endswith(("key", "secret", "token", "password"))
        ),
    }

    dep_report = check_dependencies()
    info["dependencies"] = {
        "all_required_met": dep_report.all_required_met,
        "missing_required": dep_report.missing_required,
        "version_mismatches": dep_report.version_mismatches,
        "packages": [
            {
                "name": p.pip_name,
                "version": p.version,
                "installed": p.installed,
                "meets_minimum": p.meets_minimum,
            }
            for p in dep_report.packages
        ],
    }

    try:
        import streamlit
        info["streamlit_version"] = streamlit.__version__
    except Exception:
        info["streamlit_version"] = "not_installed"

    try:
        import pydantic
        info["pydantic_version"] = pydantic.__version__
    except Exception:
        info["pydantic_version"] = "not_installed"

    return info


def write_deployment_log(
    log_dir: Path,
    diagnostics: dict[str, object],
) -> None:
    """Append a startup entry to logs/deployment.log.

    Format: JSONL — one JSON object per startup.
    Safe to call even when the directory does not exist.
    """
    import json

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "deployment.log"
        deps_raw = diagnostics.get("dependencies", {})
        deps: dict[str, Any] = deps_raw if isinstance(deps_raw, dict) else {}
        entry = {
            "event": "startup",
            "python_version": diagnostics.get("python_version", ""),
            "streamlit_version": diagnostics.get("streamlit_version", ""),
            "pydantic_version": diagnostics.get("pydantic_version", ""),
            "platform": diagnostics.get("platform", ""),
            "all_required_met": deps.get("all_required_met", False),
            "missing_required": deps.get("missing_required", []),
            "provider": "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "not_set",
            "vision_model": os.environ.get("OPENROUTER_MODEL_PRIMARY", "not_set"),
            "deployment_mode": "streamlit_cloud" if os.environ.get("STREAMLIT_RUN") else "local",
            "timestamp": diagnostics.get("timestamp", ""),
        }
        with log_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:
        logger.exception("Failed to write deployment log")


def format_dependency_error_html(missing: list[str]) -> str:
    """Return a professional HTML error card for missing dependencies."""
    pkg_list = "".join(
        f'<div style="font-size:0.9rem;color:#EF4444;padding:4px 0;">'
        f'  ✗ <code style="background:#1F2937;padding:2px 8px;border-radius:4px;">{pkg}</code>'
        f"</div>"
        for pkg in missing
    )
    return f"""
    <div style="background:#111827;border:2px solid #7F1D1D;border-radius:16px;
                padding:2.5rem;margin:2rem auto;max-width:600px;
                box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <div style="font-size:2.5rem;margin-bottom:1rem;text-align:center;">⚠️</div>
      <h2 style="color:#FCA5A5;text-align:center;margin:0 0 0.5rem;font-size:1.3rem;">
        Dependency Error
      </h2>
      <p style="color:#94A3B8;text-align:center;font-size:0.9rem;margin-bottom:1.5rem;">
        The following required packages could not be loaded:
      </p>
      <div style="margin-bottom:1.5rem;">{pkg_list}</div>
      <div style="background:#1F2937;border-radius:10px;padding:1rem;">
        <p style="color:#94A3B8;font-size:0.8rem;margin:0 0 0.5rem;">
          <strong style="color:#E2E8F0;">Recommended fix:</strong>
        </p>
        <code style="display:block;background:#0B0F19;color:#10B981;padding:0.75rem;
                      border-radius:8px;font-size:0.85rem;">
          pip install {" ".join(missing)}
        </code>
      </div>
      <p style="color:#6B7280;font-size:0.75rem;text-align:center;margin-top:1.5rem;">
        Add missing packages to <code>requirements.txt</code> and redeploy.
      </p>
    </div>
    """
