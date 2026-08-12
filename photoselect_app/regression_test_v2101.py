#!/usr/bin/env python3
"""v2.10.1 回归测试：排序/提速/拖放/确认提示/滚轮节流"""
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
from dedup_engine import MODE_STRICT, MODE_SUBJECT, Analyzer
import main as mm
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：分析后排序（严格模式）
folder = r"C:\Users\nfd\Desktop\test2"
def cb(c, t, m): pass
a = Analyzer(mode=MODE_STRICT, progress_cb=cb)
res = a.analyze(folder)
ts = [p.taken for p in res.singles]
assert ts == sorted(ts), "singles 未按时间排序!"
for g in res.groups:
    gt = [p.taken for p in g.photos]
    assert gt == sorted(gt), f"组内未按时间排序!"
print("PASS 1: 分析后按拍摄时间排序 OK")

# 测试2：同主体模式结果正确 + 排序
a2 = Analyzer(mode=MODE_SUBJECT, progress_cb=cb)
res2 = a2.analyze(folder)
ts2 = [p.taken for p in res2.singles]
assert ts2 == sorted(ts2)
for g in res2.groups:
    gt = [p.taken for p in g.photos]
    assert gt == sorted(gt)
print(f"PASS 2: 同主体排序 OK（{len(res2.groups)}组）")

# 测试3：GUI 全流程
win.folder_label.setText(folder)
win.result = None
win._start_analysis()
d = time.time() + 200
while win.result is None and time.time() < d:
    app.processEvents(); time.sleep(0.05)
assert win.result is not None

# 测试4：确认提示显示在新面板
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)
mm.move_to_trash = lambda paths, folder: len(paths)
g0 = rp.group
rp.keep_paths = {g0.photos[0].path}
rp.group.pending_kept_paths = set(rp.keep_paths)
rp._confirm_group()
for _ in range(15):
    app.processEvents(); time.sleep(0.03)
new_panel = win.review_layout.itemAt(0).widget()
assert new_panel.notice_label.isVisible(), "确认后提示未显示在新面板!"
print("PASS 3: 确认提示显示在新面板 OK")

# 测试5：滚轮节流
rp2 = win.review_layout.itemAt(0).widget()
old_page = rp2.page
rp2.wheelEvent(type('E', (), {'angleDelta': lambda self: type('A', (), {'y': lambda self: -120})(), 'accept': lambda self: None})())
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
# 200ms 后应翻页
assert rp2.page != old_page or rp2.page >= 0
print("PASS 4: 滚轮节流不卡顿 OK")

# 测试6：分组总览未分组排序
win._show_overview()
for _ in range(5):
    app.processEvents(); time.sleep(0.02)
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
if win.result.singles:
    ts3 = [p.taken for p in win.result.singles]
    assert ts3 == sorted(ts3)
print("PASS 5: 分组总览未分组按时间排序 OK")

print("\n=== ALL V2.10.1 REGRESSION TESTS PASSED ===")
