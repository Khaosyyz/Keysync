"""PyInstaller build script — produces dist/KeySync/KeySync.exe (onedir).

Only the program (KeySync.exe, _internal, engine) is replaced; user state next
to it (config, data, logs) is never touched. Settings start from code defaults,
so no config file is shipped.

Usage:
  python build.py          # build
  python build.py --clean  # clean build dir first
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
STAGE = ROOT / "build" / "stage"
BUILD = ROOT / "build"
ENTRY = ROOT / "main.py"
ENGINE_EXE = ROOT / "engine" / "llama-funasr-cli.exe"
MODELS = ROOT / "models"
WEB = ROOT / "ui" / "web"

REQUIRED = [ENGINE_EXE, MODELS / "funasr-encoder-f16.gguf",
            MODELS / "qwen3-0.6b-q8_0.gguf", MODELS / "fsmn-vad.gguf"]

HIDDEN_IMPORTS = [
    "comtypes.gen.UIAutomationClient",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        print("ERROR: missing required files:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    app_root = DIST / "KeySync"
    exe = app_root / "KeySync.exe"
    if exe.exists():
        try:
            exe.open("r+b").close()
        except PermissionError:
            print("ERROR: KeySync.exe is running, close it first")
            sys.exit(1)

    if args.clean and BUILD.exists():
        shutil.rmtree(BUILD)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "KeySync",
        "--noconfirm",
        "--windowed",
        "--clean",
        "--distpath", str(STAGE),
        "--add-data", f"{WEB};ui/web",
        *(f"--hidden-import={h}" for h in HIDDEN_IMPORTS),
        "--collect-all", "comtypes",
        str(ENTRY),
    ]
    print("Building:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("BUILD FAILED")
        sys.exit(1)

    built = STAGE / "KeySync"
    app_root.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(app_root / "_internal", ignore_errors=True)
    shutil.copytree(built / "_internal", app_root / "_internal")
    shutil.copy2(built / "KeySync.exe", exe)
    shutil.rmtree(STAGE)

    (app_root / "engine").mkdir(exist_ok=True)
    shutil.copy2(ENGINE_EXE, app_root / "engine" / ENGINE_EXE.name)

    dist_models = app_root / "models"
    dist_models.mkdir(exist_ok=True)
    for src in MODELS.glob("*.gguf"):
        dst = dist_models / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
            print(f"copied model: {src.name}")

    print(f"BUILD SUCCESS: {exe}")


if __name__ == "__main__":
    main()
