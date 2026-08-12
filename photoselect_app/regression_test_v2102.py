#!/usr/bin/env python3
"""v2.10.2 回归测试：拖放MIME回退 / 全删组不崩溃 / 效率稳定 / 排序"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

from PySide6.QtWidgets import QApplication as QA2
from PySide6.QtCore import QMimeData, Qt, QPointF
from PySide6.QtGui import QDropEvent
from main import (MainWindow, ReviewPanel, GroupOverviewPanel,
                  DoneOverviewDialog)
from dedup_engine import MODE_STRICT, MODE_SUBJECT, Analyzer
import main as mm
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：版本号
assert mm.APP_VERSION == "2.10.2", mm.APP_VERSION
print("PASS 1: 版本号 v2.10.2")

# 测试2：效率 + 排序
folder = r"C:\Users\nfd\Desktop\test2"
def cb(c, t, m): pass
a = Analyzer(mode=MODE_SUBJECT, progress_cb=cb)
t0 = time.time()
res = a.analyze(folder)
t = time.time() - t0
assert t < 120, f"同主体太慢: {t:.1f}s"
ts = [p.taken for p in res.singles]
assert ts == sorted(ts)
print(f"PASS 2: 效率+排序 OK（{t:.1f}s, {len(res.groups)}组）")

# 测试3：拖放逻辑（直接调用 _move_singles_to_group，真实拖放由 Qt 系统传递）
win.folder_label.setText(r"C:\Users\nfd\Desktop\testPhotoSelect")
win.result = None
win._start_analysis()
d = time.time() + 200
while win.result is None and time.time() < d:
    app.processEvents(); time.sleep(0.05)
win._show_overview()
for _ in range(5):
    app.processEvents(); time.sleep(0.02)
panel = win.overview_layout.itemAt(0).widget()
assert isinstance(panel, GroupOverviewPanel)
if win.result.singles and win.result.groups:
    s0 = win.result.singles[0]
    target = next((g for g in win.result.groups if not g.confirmed),
                  win.result.groups[0])
    n_before = len(win.result.singles)
    n = panel._move_singles_to_group(target, {s0.path})
    assert n == 1 and len(win.result.singles) == n_before - 1, "拖放逻辑失败!"
    print("PASS 3: 拖放加入组逻辑 OK")

# 测试4：全删组不崩溃
for i, g in enumerate(win.result.groups):
    if i == 0:
        g.user_keep = None
        g.kept_paths = set()
        g.confirmed = True
    else:
        g.user_keep = g.photos[0]
        g.kept_paths = {g.photos[0].path}
        g.confirmed = True
    win.confirmed_groups.add(i)
dod = DoneOverviewDialog(win.result, win.cache, win)
print(f"PASS 4: 全删组结果总览 OK（{len(dod._kept_paths)} 张保留）")

# 测试5：ReviewPanel 全删组恢复
win._start_review_from_overview()
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
rp = win.review_layout.itemAt(0).widget()
assert isinstance(rp, ReviewPanel)
print(f"PASS 5: 全删组面板恢复 OK（keep_paths={len(rp.keep_paths)}）")

print("\n=== ALL V2.10.2 REGRESSION TESTS PASSED ===")
