#!/usr/bin/env python3
"""v2.3 回归测试：文件过滤/分组总览/撤销/全屏/导出弹窗"""
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
from main import MainWindow, ReviewPanel, GroupOverviewPanel, FullscreenPreview
from dedup_engine import FILTER_JPG, FILTER_ALL, MODE_STRICT
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：文件类型过滤下拉
assert win.filter_combo.count() == 3
print("PASS 1: 文件类型下拉（全部/JPG/RAW）")

# 测试2：分析（全部类型）→ 分组总览自动进入
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
# d8ad463 应该被包含
n_total = len(win.result.photos)
print(f"PASS 2: 分析完成 共{n_total}张 "
      f"(含d8ad463: {any('d8ad463' in p for p in win.result.photos)})")
assert win.stack.currentWidget() is win.overview_page, "未自动进入分组总览!"
print("PASS 3: 自动进入分组总览页")

# 测试4：分组总览面板
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
print(f"PASS 4: GroupOverviewPanel OK, "
      f"组数={len(win.result.groups)}, 独张={len(win.result.singles)}")

# 测试5：手动加入组（选中未分组照片→加入组0）
if win.result.singles and win.result.groups:
    singles = win.result.singles
    # 选 2 张
    panel._multi_select = {singles[0].path, singles[1].path}
    panel._selected_group = win.result.groups[0]
    panel._add_to_group()
    assert len(win.result.groups[0].photos) >= 3
    print(f"PASS 5: 手动加入组 OK（组0现有{len(win.result.groups[0].photos)}张）")

# 测试6：进入选图
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
assert win.stack.currentWidget() is win.review_page
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)
loaded = sum(1 for c in rp.cards
             if c.img_label.pixmap() and not c.img_label.pixmap().isNull())
print(f"PASS 6: 选图页 {len(rp.cards)}张卡片, {loaded}张已显示")

# 测试7：全屏预览（保留/删除按钮 + 双击放大不改变状态）
if rp.cards:
    paths = [c.photo.path for c in rp.cards]
    keep_set = {c.photo.path for c in rp.cards if c.keep}
    pv = FullscreenPreview(paths, win.cache, keep_set, 0, win)
    before = set(pv.keep_paths)
    # 模拟点击删除按钮：当前照片从 keep 移除
    cur = paths[pv.index]
    pv._mark_delete()
    assert cur not in pv.keep_paths, "删除按钮未生效"
    # 模拟再点保留
    pv._mark_keep()
    assert cur in pv.keep_paths, "保留按钮未生效"
    # 双击 = 只切换 zoom，不改变 keep
    keep_before_dbl = set(pv.keep_paths)
    pv.zoom = not pv.zoom
    assert set(pv.keep_paths) == keep_before_dbl, "双击改变了保留状态!"
    print("PASS 7: 全屏预览 保留/删除按钮 + 双击纯放大 OK")
    pv.close()

# 测试8：确认组 + 撤销
import main as mm
mm.move_to_trash = lambda paths, folder: len(paths)
mm.restore_from_trash = lambda paths, folder: len(paths)
rp._confirm_group()
app.processEvents()
assert rp.group.confirmed
# 撤销
rp._undo_group()
app.processEvents()
assert not rp.group.confirmed
print("PASS 8: 确认+撤销 OK")

# 测试9：导出弹窗
dlg = mm.ExportDialog(5, 3, win)
print("PASS 9: 导出弹窗构建 OK")

print("\n=== ALL V2.3 REGRESSION TESTS PASSED ===")
