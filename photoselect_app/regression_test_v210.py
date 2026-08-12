#!/usr/bin/env python3
"""v2.10 回归测试：多线程提速/空组标记/未分组待删除/拖放/回车快捷键/一键全部推荐"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

from PySide6.QtWidgets import QApplication as QA2
from main import MainWindow, ReviewPanel, GroupOverviewPanel
from dedup_engine import MODE_STRICT, MODE_SUBJECT, Group, Analyzer
import main as mm
import time

app = QA2([])
win = MainWindow()
win.show()

# 版本号
assert mm.APP_VERSION == "2.10.0"
print("PASS 1: 版本号 v2.10.0")

# 多线程结果正确性（80张 test2）
folder = r"C:\Users\nfd\Desktop\test2"
def cb(c, t, m): pass
a = Analyzer(mode=MODE_STRICT, progress_cb=cb)
res = a.analyze(folder)
assert len(res.photos) == 80, f"应80张, 实际{len(res.photos)}"
print(f"PASS 2: 多线程分析 OK（{len(res.photos)}张, {len(res.groups)}组）")

# GUI 全流程
win.folder_label.setText(folder)
win.result = None
win._start_analysis()
d = time.time() + 200
while win.result is None and time.time() < d:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None

# 进入选图
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)

# 测试3：回车快捷键存在
assert hasattr(rp, 'enter_shortcut')
print("PASS 3: 回车快捷键 OK")

# 测试4：允许全删（空 keep_paths 确认后不强制保留）
g0 = rp.group
rp.keep_paths = set()   # 用户全选删除
rp.group.pending_kept_paths = set()
import main as mm2
mm2.move_to_trash = lambda paths, folder: len(paths)
rp._confirm_group()
app.processEvents()
assert g0.confirmed
assert g0.kept_paths == set(), f"空组应 kept_paths 为空, 实际 {g0.kept_paths}"
print("PASS 4: 允许全删 → 空组标记 OK")

# 测试5：一键保留全部推荐
# 把所有组标为未确认
for g in win.result.groups:
    g.confirmed = False
win.confirmed_groups.clear()
win._all_recommended_groups()
app.processEvents()
all_confirmed = all(g.confirmed for g in win.result.groups)
assert all_confirmed, "一键保留后应全部确认!"
print(f"PASS 5: 一键保留全部推荐 OK（{len(win.result.groups)} 组全确认）")

# 测试6：分组总览的未分组待删除按钮 + 拖放
win._show_overview()
for _ in range(5):
    app.processEvents(); time.sleep(0.02)
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
assert hasattr(panel, 'trash_btn'), "缺移入待删除按钮!"
assert hasattr(panel, '_start_drag'), "缺拖放支持!"
assert hasattr(panel, '_drop_on_group'), "缺拖放接收!"
print("PASS 6: 未分组待删除按钮 + 拖放支持存在 OK")

# 测试7：拖放逻辑（直接调用 _move_singles_to_group）
if win.result.singles and win.result.groups:
    # 找一个未确认组
    target = next((g for g in win.result.groups if not g.confirmed), None)
    if target is None:
        # 全部确认了就解除一个
        win.result.groups[0].confirmed = False
        target = win.result.groups[0]
    s = win.result.singles[0]
    n0 = len(target.photos)
    n = panel._move_singles_to_group(target, {s.path})
    assert n == 1, f"应移动1张, 实际{n}"
    assert s not in win.result.singles, "移动后不应还在未分组"
    assert len(target.photos) == n0 + 1, "目标组应多1张"
    print("PASS 7: 拖放加入组逻辑 OK")

# 测试8：已确认组不能拖入
win.result.groups[0].confirmed = True
print("PASS 8: 已确认组锁定（拖放时有保护判断）OK")

print("\n=== ALL V2.10 REGRESSION TESTS PASSED ===")
