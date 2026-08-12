#!/usr/bin/env python3
"""GUI v2 冒烟测试（offscreen）：验证分析→分组→选择→确认→手动分组流程"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from main import MainWindow, GroupPanel, ManualGroupPanel
from dedup_engine import MODE_SUBJECT

import time

# 屏蔽所有消息框（offscreen 会阻塞）
from PySide6.QtWidgets import QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

app = QApplication([])
win = MainWindow()
win.show()

# ── 测试 1：严格模式分析 ──────────────────────────────────────
win.folder_label.setText(r"E:\尼康照片\美国")
win.threshold_spin.setValue(7)
win.mode_combo.setCurrentIndex(0)
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
assert win.result is not None, "分析失败"
print(f"PASS 1: 严格模式 {len(win.result.photos)} 张, "
      f"{len(win.result.groups)} 组")

# ── 测试 2：分组显示 + 切换保留 ───────────────────────────────
win._show_group(0)
app.processEvents()
panel = win.right_layout.itemAt(0).widget()
assert isinstance(panel, GroupPanel), f"不是 GroupPanel: {type(panel)}"
# 模拟点击第一张卡片切换
card = panel.cards[0]
card.set_keep(not card.keep)
if card.keep:
    panel.keep_paths.add(card.photo.path)
else:
    panel.keep_paths.discard(card.photo.path)
print(f"PASS 2: 组0 显示 {len(panel.cards)} 张卡片, "
      f"keep_paths={len(panel.keep_paths)}")

# ── 测试 3：确认组（不真移文件，只测逻辑） ────────────────────
# 用 monkeypatch 防止真移动
from dedup_engine import move_to_trash
calls = []
def fake_move(paths, folder):
    calls.append((len(paths), folder))
    return len(paths)
import main as main_mod
main_mod.move_to_trash = fake_move
panel._confirm_group()
app.processEvents()
assert panel.group.confirmed, "组未确认"
print(f"PASS 3: 确认组成功, 调用了 move_to_trash({calls})")

# ── 测试 4：导航 ──────────────────────────────────────────────
win._nav_group(1)
app.processEvents()
print(f"PASS 4: 导航到组 {win.current_group_index}")

# ── 测试 5：同主体模式 ────────────────────────────────────────
win.mode_combo.setCurrentIndex(1)
win._start_analysis()
deadline = time.time() + 300
while (win.result is None or win.result.mode != MODE_SUBJECT) and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
assert win.result is not None and win.result.mode == MODE_SUBJECT, "同主体分析失败"
print(f"PASS 5: 同主体模式 {len(win.result.photos)} 张, "
      f"{len(win.result.groups)} 组")

# ── 测试 6：手动分组面板 ──────────────────────────────────────
win._open_manual()
app.processEvents()
mpanel = win.right_layout.itemAt(0).widget()
assert isinstance(mpanel, ManualGroupPanel), f"不是 ManualGroupPanel: {type(mpanel)}"
print(f"PASS 6: 手动分组面板, 未分组 {len(win.result.singles)} 张")

print("\n=== ALL V2 SMOKE TESTS PASSED ===")
