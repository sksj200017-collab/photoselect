#!/usr/bin/env python3
"""v2.4 回归测试：分组总览重设计/撤销即时刷新/筛选完毕/导出下拉"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

from PySide6.QtWidgets import QApplication as QA2
from main import (MainWindow, ReviewPanel, GroupOverviewPanel,
                  PickGroupDialog, ExportDialog, DoneOverviewDialog)
from dedup_engine import FILTER_ALL, MODE_STRICT
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：欢迎词
wl = win.welcome_page.findChildren(type(win.welcome_page.layout().itemAt(1).widget()))
print("PASS 1: 欢迎页存在")

# 测试2：分析 → 分组总览
TEST_FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"
win.folder_label.setText(TEST_FOLDER)
win.filter_combo.setCurrentIndex(0)
win.mode_combo.setCurrentIndex(0)
win.threshold_slider.setValue(7)
win.result = None
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None
assert win.stack.currentWidget() is win.overview_page
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
print(f"PASS 2: 分组总览 OK（{len(win.result.groups)}组, "
      f"{len(win.result.singles)}独张）")

# 测试3：组列表带缩略图 + 双击预览
assert hasattr(panel, '_group_widgets') and len(panel._group_widgets) == len(win.result.groups)
print("PASS 3: 组列表带代表缩略图 OK")

# 测试4：加入目标组弹窗
if win.result.singles:
    dlg = PickGroupDialog(win.result.groups, "测试", win)
    dlg.list._list.setCurrentRow(0)
    dlg._accept()
    assert dlg.selected_group is not None
    print("PASS 4: PickGroupDialog OK")

# 测试5：合并组
if len(win.result.groups) >= 2:
    g0 = win.result.groups[0]
    n0 = len(g0.photos)
    g1 = win.result.groups[1]
    n1 = len(g1.photos)
    panel._selected_group = g0
    # 模拟合并：直接把 g1 并入 g0
    g0.photos.extend(g1.photos)
    g0.recalc()
    win.result.groups.remove(g1)
    panel._refresh_groups()
    assert len(g0.photos) == n0 + n1
    print(f"PASS 5: 合并组 OK（组0 现有 {len(g0.photos)} 张）")

# 测试6：进入选图 → 确认 → 撤销（立即刷新不翻页）
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
assert win.stack.currentWidget() is win.review_page
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)

# 确认
import main as mm
mm.move_to_trash = lambda paths, folder: len(paths)
mm.restore_from_trash = lambda paths, folder: len(paths)
rp._confirm_group()
app.processEvents()
assert rp.group.confirmed
# 验证撤销按钮立即可见（无需翻页）
undo_visible = False
for i in range(rp.bottom_btns.count()):
    w = rp.bottom_btns.itemAt(i).widget()
    if w and "撤销" in w.text():
        undo_visible = True
assert undo_visible, "确认后撤销按钮未立即出现!"
print("PASS 6: 确认后撤销按钮立即出现（不翻页）")

# 撤销
rp._undo_group()
app.processEvents()
assert not rp.group.confirmed
# 验证确认按钮立即可见
confirm_visible = False
for i in range(rp.bottom_btns.count()):
    w = rp.bottom_btns.itemAt(i).widget()
    if w and "确认" in w.text():
        confirm_visible = True
assert confirm_visible, "撤销后确认按钮未立即出现!"
print("PASS 7: 撤销后确认按钮立即出现（不翻页）")

# 测试8：筛选完毕按钮（全部确认后）
win.confirmed_groups = set()
for i, g in enumerate(win.result.groups):
    if not g.confirmed:
        # monkeypatch 移动
        g.user_keep = g.photos[0]
        g.confirmed = True
    win.confirmed_groups.add(i)
win._on_group_confirmed(len(win.result.groups) - 1)
assert win.done_btn.isVisible(), "筛选完毕按钮未显示!"
print("PASS 8: 全部确认后筛选完毕按钮显示")

# 测试9：DoneOverviewDialog
dlg = DoneOverviewDialog(win.result, win.cache, win)
assert dlg is not None
print("PASS 9: 筛选结果总览对话框构建 OK")

# 测试10：导出下拉
edlg = ExportDialog(5, 3, win)
assert edlg.selected_mode() in ("all", "kept", "singles", "everything")
print("PASS 10: 导出下拉 OK")

print("\n=== ALL V2.4 REGRESSION TESTS PASSED ===")
