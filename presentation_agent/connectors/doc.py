from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector
from presentation_agent.connectors.docx import DocxConnector


class DocConnector(SuffixConnector):
    """Handle legacy binary Word ``.doc`` files via LibreOffice conversion."""

    name = "doc_reader"
    suffixes = (".doc",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        converted = convert_doc_to_docx(path)
        result = DocxConnector().load(converted, context)
        result["source_path"] = str(path)
        result["source_type"] = "doc"
        result["converted_docx_path"] = str(converted)
        result["conversion_note"] = (
            "Legacy .doc converted to .docx with LibreOffice before text/image extraction."
        )
        return result


def convert_doc_to_docx(path: Path) -> Path:
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice/soffice not found; cannot convert legacy .doc input."
        )

    output_dir = _conversion_dir(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = output_dir / "libreoffice-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["HOME"] = str(profile_dir)
    command = [
        soffice,
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--invisible",
        "--headless",
        "--norestore",
        "--convert-to",
        "docx",
        "--outdir",
        str(output_dir),
        str(path),
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    expected = output_dir / f"{path.stem}.docx"
    if proc.returncode != 0 or not expected.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"soffice exited {proc.returncode}")
    return expected


def _conversion_dir(path: Path) -> Path:
    stat = path.stat()
    key = f"{path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "presentation-agent-doc-conversions" / digest


def _find_soffice() -> str | None:
    env_path = os.environ.get("PRESENTATION_AGENT_SOFFICE")
    candidates = [
        env_path,
        shutil.which("soffice"),
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None
