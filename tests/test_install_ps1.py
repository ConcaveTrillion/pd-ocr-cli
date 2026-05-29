from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _write_fake_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_install_ps1_piped_mode_is_self_contained_and_uses_release_wheel(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"

    _write_fake_exe(
        bin_dir / "uv",
        f"""#!/bin/sh
printf '%s\\n' "$@" > {uv_log}
exit 0
""",
    )
    _write_fake_exe(
        bin_dir / "nvidia-smi",
        """#!/bin/sh
printf '%s\\n' 'CUDA Version                          : 12.4'
exit 0
""",
    )

    script = (REPO / "install.ps1").read_text(encoding="utf-8")
    escaped_script = script.replace("'@", "' + \"@\" + '")
    harness = tmp_path / "run.ps1"
    harness.write_text(
        f"""
$ErrorActionPreference = "Stop"
function Invoke-RestMethod {{
  param([string]$Uri)
  if ($Uri -like "*api.github.com/repos/pdomain/pdomain-ocr-cli/releases/latest*") {{
    return [pscustomobject]@{{
      tag_name = "v9.9.9"
      assets = @([pscustomobject]@{{
        name = "pdomain_ocr_cli-9.9.9-py3-none-any.whl"
        browser_download_url = "https://example.invalid/pdomain_ocr_cli-9.9.9-py3-none-any.whl"
      }})
    }}
  }}
  throw "unexpected Invoke-RestMethod: $Uri"
}}
function Invoke-WebRequest {{
  param([string]$Uri, [string]$OutFile)
  if ($Uri -ne "https://example.invalid/pdomain_ocr_cli-9.9.9-py3-none-any.whl") {{
    throw "unexpected Invoke-WebRequest: $Uri"
  }}
  Set-Content -Path $OutFile -Value "fake wheel"
}}
function irm {{
  param([string]$Uri)
  throw "unexpected irm: $Uri"
}}
$InstallerText = @'
{escaped_script}
'@
Invoke-Expression $InstallerText
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["PD_OCR_INSTALL_PYTHON"] = "3.12"
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    args = uv_log.read_text(encoding="utf-8")
    assert "--python\n3.12" in args
    assert "--extra-index-url" in args
    assert "https://pdomain.github.io/pdomain-index-pip/simple/" in args
    assert "pdomain_ocr_cli-9.9.9-py3-none-any.whl" in args
    assert "git+https://github.com/pdomain/pdomain-ocr-cli" not in args
