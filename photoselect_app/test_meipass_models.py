#!/usr/bin/env python3
"""验证打包后 exe 中的人脸识别模型能否加载（模拟 _MEIPASS 环境）"""
import os
import sys
import tempfile
import zipfile

# 模拟 PyInstaller 解包环境：把 assets 复制到临时 _MEIPASS
EXE = r"E:\photoselect\photoselect_app\dist\PhotoSelect.exe"
print(f"exe 大小: {os.path.getsize(EXE)/1024/1024:.1f} MB")

# 检查引擎能否在无 assets 目录的路径下找到模型（打包后路径在 _MEIPASS）
# 直接测试引擎模型加载逻辑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup_engine as de

# 模拟 _MEIPASS
fake_meipass = tempfile.mkdtemp(prefix="meipass_test_")
import shutil
shutil.copytree(r"E:\photoselect\photoselect_app\assets",
                os.path.join(fake_meipass, "assets"))

# 备份原 ASSETS 路径并指向 _MEIPASS
orig_det = de.FACE_DET_MODEL
orig_rec = de.FACE_REC_MODEL
de.FACE_DET_MODEL = os.path.join(fake_meipass, "assets", "models",
                                 "face_detection_yunet_2023mar.onnx")
de.FACE_REC_MODEL = os.path.join(fake_meipass, "assets", "models",
                                 "mobilefacenet.onnx")

# 重置缓存
de._face_cache = {}
de._face_det = None
de._face_rec = None

# 测试人脸识别
ok = de._load_face_models()
print(f"模型加载: {'✓' if ok else '✗'}")

import os as _os
test_folder = r"C:\Users\nfd\Desktop\testPhotoSelect"
p1 = _os.path.join(test_folder, "DSC_2983.JPG")
p2 = _os.path.join(test_folder, "DSC_2986.JPG")
p3 = _os.path.join(test_folder, "DSC_2994.JPG")
r1 = de.same_person(p1, p2)
r2 = de.same_person(p1, p3)
print(f"2983 vs 2986 (同人, 应 True): {r1}")
print(f"2983 vs 2994 (换人, 应 False): {r2}")
print(f"换人识别: {'✓' if r1 and r1[0] and r2 and not r2[0] else '✗'}")

shutil.rmtree(fake_meipass, ignore_errors=True)
print("DONE")
