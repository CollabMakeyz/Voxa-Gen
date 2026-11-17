import os
from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
block_cipher = None

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "docs"), "docs"),
    (os.path.join(ROOT, "README.md"), "."),
    (os.path.join(ROOT, "LICENSE"), "."),
]
binaries = collect_dynamic_libs("soundfile") + collect_dynamic_libs("soxr")

excludes = [
    "tkinter", "matplotlib", "IPython", "pytest", "_pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtHttpServer",
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pyworld", "parselmouth", "soxr", "soundfile", "pkg_resources",
                   "scipy.signal", "scipy.ndimage", "PySide6.QtSvg", "PySide6.QtMultimedia"],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VoxaGEN",
    icon=os.path.join(ROOT, "assets", "icons", "voxagen.ico"),
    console=False,
    upx=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="VoxaGEN")
