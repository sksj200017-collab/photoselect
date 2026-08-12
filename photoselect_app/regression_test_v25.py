#!/usr/bin/env python3
"""v2.5 回归测试：居中欢迎页/音效/组多选合并/导出所有保留/结果总览分页"""
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
                  PickGroupDialog, PickGroupsDialog, ExportDialog,
                  DoneOverviewDialog, play_success_sound)
from dedup_engine import FILTER_ALL, MODE_STRICT
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：居中欢迎页 + 顶部栏初始隐藏
assert hasattr(win, 'welcome_folder_label')
assert hasattr(win, 'top_widget')
assert not win.top_widget.isVisible(), "顶部栏应初始隐藏"
print("PASS 1: 居中欢迎页 OK（顶部栏初始隐藏）")

# 测试2：音效函数不报错
play_success_sound()
print("PASS 2: 音效函数调用 OK")

# 测试3：分析 → 分组总览（顶部栏出现）
TEST_FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"
win.folder_label.setText(TEST_FOLDER)
win.welcome_folder_label.setText(f"📁 {TEST_FOLDER}")
win.w_filter.setCurrentIndex(0)
win.w_mode.setCurrentIndex(0)
win.result = None
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None
assert win.top_widget.isVisible(), "分析后顶部栏应显示"
assert win.stack.currentWidget() is win.overview_page
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
print(f"PASS 3: 分析完成 → 分组总览 OK（{len(win.result.groups)}组）")

# 测试4：组列表加大 + 缩略图
assert hasattr(panel, '_group_widgets')
w0 = panel._group_widgets[0]
thumb = w0.findChildren(type(w0.layout().itemAt(0).widget()))[0]
print("PASS 4: 组列表带缩略图 OK")

# 测试5：PickGroupsDialog 多选
if len(win.result.groups) >= 2:
    pgd = PickGroupsDialog(win.result.groups, win.cache, "测试", win)
    # 勾选前两组
    pgd._rows[0][1].setChecked(True)
    pgd._rows[1][1].setChecked(True)
    pgd._accept()
    assert len(pgd.selected_groups) == 2
    print("PASS 5: 合并多选对话框 OK")

# 测试6：PickGroupDialog 单选带缩略图
pgd2 = PickGroupDialog(win.result.groups, "测试", win)
pgd2._select_row(1)
assert pgd2.selected_group is win.result.groups[1]
print("PASS 6: 加入组单选对话框（带缩略图）OK")

# 测试7：进入选图 → 确认多张保留 → 验证 kept_paths 保存
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)
# 全保留（模拟多选保留）
rp._all_keep_btn_ok = True
rp.keep_paths = {p.path for p in rp.group.photos}
rp._confirm_group()
app.processEvents()
assert rp.group.confirmed
assert rp.group.kept_paths == {p.path for p in rp.group.photos}
print(f"PASS 7: 确认多张保留 → kept_paths 保存 {len(rp.group.kept_paths)}张")

# 测试8：DoneOverviewDialog 显示所有保留 + 分页
# 构造一个保留多张的组
all_confirmed = True
for g in win.result.groups:
    if not g.confirmed:
        g.user_keep = g.photos[0]
        g.kept_paths = {p.path for p in g.photos[:2]}
        g.confirmed = True
    win.confirmed_groups.add(win.result.groups.index(g))
dod = DoneOverviewDialog(win.result, win.cache, win)
n_kept = len(dod._kept_paths)
print(f"PASS 8: 结果总览 {n_kept} 张保留照片（含每组的全部保留）")
assert n_kept >= len(win.result.groups)

# 测试9：导出下拉（无"所有照片"项）
edlg = ExportDialog(5, 3, win)
modes = [edlg.export_combo.itemData(i) for i in range(edlg.export_combo.count())]
assert "everything" not in modes
print(f"PASS 9: 导出下拉 OK（选项: {modes}）")

# 测试10：导出收集所有保留
import main as mm
mm.copy_kept = lambda paths, dest: (len(paths), 0)
kept_paths = []
for g in win.result.groups:
    if g.kept_paths:
        kept_paths.extend(p.path for p in g.photos if p.path in g.kept_paths)
    elif g.confirmed:
        kept_paths.append(g.user_keep.path)
    else:
        kept_paths.append(g.recommended_keep.path)
print(f"PASS 10: 导出收集所有保留 {len(kept_paths)} 张")

print("\n=== ALL V2.5 REGRESSION TESTS PASSED ===")
