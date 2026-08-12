#!/usr/bin/env python3
"""端到端测试：复制少量真实照片到临时文件夹，验证 确认→移动→导出 全链路"""
import os
import sys
import shutil
import tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

from main import MainWindow, GroupPanel
import time

SRC = r"E:\尼康照片\美国"
# 取前 12 张真实照片做测试
files = sorted(os.listdir(SRC))[:12]
test_dir = tempfile.mkdtemp(prefix="photoselect_e2e_")
for f in files:
    shutil.copy2(os.path.join(SRC, f), os.path.join(test_dir, f))
print(f"测试目录: {test_dir} ({len(files)} 张照片)")

app = QApplication([])
win = MainWindow()
win.show()
win.folder_label.setText(test_dir)
win.threshold_spin.setValue(7)
win._start_analysis()
deadline = time.time() + 120
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
assert win.result is not None, "分析失败"
print(f"分析: {len(win.result.photos)} 张, {len(win.result.groups)} 组")

# 确认第一个组（真实移动）
if win.result.groups:
    win._show_group(0)
    app.processEvents()
    panel = win.right_layout.itemAt(0).widget()
    panel._confirm_group()
    app.processEvents()
    trash = os.path.join(test_dir, "_待删除")
    assert os.path.isdir(trash), "待删除文件夹未创建"
    n_trash = len(os.listdir(trash))
    print(f"确认组0: {n_trash} 张已移入 _待删除 ✓")

    # 验证原文件夹少了 n_trash 张
    remaining = [f for f in os.listdir(test_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"原文件夹剩余: {len(remaining)} 张 (应为 {len(files) - n_trash})")
    assert len(remaining) == len(files) - n_trash, "数量不符!"

    # 测试导出
    export_dir = tempfile.mkdtemp(prefix="photoselect_export_")
    from dedup_engine import copy_kept
    kept_paths = []
    for i, g in enumerate(win.result.groups):
        if i in win.confirmed_groups:
            kept_paths.append(g.user_keep.path)
        else:
            kept_paths.append(g.recommended_keep.path)
    kept_paths.extend(s.path for s in win.result.singles)
    ok, skipped = copy_kept(kept_paths, export_dir)
    print(f"导出: {ok} 张到临时导出目录 (跳过 {skipped})")
    assert ok > 0, "导出失败!"

# 清理
shutil.rmtree(test_dir, ignore_errors=True)
print("\n=== E2E TEST PASSED ===")
