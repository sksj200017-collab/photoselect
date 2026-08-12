#!/usr/bin/env python3
"""v2.11 回归测试：照片格式改名/解散分组/可见照片过滤/全屏按钮/重置全部"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)  # 重置确认默认同意
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from PySide6.QtWidgets import QApplication as QA2
from main import MainWindow, ReviewPanel, GroupOverviewPanel, FullscreenPreview
from dedup_engine import MODE_STRICT, Group, ThumbnailCache
import main as mm
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：照片格式标签
assert mm.APP_VERSION.startswith("2.11")
assert win.w_filter is not None
print("PASS 1: 版本 v2.11 + 界面存在")

# 测试2：Group 有 visible_photos 方法
assert hasattr(Group, 'visible_photos')
print("PASS 2: Group.visible_photos 存在")

# 测试3：分析 + 进入选图
win.folder_label.setText(r"C:\Users\nfd\Desktop\test2")
win.result = None
win._start_analysis()
d = time.time() + 200
while win.result is None and time.time() < d:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)
assert hasattr(rp, 'reset_btn'), "缺重置按钮!"
assert not hasattr(rp, 'only_rec_btn'), "仅保留推荐按钮应被移除!"
print("PASS 3: 重置按钮存在，仅保留推荐已移除")

# 测试4：确认一组后 visible_photos 正确
g0 = rp.group
mm.move_to_trash = lambda paths, folder: len(paths)
rp.keep_paths = {g0.photos[0].path}
rp.group.pending_kept_paths = set(rp.keep_paths)
rp._confirm_group()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
vis = g0.visible_photos()
assert len(vis) == 1, f"确认保留1张后 visible 应为1, 实际{len(vis)}"
print("PASS 4: 确认后 visible_photos 只显示保留的")

# 测试5：重置全部（模拟确认后重置）
n_confirmed_before = sum(1 for g in win.result.groups if g.confirmed)
assert n_confirmed_before >= 1
win._reset_all_groups()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
all_unconfirmed = all(not g.confirmed for g in win.result.groups)
assert all_unconfirmed, "重置后应全部未确认!"
assert len(win.confirmed_groups) == 0
print(f"PASS 5: 重置全部筛选 OK（{n_confirmed_before} 组已重置）")

# 测试6：全屏预览单张隐藏翻页按钮
fp = FullscreenPreview([r"C:\Users\nfd\Desktop\test2\DSC_6180.JPG"],
                       ThumbnailCache(), set(), 0)
fp.show()
assert not fp.prev_btn.isVisible() and not fp.next_btn.isVisible()
print("PASS 6: 单张照片翻页按钮隐藏 OK")

# 测试7：组内预览只显示可见照片 + 解散按钮
win._show_overview()
for _ in range(5):
    app.processEvents(); time.sleep(0.02)
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
# 找一个未确认组
unconf = next((g for g in win.result.groups if not g.confirmed), None)
if unconf:
    from main import PickRemoveDialog
    dlg = PickRemoveDialog(unconf, win.cache, mode="remove", parent=win)
    assert hasattr(dlg, '_dissolve'), "缺解散方法!"
    assert dlg._cards, "组内预览应显示卡片"
    print(f"PASS 7: 组内预览 + 解散按钮 OK（{len(dlg._cards)} 张可见）")

print("\n=== ALL V2.11 REGRESSION TESTS PASSED ===")
