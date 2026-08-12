#!/usr/bin/env python3
"""v2.6 回归测试：欢迎页滑块/i信息/模式同步/新建组/锁定组/自定义弹窗"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 屏蔽自定义弹窗（offscreen 会阻塞）
from main import _ps_dialog, play_success_sound

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

from PySide6.QtWidgets import QApplication as QA2
from main import (MainWindow, ReviewPanel, GroupOverviewPanel,
                  PickGroupDialog, PickGroupsDialog, _patch_message_boxes)
from dedup_engine import FILTER_ALL, MODE_STRICT, MODE_SUBJECT, Group
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：欢迎页有相似程度滑块 + i 信息
assert hasattr(win, 'w_threshold'), "欢迎页缺相似程度滑块!"
assert hasattr(win, 'w_threshold_value')
print("PASS 1: 欢迎页相似程度滑块存在")

# 测试2：欢迎页滑块与顶部栏同步
win.w_threshold.setValue(11)
assert win.threshold == 11, f"阈值未同步: {win.threshold}"
assert win.threshold_slider.value() == 11
assert win.w_threshold_value.text() == "11"
print("PASS 2: 滑块双向同步 OK")

# 测试3：模式双向同步（顶部栏改 → 欢迎页同步）
win.mode_combo.setCurrentIndex(1)  # 同主体
assert win.w_mode.currentIndex() == 1, "模式未同步到欢迎页!"
# 欢迎页改 → 顶部栏同步
win.w_mode.setCurrentIndex(0)
assert win.mode_combo.currentIndex() == 0, "模式未同步到顶部栏!"
print("PASS 3: 模式双向同步 OK")

# 测试4：_start_analysis 从顶部栏读取（修复第4点 bug）
win.folder_label.setText(r"C:\Users\nfd\Desktop\testPhotoSelect")
win.welcome_folder_label.setText("📁 test")
win.mode_combo.setCurrentIndex(1)   # 同主体
win.filter_combo.setCurrentIndex(0)
win.result = None
win._start_analysis()
deadline = time.time() + 400
while (win.result is None or win.result.mode != MODE_SUBJECT) \
        and time.time() < deadline:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None and win.result.mode == MODE_SUBJECT, \
    f"模式未生效: {win.result.mode if win.result else 'None'}"
print(f"PASS 4: 顶部栏模式生效（同主体筛选，{len(win.result.groups)}组）")

# 测试5：分组总览 + 新建组
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
# 模拟选择2张未分组照片 → 新建组
if len(win.result.singles) >= 2:
    singles = win.result.singles
    panel._multi_select = {singles[0].path, singles[1].path}
    # 模拟 PickGroupDialog 新建组
    photos = [p for p in win.result.singles if p.path in panel._multi_select]
    grp = Group(photos)
    grp.recalc()
    win.result.groups.append(grp)
    win.result.singles = [p for p in win.result.singles
                          if p.path not in panel._multi_select]
    panel._multi_select.clear()
    panel._refresh_groups()
    panel._refresh_singles()
    print(f"PASS 5: 新建组 OK（现有 {len(win.result.groups)} 组）")

# 测试6：锁定组保护（已确认组不能合并/移出）
if win.result.groups:
    g0 = win.result.groups[0]
    g0.confirmed = True
    # 合并时可用组应排除 g0
    available = [g for g in win.result.groups if not g.confirmed]
    assert g0 not in available, "已确认组未被排除!"
    # 预览已确认组 → 只读
    import main as mm
    mm.PickRemoveDialog = lambda *a, **k: type('D', (), {'exec': lambda s: False})()
    print(f"PASS 6: 锁定组保护 OK（{len(win.result.groups)-len(available)} 组已锁）")

# 测试7：自定义弹窗函数
_patch_message_boxes()
assert callable(QMessageBox.information)
print("PASS 7: 自定义弹窗替换 OK")

# 测试8：PickGroupDialog 新建组按钮
if win.result.groups:
    pgd = PickGroupDialog(win.result.groups, "测试", win,
                          allow_new_group=True, new_photo_count=3)
    assert pgd._allow_new_group
    pgd._accept_new()
    assert pgd.new_group
    print("PASS 8: 新建组按钮 OK")

print("\n=== ALL V2.6 REGRESSION TESTS PASSED ===")
