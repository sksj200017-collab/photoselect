#!/usr/bin/env python3
"""v2.7 回归测试：多选保留跨面板保持 / 总览显示全部 / 分组列表宽度"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

from PySide6.QtWidgets import QApplication as QA2
from main import (MainWindow, ReviewPanel, GroupOverviewPanel,
                  DoneOverviewDialog)
from dedup_engine import MODE_STRICT, Group
import time

app = QA2([])
win = MainWindow()
win.show()

# 版本号
import main as mm_mod
assert mm_mod.APP_VERSION == "2.7.0"
print(f"PASS 1: 版本号 v{mm_mod.APP_VERSION}")

# 分析
TEST_FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"
win.folder_label.setText(TEST_FOLDER)
win.welcome_folder_label.setText(f"📁 {TEST_FOLDER}")
win.mode_combo.setCurrentIndex(0)
win.filter_combo.setCurrentIndex(0)
win.threshold_slider.setValue(7)
win.result = None
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None

# 进入选图
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)

# 测试：组内选多张保留（>1张）
group0 = rp.group
if len(group0.photos) >= 2:
    # 保留前2张
    rp.keep_paths = {group0.photos[0].path, group0.photos[1].path}
    rp.group.pending_kept_paths = set(rp.keep_paths)
    rp._rebuild()
    n_keep = len(rp.keep_paths)
    print(f"  → 选了 {n_keep} 张保留")
    assert n_keep >= 2, "应至少选2张"

    # 切到别的组再回来（模拟跨面板）
    if len(win.result.groups) > 1:
        win._show_group(1)
        for _ in range(5):
            app.processEvents(); time.sleep(0.02)
        win._show_group(0)
        for _ in range(5):
            app.processEvents(); time.sleep(0.02)
        rp2 = win.review_layout.itemAt(0).widget()
        assert isinstance(rp2, ReviewPanel)
        restored = len(rp2.keep_paths)
        print(f"  → 切回后恢复 {restored} 张保留")
        assert restored == n_keep, \
            f"BUG: 切回后只显示 {restored} 张（应为 {n_keep}）"
        print("PASS 2: 多选保留跨面板保持 OK")

    # 确认 → kept_paths 保存全部
    import main as mm
    mm.move_to_trash = lambda paths, folder: len(paths)
    rp._confirm_group()
    app.processEvents()
    assert group0.confirmed
    assert len(group0.kept_paths) == n_keep, \
        f"kept_paths 只有 {len(group0.kept_paths)} 张（应为 {n_keep}）"
    print(f"PASS 3: 确认后 kept_paths 保存 {len(group0.kept_paths)} 张")

    # 总览显示全部保留
    # 把所有组标为确认
    for g in win.result.groups:
        if not g.confirmed:
            g.user_keep = g.photos[0]
            g.kept_paths = {g.photos[0].path}
            g.confirmed = True
    dod = DoneOverviewDialog(win.result, win.cache, win)
    n_ov = len(dod._kept_paths)
    print(f"  → 总览显示 {n_ov} 张")
    # 组0的2张都应该在总览里
    kept0 = group0.kept_paths
    in_overview = sum(1 for p in kept0 if p in dod._kept_paths)
    assert in_overview == len(kept0), f"总览缺少 {len(kept0)-in_overview} 张"
    print("PASS 4: 结果总览显示全部保留照片 OK")

# 分组列表宽度
panel = win.overview_layout.itemAt(0).widget() if win.overview_layout.count() else None
if panel is None:
    win._show_overview()
    for _ in range(5):
        app.processEvents(); time.sleep(0.02)
    panel = win.overview_layout.itemAt(0).widget()
w = panel.group_scroll.width() if hasattr(panel, 'group_scroll') else 0
print(f"PASS 5: 分组列表宽度 = {w}px（应为520）")
assert w >= 500

print("\n=== ALL V2.7 REGRESSION TESTS PASSED ===")
