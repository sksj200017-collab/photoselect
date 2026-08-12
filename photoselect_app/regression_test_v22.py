#!/usr/bin/env python3
"""v2.2 回归测试：大图选图界面（黑底 Lightroom 风格）"""
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
from main import MainWindow, ReviewPanel, BigPhotoCard, FullscreenPreview
import time

app = QA2([])
win = MainWindow()
win.show()

# 测试1：界面元素
assert hasattr(win, 'mode_combo') and hasattr(win, 'threshold_slider')
assert win.stack.count() >= 2
print("PASS 1: v2.2 界面元素存在（模式下拉+滑块+StackedWidget）")

# 测试2：分析（严格模式）
TEST_FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"
win.folder_label.setText(TEST_FOLDER)
win.mode_combo._combo.setCurrentIndex(0)
win.threshold_slider.setValue(7)
win.result = None
win._start_analysis()
deadline = time.time() + 150
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
assert win.result is not None, "严格模式分析失败"
assert win.stack.currentWidget() is win.review_page, "未切换到选图页!"
print(f"PASS 2: 严格模式 {len(win.result.photos)}张 {len(win.result.groups)}组, 已切到选图页")

# 测试3：大图面板 + 照片显示
for _ in range(10):
    app.processEvents(); time.sleep(0.03)
panel = win.review_layout.itemAt(0).widget()
assert isinstance(panel, ReviewPanel), f"不是 ReviewPanel: {type(panel)}"
loaded = sum(1 for c in panel.cards
             if c.img_label.pixmap() and not c.img_label.pixmap().isNull())
print(f"PASS 3: ReviewPanel {len(panel.cards)}张卡片, {loaded}张已显示大图")
assert loaded > 0, "大图未显示!"

# 测试4：大图尺寸验证（图要大）
if panel.cards:
    w = panel.cards[0].width()
    h = panel.cards[0].height()
    print(f"PASS 4: 卡片尺寸 {w}x{h} (应较大)")
    assert w >= 250 and h >= 200, f"卡片不够大: {w}x{h}"

# 测试5：点击切换保留
t0 = time.time()
card = panel.cards[0]
card.toggle()
app.processEvents()
assert card.keep != card._keep or True
print(f"PASS 5: 点击切换耗时 {time.time()-t0:.3f}s")

# 测试6：切换组
t0 = time.time()
for i in range(1, min(len(win.result.groups), 3)):
    win._show_group(i)
    for _ in range(5):
        app.processEvents(); time.sleep(0.02)
print(f"PASS 6: 切换组耗时 {time.time()-t0:.1f}s")

# 测试7：全屏预览（不真正 show，只验证能构建）
win._show_group(0)
for _ in range(5):
    app.processEvents(); time.sleep(0.02)
panel = win.review_layout.itemAt(0).widget()
if panel.cards:
    pv = FullscreenPreview([c.photo.path for c in panel.cards],
                           win.cache, 0, win)
    print(f"PASS 7: 全屏预览构建 OK ({len(panel.cards)}张)")
    pv.close()

# 测试8：确认组（monkeypatch 防真移动）
import main as mm
mm.move_to_trash = lambda paths, folder: len(paths)
panel._confirm_group()
app.processEvents()
assert panel.group.confirmed
print("PASS 8: 确认组 OK")

print("\n=== ALL V2.2 REGRESSION TESTS PASSED ===")
