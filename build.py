"""PyInstaller build script.

  python build.py              # dist/KeySync/ (onedir app)
  python build.py --installer  # also dist/KeySync-Setup-<version>.exe
  python build.py --clean      # clean the build dir first

Only the program (KeySync.exe, _internal, engine) is replaced in dist/KeySync;
user state next to it (config, data, logs, models) is never touched. Local
models are seeded there for testing; the installer never ships them, the app
downloads them on first run. The icon is rendered from ui/web/logo.svg by Edge.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import winreg
import zipfile
from pathlib import Path

from PIL import Image

from installer import product

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
STAGE = BUILD / "stage"
APP_ROOT = DIST / product.NAME
ENGINE_EXE = ROOT / "engine" / "llama-funasr-cli.exe"
MODELS = ROOT / "models"
WEB = ROOT / "ui" / "web"
LOGO = WEB / "logo.svg"
ICON = BUILD / f"{product.NAME}.ico"
ICON_SIZES = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
EDGE_APP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
SETUP_EXE = DIST / f"{product.NAME}-Setup-{product.VERSION}.exe"

HIDDEN_IMPORTS = [
    "comtypes.gen.UIAutomationClient",
]


def pyinstaller(name: str, entry: Path, *options: str):
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", name, "--noconfirm", "--windowed", "--clean",
        "--icon", str(ICON),
        "--specpath", str(BUILD), "--workpath", str(BUILD / "work"), "--distpath", str(STAGE),
        *options, str(entry),
    ]
    print("Building:", " ".join(cmd))
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        print(f"BUILD FAILED: {name}")
        sys.exit(1)


def render_icon():
    edge = winreg.QueryValue(winreg.HKEY_LOCAL_MACHINE, EDGE_APP_PATH)
    size = ICON_SIZES[-1][0]
    with tempfile.TemporaryDirectory() as tmp:
        page, shot = Path(tmp) / "icon.html", Path(tmp) / "icon.png"
        page.write_text(f'<style>html,body{{margin:0;background:transparent}}</style>'
                        f'<img src="{LOGO.as_uri()}" width="{size}" height="{size}" style="display:block">',
                        encoding="utf-8")
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--default-background-color=00000000",
                        "--virtual-time-budget=2000", f"--window-size={size},{size}",
                        f"--screenshot={shot}", page.as_uri()], check=True, capture_output=True)
        Image.open(shot).save(ICON, sizes=ICON_SIZES)


def build_app():
    pyinstaller(product.NAME, ROOT / "main.py",
                "--add-data", f"{WEB};ui/web",
                *(f"--hidden-import={h}" for h in HIDDEN_IMPORTS),
                "--collect-all", "comtypes")
    built = STAGE / product.NAME
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(APP_ROOT / "_internal", ignore_errors=True)
    shutil.copytree(built / "_internal", APP_ROOT / "_internal")
    shutil.copy2(built / product.APP_EXE, APP_ROOT / product.APP_EXE)
    (APP_ROOT / "engine").mkdir(exist_ok=True)
    shutil.copy2(ENGINE_EXE, APP_ROOT / "engine" / ENGINE_EXE.name)


def seed_models():
    target = APP_ROOT / "models"
    for src in MODELS.glob("*.gguf"):
        dst = target / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            target.mkdir(exist_ok=True)
            shutil.copy2(src, dst)
            print(f"copied model: {src.name}")


def build_installer():
    pyinstaller("Uninstall", ROOT / "installer" / "uninstall.py", "--onefile", "--paths", str(ROOT))
    payload = BUILD / product.PAYLOAD
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(STAGE / product.UNINSTALL_EXE, product.UNINSTALL_EXE)
        for name in product.APP_FILES:
            src = APP_ROOT / name
            for path in [src] if src.is_file() else (p for p in src.rglob("*") if p.is_file()):
                z.write(path, path.relative_to(APP_ROOT))
    pyinstaller(SETUP_EXE.stem, ROOT / "installer" / "install.py", "--onefile", "--paths", str(ROOT),
                "--add-data", f"{payload};.", "--add-data", f"{WEB};ui/web")
    shutil.copy2(STAGE / SETUP_EXE.name, SETUP_EXE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--installer", action="store_true")
    args = parser.parse_args()

    if not ENGINE_EXE.exists():
        print(f"ERROR: missing required file: {ENGINE_EXE}")
        sys.exit(1)
    if product.is_running(APP_ROOT):
        print(f"ERROR: {product.APP_EXE} is running, close it first")
        sys.exit(1)

    if args.clean and BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(exist_ok=True)
    render_icon()
    build_app()
    seed_models()
    if args.installer:
        build_installer()
    shutil.rmtree(STAGE)
    print(f"BUILD SUCCESS: {SETUP_EXE if args.installer else APP_ROOT / product.APP_EXE}")


if __name__ == "__main__":
    main()
