#!/usr/bin/env python3
"""修复后回归测试：验证分析完成自动显示照片 + 切换组不卡死"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from main import MainWindow, GroupPanel
import time

app = QApplication([])
win = MainWindow()
win.folder_label.setText(r"C:\Users\nfd\Desktop\testPhotoSelect")

for mode_name, mode in [("严格", "strict"), ("同主体", "subject")]:
    t0 = time.time()
    win._set_mode(mode)
    win.result = None
    win._start_analysis()
    deadline = time.time() + 400
    while (win.result is None or win.result.mode != mode) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    assert win.result is not None, f"{mode_name}模式分析失败"
    print(f"[{mode_name}] 分析完成 {time.time()-t0:.1f}s: "
          f"{len(win.result.photos)}张 {len(win.result.groups)}组", flush=True)

    # 验证分析完成自动显示第一组
    for _ in range(10):
        app.processEvents(); time.sleep(0.03)
    panel = win.right_layout.itemAt(0).widget()
    assert isinstance(panel, GroupPanel), "分析完成后未自动显示 GroupPanel!"
    # 验证照片 pixmap 已加载
    loaded = 0
    for c in panel.cards:
        pm = c.img_label.pixmap()
        if pm is not None and not pm.isNull():
            loaded += 1
    print(f"[{mode_name}] 自动显示组0: {len(panel.cards)}卡片, "
          f"{loaded}张已显示照片", flush=True)
    assert loaded > 0, "照片未显示!"

    # 验证切换组不卡死
    t1 = time.time()
    for i in range(min(len(win.result.groups), 3)):
        win._show_group(i)
        for _ in range(5):
            app.processEvents(); time.sleep(0.02)
    print(f"[{mode_name}] 切换3组耗时 {time.time()-t1:.1f}s", flush=True)

    # 验证点击卡片不卡死
    t2 = time.time()
    panel = win.right_layout.itemAt(0).widget()
    if panel.cards:
        panel.cards[0].toggle()
        app.processEvents()
    print(f"[{mode_name}] 点击卡片耗时 {time.time()-t2:.3f}s", flush=True)

print("\n=== 回归测试全部通过 ===")
