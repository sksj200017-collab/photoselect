#!/usr/bin/env python3
"""GUI v2.1 冒烟测试（offscreen）：验证漫画风界面 + 人脸识别模式"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 必须在 import main 之前替换 QMessageBox
from PySide6.QtWidgets import QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

from PySide6.QtWidgets import QApplication
from main import MainWindow, GroupPanel, ManualGroupPanel
from dedup_engine import MODE_SUBJECT, MODE_STRICT

import time

app = QApplication([])
win = MainWindow()
win.show()

# 测试 1：界面元素
assert hasattr(win, 'card_strict') and hasattr(win, 'card_subject')
assert hasattr(win, 'threshold_slider')
print("PASS 1: 漫画风模式卡片 + 滑块存在")

# 测试 2：模式切换
win._set_mode(MODE_SUBJECT)
assert win.mode == MODE_SUBJECT
print("PASS 2: 模式切换 OK")

# 测试 3：严格模式分析
TEST_FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"
win.folder_label.setText(TEST_FOLDER)
win._set_mode(MODE_STRICT)
win.threshold_slider.setValue(7)
win.result = None
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
assert win.result is not None, "严格模式分析失败"
print(f"PASS 3: 严格模式 {len(win.result.photos)} 张, {len(win.result.groups)} 组")

# 测试 4：同主体（人脸识别）模式
print("T4: 切换同主体模式...", flush=True)
win._set_mode(MODE_SUBJECT)
win.result = None
print("T4: 启动分析...", flush=True)
win._start_analysis()
print("T4: 等待分析完成...", flush=True)
deadline = time.time() + 400
while (win.result is None or win.result.mode != MODE_SUBJECT) \
        and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
print(f"T4: result={win.result is not None}", flush=True)
assert win.result is not None and win.result.mode == MODE_SUBJECT, "同主体分析失败"
print(f"PASS 4: 同主体模式 {len(win.result.photos)} 张, {len(win.result.groups)} 组", flush=True)

# 关键验证：换人拆开
g1 = g2 = None
for g in win.result.groups:
    names = [p.name for p in g.photos]
    if any('2983' in n for n in names):
        g1 = names
    if any('2994' in n for n in names):
        g2 = names
assert g1 and g2 and not any('2994' in n for n in g1), "换人未拆开!"
print(f"PASS 4b: 换人识别成功 — 2983组{len(g1)}张, 2994组{len(g2)}张")

# 测试 5：分组显示 + 卡片切换
win._show_group(0)
app.processEvents()
panel = win.right_layout.itemAt(0).widget()
assert isinstance(panel, GroupPanel)
card = panel.cards[0]
card.set_keep(not card.keep)
if card.keep:
    panel.keep_paths.add(card.photo.path)
else:
    panel.keep_paths.discard(card.photo.path)
print(f"PASS 5: 组0 显示 {len(panel.cards)} 张卡片, keep_paths={len(panel.keep_paths)}")

# 测试 6：确认组
import main as main_mod
calls = []
def fake_move(paths, folder):
    calls.append((len(paths), folder))
    return len(paths)
main_mod.move_to_trash = fake_move
panel._confirm_group()
app.processEvents()
assert panel.group.confirmed
print(f"PASS 6: 确认组 OK, move_to_trash({calls})")

# 测试 7：手动分组面板
win._open_manual()
app.processEvents()
mpanel = win.right_layout.itemAt(0).widget()
assert isinstance(mpanel, ManualGroupPanel)
print(f"PASS 7: 手动分组面板, 未分组 {len(win.result.singles)} 张")

print("\n=== ALL V2.1 SMOKE TESTS PASSED ===")
