# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — PhotoSelect v2.9.1（含离线人脸识别模型 + rawpy RAW 支持）

import rawpy
import os
_rawpy_dir = os.path.dirname(rawpy.__file__)
_rawpy_bins = [
    (os.path.join(_rawpy_dir, f), 'rawpy')
    for f in os.listdir(_rawpy_dir)
    if f.endswith(('.pyd', '.dll'))
]
# pillow_heif C 扩展 + libheif DLL（不在 pillow_heif 子目录里，需手动加）
import site
_sp_dir = site.getsitepackages()[0]
_heif_bins = []
for _f in os.listdir(_sp_dir):
    if _f.startswith('_pillow_heif') and _f.endswith('.pyd'):
        _heif_bins.append((os.path.join(_sp_dir, _f), '.'))
    elif _f.startswith('libheif') and _f.endswith('.dll'):
        _heif_bins.append((os.path.join(_sp_dir, _f), '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_rawpy_bins + _heif_bins,
    datas=[
        ('assets/icon_256.png', 'assets'),
        ('assets/mode_landscape.png', 'assets'),
        ('assets/mode_portrait.png', 'assets'),
        ('assets/sounds/success.wav', 'assets/sounds'),
        ('assets/models/face_detection_yunet_2023mar.onnx', 'assets/models'),
        ('assets/models/mobilefacenet.onnx', 'assets/models'),
    ],
    hiddenimports=['cv2', 'numpy', 'rawpy', 'PySide6.QtMultimedia', 'pillow_heif'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PhotoSelect',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
