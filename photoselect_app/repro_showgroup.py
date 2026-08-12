#!/usr/bin/env python3
"""复现：分析完成后 _show_group 是否卡死/不显示照片"""
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
win._set_mode("strict")
win.result = None
t0 = time.time()
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
print(f"分析完成: {time.time()-t0:.1f}s, {len(win.result.photos)}张 {len(win.result.groups)}组", flush=True)

# 手动调用 _show_group(0)，计时
t1 = time.time()
print("开始 _show_group(0)...", flush=True)
win._show_group(0)
app.processEvents()
print(f"_show_group(0) 返回: {time.time()-t1:.1f}s", flush=True)

# 检查右侧有没有 panel
panel = win.right_layout.itemAt(0).widget()
print(f"右侧 widget: {type(panel).__name__}", flush=True)
if isinstance(panel, GroupPanel):
    print(f"GroupPanel cards: {len(panel.cards)}", flush=True)
    for c in panel.cards:
        pm = c.img_label.pixmap()
        print(f"  card {c.photo.name}: pixmap={'有' if pm and not pm.isNull() else '空'}", flush=True)
print("DONE", flush=True)
