from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_install_sh_uses_release_wheel_and_pdomain_index(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"

    (bin_dir / "uv").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {uv_log}\nexit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "uv").chmod(0o755)
    (bin_dir / "curl").write_text(
        """#!/bin/sh
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then shift; out="$1"; fi
  shift || true
done
if [ -n "$out" ]; then
  printf 'fake wheel' > "$out"
else
  cat <<'JSON'
{"tag_name":"v9.9.9","assets":[{"browser_download_url":"https://example.invalid/pdomain_ocr_cli-9.9.9-py3-none-any.whl"}]}
JSON
fi
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").chmod(0o755)
    (bin_dir / "gh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    (bin_dir / "nvidia-smi").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "nvidia-smi").chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["sh", str(REPO / "install.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    args = uv_log.read_text(encoding="utf-8")
    assert "--extra-index-url" in args
    assert "https://pdomain.github.io/pdomain-index-pip/simple/" in args
    assert "pdomain_ocr_cli-9.9.9-py3-none-any.whl" in args
    assert "git+https://github.com/pdomain/pdomain-ocr-cli" not in args
