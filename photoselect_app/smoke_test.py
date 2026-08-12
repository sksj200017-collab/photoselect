#!/usr/bin/env python3
"""GUI 冒烟测试：用 offscreen 模式实例化主窗口，验证核心流程"""
import os
import sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication([])
win = MainWindow()
win.show()

# 模拟选择文件夹 + 分析
win.folder_label.setText(r"E:\尼康照片\美国")
win.threshold_spin.setValue(7)
win._start_analysis()

# 等分析线程完成（最多 120 秒）
import time
deadline = time.time() + 120
while win.result is None and time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)

if win.result is None:
    print("FAIL: 分析未完成")
    sys.exit(1)

print(f"OK: 分析完成 {len(win.result.photos)} 张, "
      f"{len(win.result.groups)} 组")
print(f"OK: 工作组区可见={win.workspace.isVisible()}")

# 测试切换到组 0
win._show_group(0)
app.processEvents()
print("OK: 显示组0")

# 模拟用户选择：点击"仅保留推荐"按钮
panel = win.group_panel_holder.findChild(type(win.group_panel_holder.layout().itemAt(0).widget()))
print(f"OK: GroupPanel 类型 = {type(panel).__name__}")

# 测试统计逻辑
win._collect_choices()
kept = win.user_choices.get(0)
print(f"OK: 组0 用户选择 = {kept}")

# 测试 nav_group
win._nav_group(1)
app.processEvents()
print(f"OK: 导航到组1, 当前索引={win.current_group_index}")

print("\n=== ALL SMOKE TESTS PASSED ===")
