"""Compile portal CSS with the pinned upstream standalone Tailwind compiler."""

import hashlib
import platform
import subprocess
from pathlib import Path
from urllib.request import urlretrieve


def main():
    root = Path(__file__).resolve().parents[1]
    version = "3.4.17"
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    architecture = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    asset = f"tailwindcss-{system}-{architecture}" + (".exe" if system == "windows" else "")
    compiler = root / ".pytest_cache" / "tools" / f"{version}-{asset}"
    compiler.parent.mkdir(parents=True, exist_ok=True)
    if not compiler.exists():
        urlretrieve(f"https://github.com/tailwindlabs/tailwindcss/releases/download/v{version}/{asset}", compiler)
        if system != "windows":
            compiler.chmod(0o755)
    output = root / "src" / "static" / "portal.css"
    output.parent.mkdir(exist_ok=True)
    subprocess.run([
        str(compiler), "-c", "tailwind.config.cjs", "-i", "src/styles/portal.css",
        "-o", "src/static/portal.css", "--minify",
    ], cwd=root, check=True)
    print("Compiler SHA256:", hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()