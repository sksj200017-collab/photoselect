#!/usr/bin/env python3
"""
PhotoSelect — 照片优选工具 (GUI v2.3)
- 文件类型过滤（JPG/RAW/全部）
- 分析完成 → 分组总览（可手动加入/移出组）→ 大图选图
- 全屏预览：保留/删除按钮 + 双击纯放大
- 每组确认后可撤销（从 待删除 移回）
- 照片>6张滚动翻页
- 导出前弹窗勾选范围
"""

import os
import sys
from collections import OrderedDict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFileDialog, QProgressBar, QSlider,
    QFrame, QMessageBox, QScrollArea, QSizePolicy, QStackedWidget,
    QComboBox, QLineEdit, QDialog, QCheckBox, QDialogButtonBox, QSpinBox,
    QAbstractSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QEvent
from PySide6.QtGui import QPixmap, QImage, QFont, QIcon, QKeySequence, QShortcut

from dedup_engine import (
    Analyzer, ThumbnailCache, move_to_trash, restore_from_trash, copy_kept,
    TRASH_DIR_NAME, DEFAULT_THRESHOLD, MODE_STRICT, MODE_SUBJECT,
    Group, FILTER_JPG, FILTER_RAW, FILTER_ALL, build_jpg_raw_pairs,
    count_jpg_raw_pairs,
)

APP_NAME = "PhotoSelect 照片优选"
APP_VERSION = "2.12.12"

# ── Lightroom 风格黑底深色主题 ────────────────────────────────────
QSS = """
QMainWindow, QWidget { background: #1e1e1e; color: #e0e0e0;
    font-family: "Microsoft YaHei"; font-size: 13px; }
QPushButton {
    background: #333333; color: #e0e0e0;
    border: 1px solid #555555; border-radius: 6px;
    padding: 8px 18px; font-weight: bold;
}
QPushButton:hover { background: #444444; border-color: #888888; }
QPushButton:pressed { background: #2a7de1; color: white; }
QPushButton:disabled { color: #666666; border-color: #444444; background: #2a2a2a; }
QPushButton#primary {
    background: #2a7de1; color: white; border: none;
    font-size: 14px; padding: 10px 26px;
}
QPushButton#primary:hover { background: #3a8df1; }
QPushButton#success {
    background: #2e9e5b; color: white; border: none;
    font-size: 14px; padding: 10px 26px;
}
QPushButton#success:hover { background: #3aae6b; }
QPushButton#warning {
    background: #d97706; color: white; border: none;
    font-size: 14px; padding: 10px 26px;
}
QPushButton#warning:hover { background: #e98716; }
QPushButton#danger {
    background: #dc2626; color: white; border: none;
    font-size: 14px; padding: 10px 26px;
}
QPushButton#danger:hover { background: #ef4444; }
QPushButton#ghost { background: transparent; border: 1px solid #555; }
QComboBox {
    background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
    border-radius: 6px; padding: 6px 10px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #2a2a2a; color: #e0e0e0;
    selection-background-color: #2a7de1;
}
QLineEdit {
    background: #2a2a2a; border: 1px solid #444; border-radius: 6px;
    padding: 6px 10px; color: #e0e0e0;
}
QProgressBar {
    border: 1px solid #444; border-radius: 5px; background: #2a2a2a;
    text-align: center; height: 22px; font-weight: bold;
}
QProgressBar::chunk { background: #2a7de1; border-radius: 4px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #555; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QSlider::groove:horizontal { height: 6px; background: #444; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #2a7de1; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; height: 18px; margin: -6px 0;
    background: #ddd; border-radius: 9px; }
QSlider::handle:horizontal:hover { background: white; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QDialog { background: #1e1e1e; }
"""


def asset(name):
    for base in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
                 os.path.join(getattr(sys, '_MEIPASS', ''), 'assets')):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)


# ── 音效播放（俏皮提示音） ────────────────────────────────────────
_sound_player = None
_pix_cache = OrderedDict()   # 进程内 QPixmap LRU 缓存（加速翻页/重建卡片）

def play_success_sound():
    """播放俏皮提示音（QSoundEffect，支持 wav）"""
    global _sound_player
    try:
        if _sound_player is None:
            from PySide6.QtMultimedia import QSoundEffect
            wav = asset("sounds/success.wav")
            if not wav or not os.path.exists(wav):
                return
            _sound_player = QSoundEffect()
            _sound_player.setSource(QUrl.fromLocalFile(wav))
            _sound_player.setVolume(1.0)
        _sound_player.play()
    except Exception:
        pass


# ── 自定义弹窗（播放专属音效，不触发 Windows 系统音） ────────────
def _ps_dialog(parent, title, text, kind="info", buttons=QMessageBox.Ok):
    """自定义消息框：不触发系统提示音，统一播放专属音效。
    支持按钮：QMessageBox.Ok（单按钮）或 QMessageBox.Yes|QMessageBox.No（确认/取消）"""
    from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QHBoxLayout
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumWidth(420)
    dlg.setStyleSheet(
        "QDialog { background:#1e1e1e; }"
        "QLabel { color:#e0e0e0; font-size:13px; }")
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(12)

    icon = "✅" if kind == "info" else ("❌" if kind == "critical" else "⚠️")
    msg = QLabel(f"{icon}  {text}")
    msg.setWordWrap(True)
    msg.setStyleSheet("font-size:14px; line-height:1.5;")
    lay.addWidget(msg)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    result = [QMessageBox.No]
    if buttons & QMessageBox.Yes:
        yes_btn = QPushButton("确定")
        yes_btn.setObjectName("danger" if kind == "warning" else "primary")
        yes_btn.setFixedWidth(110)
        yes_btn.clicked.connect(lambda: (result.__setitem__(0, QMessageBox.Yes),
                                         dlg.accept()))
        btn_row.addWidget(yes_btn)
    ok_btn = QPushButton("好的" if not (buttons & QMessageBox.Yes) else "取消")
    ok_btn.setObjectName("ghost")
    ok_btn.setFixedWidth(110)
    ok_btn.clicked.connect(lambda: (result.__setitem__(0, QMessageBox.No),
                                    dlg.accept()))
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)

    play_success_sound()
    dlg.exec()
    return result[0]


def _patch_message_boxes():
    """把所有 QMessageBox 静态方法替换为自定义弹窗（消系统音+播专属音效）"""
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: _ps_dialog(parent, title, text, "info"))
    QMessageBox.warning = staticmethod(
        lambda parent, title, text, *a, **k: _ps_dialog(
            parent, title, text, "warning",
            buttons=(a[0] if a and isinstance(a[0], QMessageBox.StandardButton)
                     else QMessageBox.Ok)))
    QMessageBox.critical = staticmethod(
        lambda parent, title, text, *a, **k: _ps_dialog(parent, title, text, "critical"))
    QMessageBox.question = staticmethod(
        lambda parent, title, text, *a, **k: _ps_dialog(
            parent, title, text, "warning",
            buttons=(a[0] if a and isinstance(a[0], QMessageBox.StandardButton)
                     else QMessageBox.Yes | QMessageBox.No)))


# ── 启动许可提醒弹窗 ──────────────────────────────────────────────
class LicenseReminderDialog(QDialog):
    """每次启动提醒：免费个人使用 / 禁商用 / 联系方式"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用须知")
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        title = QLabel("📸 PhotoSelect 使用须知")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#2a7de1;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        body = QLabel(
            "使用前请先阅读 README 说明\n\n"
            "· 免费个人使用 · 禁止商业用途 · by nfd\n"
            "· 商用授权或 Bug 反馈请邮件\n"
            "   745936837@qq.com\n"
            "· 或加微信 13917034098\n\n"
            "⚠️ 重要提醒：\n"
            "被标记删除的照片会移入原文件夹内的\n"
            "「待删除」文件夹（可恢复），\n"
            "确认无误后再手动删除释放空间。")
        body.setStyleSheet("color:#ddd; font-size:13px; line-height:1.7;")
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("我知道了")
        ok_btn.setObjectName("primary")
        ok_btn.setFixedWidth(140)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        play_success_sound()


# ── 分析线程 ──────────────────────────────────────────────────────
class AnalyzeThread(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, folder, threshold, mode, file_filter,
                 parent=None, enable_blur=False, blur_threshold=None):
        super().__init__(parent)
        self.folder = folder
        self.threshold = threshold
        self.mode = mode
        self.file_filter = file_filter
        self.enable_blur = enable_blur
        self.blur_threshold = blur_threshold

    def run(self):
        try:
            analyzer = Analyzer(
                threshold=self.threshold, mode=self.mode,
                file_filter=self.file_filter,
                progress_cb=lambda c, t, m: self.progress.emit(c, t, m))
            result = analyzer.analyze(self.folder,
                enable_blur=self.enable_blur,
                blur_threshold=self.blur_threshold)
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


# ── 大图卡片 ──────────────────────────────────────────────────────
class BigPhotoCard(QFrame):
    clicked = Signal(object)
    double_clicked = Signal(object)

    def __init__(self, photo, cache, keep=True, show_mark=True, parent=None, blurry=False):
        super().__init__(parent)
        self.photo = photo
        self.cache = cache
        self._keep = keep
        self._show_mark = show_mark
        self._orig_pixmap = None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 150)

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(6, 6, 6, 6)
        self.lay.setSpacing(0)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img_label.setStyleSheet("background:#111111; border-radius:4px;")
        self.lay.addWidget(self.img_label, 1)
        # 模糊照片：右上角覆盖 ⚠ 徽标（不遮挡底部文件名；有 ✓/✗ 标记时也显示）
        self.blur_badge = None
        if blurry:
            self.blur_badge = QLabel("⚠ 模糊", self)
            self.blur_badge.setStyleSheet(
                "color:#f59e0b; font-weight:bold; font-size:12px; "
                "background:rgba(42,26,0,220); border:1px solid #d97706; "
                "border-radius:4px; padding:2px 6px;")
            self.blur_badge.adjustSize()
            self.blur_badge.hide()

        info = QHBoxLayout()
        _disp = getattr(photo, 'display_name', None) or photo.name
        self.name_label = QLabel(_disp)
        self.name_label.setStyleSheet("color:#aaa; font-size:11px;")
        info.addWidget(self.name_label)
        info.addStretch()
        self.mark_label = QLabel()
        self.mark_label.setStyleSheet(self._mark_style())
        if show_mark:
            self.mark_label.setText("✓ 保留" if keep else "✗ 删除")
            info.addWidget(self.mark_label)
        self.lay.addLayout(info)

        self._update_frame_style()
        self._load_image()
        QTimer.singleShot(0, self.refresh_image)
        # 布局激活后主动定位右上角徽标（不能只靠 resizeEvent——
        # 首次 resize 时 badge 可能还没创建）
        QTimer.singleShot(0, self._position_blur_badge)

    def _position_blur_badge(self):
        """把 ⚠ 徽标定位到图片区右上角并显示"""
        if self.blur_badge is None:
            return
        geo = self.img_label.geometry()
        if geo.width() <= 0 or geo.height() <= 0:
            return   # 布局未激活，等下一次
        bw, bh = self.blur_badge.width(), self.blur_badge.height()
        self.blur_badge.move(geo.right() - bw - 8, geo.top() + 8)
        self.blur_badge.show()
        self.blur_badge.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口变化时重新定位右上角徽标
        self._position_blur_badge()

    def _mark_style(self):
        if self._keep:
            return ("color:#4ade80; font-weight:bold; font-size:13px; "
                    "background:#1a3a2a; border-radius:4px; padding:2px 8px;")
        return ("color:#f87171; font-weight:bold; font-size:13px; "
                "background:#3a1a1a; border-radius:4px; padding:2px 8px;")

    def _update_frame_style(self):
        if self._keep:
            self.setStyleSheet(
                "QFrame { background:#1e1e1e; border:3px solid #2e9e5b;"
                "border-radius:8px; }")
        else:
            self.setStyleSheet(
                "QFrame { background:#1e1e1e; border:3px solid #555555;"
                "border-radius:8px; }")

    @property
    def keep(self):
        return self._keep

    def set_keep(self, keep):
        self._keep = keep
        if self._show_mark:
            self.mark_label.setText("✓ 保留" if keep else "✗ 删除")
        self.mark_label.setStyleSheet(self._mark_style())
        self._update_frame_style()

    def toggle(self):
        self.set_keep(not self._keep)

    def _load_image(self):
        # 进程内 QPixmap 缓存（避免翻页重建时重复解码）
        key = ("pix", self.photo.path)
        pix = _pix_cache.get(key)
        if pix is not None:
            _pix_cache.move_to_end(key)   # LRU 更新
        if pix is None:
            img = self.cache.get(self.photo.path, 1200)
            if img is None:
                self.img_label.setText("无法加载")
                return
            img = img.convert('RGB')
            data = img.tobytes('raw', 'RGB')
            qimg = QImage(data, img.width, img.height, img.width * 3,
                          QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            # LRU 淘汰最久未用的（而非全清，避免抖动）
            _pix_cache[key] = pix
            _pix_cache.move_to_end(key)
            while len(_pix_cache) > 150:
                _pix_cache.popitem(last=False)
        self._orig_pixmap = pix

    def refresh_image(self):
        if self._orig_pixmap is None:
            return
        target_w = max(self.img_label.width() - 8, 60)
        target_h = max(self.img_label.height() - 8, 60)
        pix = self._orig_pixmap.scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_image()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_image()
        self._position_blur_badge()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self)
        super().mouseDoubleClickEvent(event)


# ── 全屏预览（保留/删除按钮 + 双击放大） ─────────────────────────
class FullscreenPreview(QDialog):
    def __init__(self, paths, cache, keep_paths, start_index=0, parent=None,
                 preview_only=False, selected_paths=None, on_select_toggled=None):
        super().__init__(parent)
        self.paths = paths
        self.cache = cache
        self.keep_paths = set(keep_paths)   # 当前保留的 path 集合
        self.index = start_index
        self.zoom = False
        self.preview_only = preview_only    # 纯预览：不显示保留/删除按钮
        self.selected_paths = selected_paths          # 模糊预览的选中集合（引用）
        self.on_select_toggled = on_select_toggled    # 切换选中回调
        self.setWindowTitle("全屏预览")
        self.resize(1200, 800)
        # app 级事件过滤器：任何焦点状态下 ←→ 翻页都有效
        QApplication.instance().installEventFilter(self)

        self.setStyleSheet(
            "QDialog { background:#000000; }"
            "QPushButton { background:#333; color:#eee; border:1px solid #555;"
            "border-radius:6px; padding:8px 16px; font-weight:bold; }"
            "QPushButton:hover { background:#444; }"
            "QPushButton#keep { background:#2e9e5b; color:white; }"
            "QPushButton#del { background:#dc2626; color:white; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        self.counter_label = QLabel("")
        self.counter_label.setStyleSheet("color:#aaa; font-size:14px;")
        top.addWidget(self.counter_label)
        top.addStretch()
        self.zoom_label = QLabel("单击左/右半屏翻页 · 双击放大/还原 · ←→键翻页")
        self.zoom_label.setStyleSheet("color:#666; font-size:12px;")
        top.addWidget(self.zoom_label)
        self.close_btn = QPushButton("✕ 关闭 (Esc)")
        self.close_btn.clicked.connect(self.close)
        top.addWidget(self.close_btn)
        layout.addLayout(top)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background:#000;")
        self.image_label.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.image_label, 1)

        bottom = QHBoxLayout()
        self.prev_btn = QPushButton("◀ 上一张")
        self.next_btn = QPushButton("下一张 ▶")
        self.prev_btn.clicked.connect(lambda: self._nav(-1))
        self.next_btn.clicked.connect(lambda: self._nav(1))
        # NoFocus：防止 ←→ 键被按钮焦点吃掉（翻页键始终有效）
        self.prev_btn.setFocusPolicy(Qt.NoFocus)
        self.next_btn.setFocusPolicy(Qt.NoFocus)
        bottom.addWidget(self.prev_btn)
        bottom.addWidget(self.next_btn)
        bottom.addStretch()
        # 单个切换按钮：待删除 ⇄ 已保留（学习模糊预览的选中按钮交互）
        self.toggle_btn = QPushButton()
        self.toggle_btn.clicked.connect(self._toggle_keep)
        self.toggle_btn.setFocusPolicy(Qt.NoFocus)
        self.toggle_btn.setToolTip("点击切换这张照片的保留/删除状态（退出全屏后依然生效）")
        bottom.addWidget(self.toggle_btn)
        # 纯预览模式：隐藏保留/删除切换按钮（模糊预览等场景）
        if preview_only:
            self.toggle_btn.setVisible(False)
            self.zoom_label.setText("单击左/右半屏翻页 · 双击放大/还原 · ←→键翻页")
            # 模糊预览：加「选中/取消选中」按钮（退出后状态同步回对话框）
            if self.on_select_toggled is not None:
                self.select_btn = QPushButton("⭕ 选中")
                self.select_btn.setObjectName("keep")
                self.select_btn.clicked.connect(self._toggle_select)
                self.select_btn.setFocusPolicy(Qt.NoFocus)
                self.select_btn.setToolTip("标记/取消标记这张照片为选中（退出全屏后依然生效）")
                bottom.addWidget(self.select_btn)
        layout.addLayout(bottom)

        self._show()

    def _toggle_select(self):
        path = self.paths[self.index]
        if self.on_select_toggled is not None:
            self.on_select_toggled(path)
        self._update_select_btn()

    def _update_select_btn(self):
        if not hasattr(self, 'select_btn'):
            return
        path = self.paths[self.index]
        is_sel = (self.selected_paths is not None
                  and path in self.selected_paths)
        self.select_btn.setText("✓ 已选中" if is_sel else "⭕ 选中")
        self.select_btn.setStyleSheet(
            "background:#1a3a2a; color:#4ade80; border:1px solid #2e9e5b;"
            if is_sel else
            "background:#2e9e5b; color:white;")

    def _show(self):
        path = self.paths[self.index]
        self._display()
        name = os.path.basename(path)
        self.counter_label.setText(
            f"{self.index + 1} / {len(self.paths)} · {name}")
        # 单张照片时隐藏翻页按钮（避免出现禁用的灰按钮）
        single = len(self.paths) <= 1
        self.prev_btn.setVisible(not single)
        self.next_btn.setVisible(not single)
        if not single:
            self.prev_btn.setEnabled(self.index > 0)
            self.next_btn.setEnabled(self.index < len(self.paths) - 1)
        # 纯预览模式不更新保留/删除按钮状态（但更新选中按钮）
        if self.preview_only:
            self._update_select_btn()
            return
        # 更新切换按钮状态（表示当前照片的状态，点击切换）
        is_keep = path in self.keep_paths
        if is_keep:
            self.toggle_btn.setText("✓ 已保留（点击改为删除）")
            self.toggle_btn.setStyleSheet(
                "background:#2e9e5b; color:white; font-weight:bold;")
        else:
            self.toggle_btn.setText("✗ 待删除（点击改为保留）")
            self.toggle_btn.setStyleSheet(
                "background:#dc2626; color:white; font-weight:bold;")

    def _display(self):
        path = self.paths[self.index]
        img = self.cache.get(path, 1920)
        if img is None:
            return
        img = img.convert('RGB')
        data = img.tobytes('raw', 'RGB')
        qimg = QImage(data, img.width, img.height, img.width * 3,
                      QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        if self.zoom:
            # 100% 原图（超出屏幕可滚动）——简化为适配屏幕宽度
            max_w = self.width() - 40
            max_h = self.height() - 140
            pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
        else:
            max_w = self.width() - 40
            max_h = self.height() - 140
            pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)

    def _nav(self, delta):
        self.index = max(0, min(len(self.paths) - 1, self.index + delta))
        self.zoom = False
        self._show()
        # 预加载相邻图片，翻页更丝滑
        for off in (1, -1):
            i = self.index + off
            if 0 <= i < len(self.paths):
                try:
                    self.cache.get(self.paths[i], 1920)
                except Exception:
                    pass

    def _toggle_keep(self):
        """切换当前照片的保留/删除状态"""
        path = self.paths[self.index]
        if path in self.keep_paths:
            self.keep_paths.discard(path)
        else:
            self.keep_paths.add(path)
        self._show()

    def mousePressEvent(self, event):
        """单击 = 翻页：点左半屏上一张，右半屏下一张（双击仍放大）"""
        if event.button() == Qt.LeftButton:
            # 延迟判断，等双击信号（双击会先触发两次单击）
            pos = event.position()
            self._click_half = 'left' if pos.x() < self.width() / 2 else 'right'
            self._click_timer = QTimer()
            self._click_timer.setSingleShot(True)
            self._click_timer.timeout.connect(self._do_click_nav)
            self._click_timer.start(220)
            return
        super().mousePressEvent(event)

    def _do_click_nav(self):
        """执行单击翻页（双击已触发则取消）"""
        if hasattr(self, '_click_half'):
            self._nav(-1 if self._click_half == 'left' else 1)
            self._click_half = None

    def mouseDoubleClickEvent(self, event):
        """双击 = 放大/还原（取消待执行的单击翻页）"""
        self._click_half = None
        if hasattr(self, '_click_timer'):
            self._click_timer.stop()
        self.zoom = not self.zoom
        self._display()
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, obj, event):
        """app 级拦截 ←→：任何焦点状态下翻页都有效"""
        if not self.isVisible():
            return False
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Left:
                self._nav(-1)
                return True
            if event.key() == Qt.Key_Right:
                self._nav(1)
                return True
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self._nav(-1)
        elif event.key() == Qt.Key_Right:
            self._nav(1)
        else:
            super().keyPressEvent(event)


# ── 大图选图面板（滚动翻页 + 撤销） ───────────────────────────────
class ReviewPanel(QWidget):
    confirmed = Signal(int)
    undone = Signal(int)
    confirmed_with_msg = Signal(int, str)   # (组索引, 提示消息)
    reset_all_requested = Signal()

    def __init__(self, group, cache, group_index, parent=None, pairs=None):
        super().__init__(parent)
        self.group = group
        self.cache = cache
        self.group_index = group_index
        self.pairs = pairs or {}   # JPG+RAW 配对映射
        self.cards = []
        self.page = 0
        self.per_page = 6          # 每页最多 6 张大图
        self._all_kept = False     # 是否处于「全选(保留全部)」状态
        # 恢复保留选择：已确认→kept_paths；未确认→pending（若存在）；否则推荐
        if group.kept_paths is not None:
            self.keep_paths = set(group.kept_paths)
        elif group.pending_kept_paths is not None:
            self.keep_paths = set(group.pending_kept_paths)
        elif group.confirmed and group.user_keep is not None:
            self.keep_paths = {group.user_keep.path}
        elif group.confirmed:
            self.keep_paths = set()   # 全删组：保留为空
        else:
            self.keep_paths = set()   # 不再自动推荐

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(8)

        # 顶部
        top = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size:16px; font-weight:bold;")
        top.addWidget(self.title_label)
        top.addStretch()
        self.sel_all_btn = QPushButton("☑ 全选（保留本组全部）")
        self.sel_all_btn.setObjectName("primary")
        self.sel_all_btn.setToolTip("保留本组所有照片（删除 0 张）")
        self.sel_all_btn.clicked.connect(self._select_all_keep)
        self.sel_all_btn.setFocusPolicy(Qt.NoFocus)
        top.addWidget(self.sel_all_btn)
        self.reset_btn = QPushButton("↺ 重置全部筛选")
        self.reset_btn.setObjectName("danger")
        self.reset_btn.setToolTip(
            "一键撤销所有确认：把已移入「待删除」的照片全部恢复，重新开始筛选")
        self.reset_btn.clicked.connect(self._reset_all)
        top.addWidget(self.reset_btn)
        outer.addLayout(top)

        hint = QLabel("🖱 点击切换保留/删除 · 双击放大 · 滚轮/按钮翻页 · ←→键切组 · 回车确认本组")
        hint.setStyleSheet("color:#888; font-size:12px;")
        outer.addWidget(hint)

        # 页面上方信息栏（确认/撤销提示，不弹窗）
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(
            "color:#4ade80; font-size:13px; background:#1a2a1a;"
            "border:1px solid #2e9e5b; border-radius:6px; padding:8px;")
        self.notice_label.setVisible(False)
        outer.addWidget(self.notice_label)

        # 分页条
        page_bar = QHBoxLayout()
        self.prev_page_btn = QPushButton("◀ 上一页")
        self.prev_page_btn.setObjectName("ghost")
        self.prev_page_btn.setFocusPolicy(Qt.NoFocus)
        self.page_label = QLabel("")
        self.page_label.setStyleSheet("color:#aaa; padding:0 10px;")
        self.next_page_btn = QPushButton("下一页 ▶")
        self.next_page_btn.setObjectName("ghost")
        self.next_page_btn.setFocusPolicy(Qt.NoFocus)
        self.prev_page_btn.clicked.connect(lambda: self._set_page(self.page - 1))
        self.next_page_btn.clicked.connect(lambda: self._set_page(self.page + 1))
        page_bar.addStretch()
        page_bar.addWidget(self.prev_page_btn)
        page_bar.addWidget(self.page_label)
        page_bar.addWidget(self.next_page_btn)
        page_bar.addStretch()
        outer.addLayout(page_bar)

        # 大图网格
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        outer.addLayout(self.grid, 1)

        # 底部：撤销 + 确认
        bottom = QHBoxLayout()
        self.counter_label = QLabel("")
        self.counter_label.setStyleSheet("color:#aaa; font-size:13px;")
        bottom.addWidget(self.counter_label)
        bottom.addStretch()

        # 撤销/确认按钮容器（动态切换，由 _rebuild 管理）
        self.bottom_btns = QHBoxLayout()
        bottom.addLayout(self.bottom_btns)
        outer.addLayout(bottom)

        # 回车 = 确认本组（第 4 点快捷键）
        self.enter_shortcut = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.enter_shortcut.activated.connect(self._shortcut_confirm)
        self.enter_shortcut2 = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.enter_shortcut2.activated.connect(self._shortcut_confirm)

        # 全部按钮 NoFocus：←→ 始终用于翻页/切组，不被按钮吃掉
        for _b in self.findChildren(QPushButton):
            _b.setFocusPolicy(Qt.NoFocus)

        self._rebuild()

    # ── 构建 ────────────────────────────────────────────────────
    def _show_notice(self, text):
        """在页面上方显示提示信息（不弹窗），4 秒后自动隐藏"""
        self.notice_label.setText(text)
        self.notice_label.setVisible(True)
        QTimer.singleShot(4000, lambda: self.notice_label.setVisible(False))

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        photos = self.group.photos
        n = len(photos)
        total_pages = max(1, (n + self.per_page - 1) // self.per_page)
        if self.page >= total_pages:
            self.page = total_pages - 1

        # 每页最多 per_page 张
        start = self.page * self.per_page
        end = min(n, start + self.per_page)
        page_photos = photos[start:end]
        np_ = len(page_photos)

        # 列数：1-2=2, 3-4=2, 5-6=3
        if np_ <= 2:
            cols = 2
        elif np_ <= 4:
            cols = 2
        else:
            cols = 3
        rows = (np_ + cols - 1) // cols

        for i, photo in enumerate(page_photos):
            card = BigPhotoCard(photo, self.cache,
                                keep=(photo.path in self.keep_paths),
                                blurry=getattr(photo, 'is_blurry', False))
            card.clicked.connect(self._on_clicked)
            card.double_clicked.connect(self._on_double_clicked)
            self.cards.append(card)
            self.grid.addWidget(card, i // cols, i % cols)
            self.grid.setColumnStretch(i % cols, 1)
            self.grid.setRowStretch(i // cols, 1)

        # 更新状态
        n_keep = len(self.keep_paths)
        n_del = n - n_keep
        status = "已确认 ✓" if self.group.confirmed else "待确认"
        self.title_label.setText(
            f"组 {self.group_index + 1} · {n}张相似照片 · {status}")
        self.counter_label.setText(f"保留 {n_keep} 张 · 删除 {n_del} 张")
        self.page_label.setText(f"第 {self.page + 1}/{total_pages} 页"
                                f"（{np_}张）")
        self.prev_page_btn.setEnabled(self.page > 0)
        self.next_page_btn.setEnabled(self.page < total_pages - 1)
        # 动态切换 撤销/确认 按钮
        self._rebuild_bottom_buttons()

    def _rebuild_bottom_buttons(self):
        """根据确认状态动态重建底部按钮（确认↔撤销即时切换）"""
        # 清空按钮容器
        while self.bottom_btns.count():
            item = self.bottom_btns.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if self.group.confirmed:
            undo_btn = QPushButton("↩ 撤销本组确认")
            undo_btn.setObjectName("danger")
            undo_btn.clicked.connect(self._undo_group)
            self.bottom_btns.addWidget(undo_btn)
            confirm_btn = QPushButton("✓ 本组已确认")
            confirm_btn.setEnabled(False)
            confirm_btn.setObjectName("success")
            self.bottom_btns.addWidget(confirm_btn)
        else:
            n_keep = len(self.keep_paths)
            n_del = len(self.group.photos) - n_keep
            confirm_btn = QPushButton(
                f"✓ 确认本组（保留 {n_keep} 张 · 删除 {n_del} 张）")
            confirm_btn.setObjectName("success")
            confirm_btn.clicked.connect(self._confirm_group)
            self.bottom_btns.addWidget(confirm_btn)
        # 引用供 _update_counts 使用
        self.confirm_btn = self.bottom_btns.itemAt(
            self.bottom_btns.count() - 1).widget()
        # 动态创建的按钮也要 NoFocus（否则 ←→ 被按钮焦点吃掉）
        for _i in range(self.bottom_btns.count()):
            _w = self.bottom_btns.itemAt(_i).widget()
            if _w is not None:
                _w.setFocusPolicy(Qt.NoFocus)

    def _set_page(self, page):
        n = len(self.group.photos)
        total_pages = max(1, (n + self.per_page - 1) // self.per_page)
        self.page = max(0, min(total_pages - 1, page))
        self._rebuild()

    def has_prev_page(self):
        return self.page > 0

    def has_next_page(self):
        n = len(self.group.photos)
        total_pages = max(1, (n + self.per_page - 1) // self.per_page)
        return self.page < total_pages - 1

    def wheelEvent(self, event):
        """滚轮翻页（节流：连续滚动合并，避免卡顿）"""
        delta = event.angleDelta().y()
        # 累计方向，200ms 内只翻一次页
        if not hasattr(self, '_wheel_accum'):
            self._wheel_accum = 0
            self._wheel_timer = None
        self._wheel_accum += delta
        if self._wheel_timer is None:
            self._wheel_timer = QTimer()
            self._wheel_timer.setSingleShot(True)
            self._wheel_timer.timeout.connect(self._flush_wheel)
        self._wheel_timer.start(200)
        event.accept()

    def _flush_wheel(self):
        """执行累计的滚轮翻页（一次）"""
        acc = getattr(self, '_wheel_accum', 0)
        self._wheel_accum = 0
        self._wheel_timer = None
        if acc > 0:
            self._set_page(self.page - 1)
        elif acc < 0:
            self._set_page(self.page + 1)

    # ── 交互 ────────────────────────────────────────────────────
    def _update_sel_all_btn(self):
        """根据是否已全保留实时更新「全选/取消全选」按钮"""
        total = len(self.group.photos)
        n = len(self.keep_paths)
        if total > 0 and n >= total:
            self.sel_all_btn.setText("↺ 取消全选")
            self._all_kept = True
        else:
            self.sel_all_btn.setText("☑ 全选（保留本组全部）")
            self._all_kept = False

    def _on_clicked(self, card):
        if self.group.confirmed:
            return
        card.toggle()
        if card.keep:
            self.keep_paths.add(card.photo.path)
        else:
            self.keep_paths.discard(card.photo.path)
        self.group.pending_kept_paths = set(self.keep_paths)   # 跨面板保存
        self._update_sel_all_btn()
        self._update_counts()

    def _on_double_clicked(self, card):
        paths = [c.photo.path for c in self.cards]
        idx = paths.index(card.photo.path)
        preview = FullscreenPreview(paths, self.cache, self.keep_paths, idx, self)
        preview.exec()
        # 全屏预览修改了保留状态（无论怎么关闭都同步回传）
        if preview.keep_paths != self.keep_paths:
            self.keep_paths = preview.keep_paths
            self.group.pending_kept_paths = set(self.keep_paths)
            self._rebuild()

    def _update_counts(self):
        n_keep = len(self.keep_paths)
        n_del = len(self.group.photos) - n_keep
        self.counter_label.setText(f"保留 {n_keep} 张 · 删除 {n_del} 张")
        if not self.group.confirmed:
            self.confirm_btn.setText(
                f"✓ 确认本组（保留 {n_keep} 张 · 删除 {n_del} 张）")
        self._update_sel_all_btn()

    def _select_all_keep(self):
        """全选：保留本组所有照片；再次点击=取消全选（全部不保留）"""
        if self.group.confirmed:
            return
        if self._all_kept:
            # 取消全选：全部不保留
            self.keep_paths.clear()
            self.group.pending_kept_paths = set()
            for card in self.cards:
                card.set_keep(False)
        else:
            self.keep_paths = {p.path for p in self.group.photos}
            self.group.pending_kept_paths = set(self.keep_paths)
            for card in self.cards:
                card.set_keep(True)
        self._update_sel_all_btn()
        self._update_counts()

    def _reset_all(self):
        """一键重置全部筛选：撤销所有确认，恢复所有照片，重新开始"""
        self.reset_all_requested.emit()

    def _shortcut_confirm(self):
        """回车快捷键：确认本组（已确认则撤销）"""
        if self.group.confirmed:
            self._undo_group()
        else:
            self._confirm_group()

    def _confirm_group(self):
        if self.group.confirmed:
            return
        # JPG+RAW 配对：保留 JPG 则 RAW 一起保留；删除 JPG 则 RAW 一起删
        keep = set(self.keep_paths)
        for k in list(keep):
            if k in self.pairs:
                keep.add(self.pairs[k])
        # 允许全删（keep_paths 可为空 = 整组都不要）
        self.group.user_keep = next(
            (p for p in self.group.photos if p.path in self.keep_paths),
            None)
        self.group.kept_paths = keep              # 保存所有保留照片（含 RAW 对）
        self.group.pending_kept_paths = None

        folder = os.path.dirname(self.group.photos[0].path)
        to_delete = [p.path for p in self.group.photos
                     if p.path not in keep]
        for p in list(to_delete):
            if p in self.pairs and self.pairs[p] not in keep:
                to_delete.append(self.pairs[p])
        n_files = move_to_trash(to_delete, folder)
        n_photos = self._count_photos(to_delete)   # JPG+RAW 对算 1 张
        self.group.confirmed = True
        self.confirmed.emit(self.group_index)
        play_success_sound()

        # 提示信息通过信号传给主窗口（跳转后显示在新面板上，不弹窗）
        msg = (f"✅ 本组已确认"
               + (f"：保留 {len(self.keep_paths)} 张" if self.keep_paths
                  else "：全部移入「待删除」（空组标记）")
               + f"，其余 {n_photos} 张已移入「{TRASH_DIR_NAME}」\n"
                 f"💡 点「↩ 撤销本组确认」可恢复。")
        self.confirmed_with_msg.emit(self.group_index, msg)
        self._rebuild()

    def _count_photos(self, paths):
        """按「照片」计数：JPG+RAW 对算 1 张（实际文件一起移动）"""
        seen = set()
        n = 0
        for p in paths:
            if p in seen:
                continue
            seen.add(p)
            n += 1
            if p in self.pairs:
                seen.add(self.pairs[p])
        return n

    def _undo_group(self):
        """撤销确认：把照片从 待删除 移回"""
        if not self.group.confirmed:
            return
        folder = os.path.dirname(self.group.photos[0].path)
        # 被删除的照片 = 组内不在 keep_paths 的（含 RAW 对）
        keep = set(self.keep_paths)
        for k in list(keep):
            if k in self.pairs:
                keep.add(self.pairs[k])
        deleted = [p.path for p in self.group.photos
                   if p.path not in keep]
        for p in list(deleted):
            if p in self.pairs and self.pairs[p] not in keep:
                deleted.append(self.pairs[p])
        n = restore_from_trash(deleted, folder)
        self.group.confirmed = False
        self.group.kept_paths = None
        self.group.pending_kept_paths = set(self.keep_paths)
        self.undone.emit(self.group_index)

        self._show_notice(
            f"↩ 已撤销确认：从「{TRASH_DIR_NAME}」恢复 {n} 张照片，可重新选择。")
        self._rebuild()



# ── 模糊照片预览（分析后、分组总览前）─────────────────────────────
class BlurPreviewDialog(QDialog):
    """模糊照片预览：缩略图网格 + 双击全屏 + 回车移入待删除"""
    def __init__(self, result, cache, parent=None):
        super().__init__(parent)
        self.result = result
        self.cache = cache
        self.selected_paths = set()  # 用户选中要删除的路径
        self._cards = {}
        self._deleted = []           # 已确认删除的 PhotoInfo 列表
        self._all_selected = False   # 是否处于「全选」状态（用于切换取消全选）

        photos = result.blurry_photos
        n = len(photos)
        self.setWindowTitle(f"模糊照片预览 — {n} 张可能模糊的照片")
        self.resize(1300, 820)
        self.setStyleSheet("""
            QDialog { background:#1a1a1a; }
            QPushButton { background:#333; color:#eee; border:1px solid #555;
                          border-radius:6px; padding:8px 16px; font-weight:bold; }
            QPushButton:hover { background:#444; }
        """)

        layout = QVBoxLayout(self)

        # 顶部提示
        top = QHBoxLayout()
        self.info_label = QLabel(
            f"🔍 以下 {n} 张照片可能没有对焦到主体上（模糊或手抖）。"
            "\n点击选中照片（橙色边框）→ 点「🗑 删除选中」移入待删除，"
            "或点「✓ 保留选中」其余移入待删除"
            "\n双击放大预览 · ←→键移动选择 · 未删除的进入后续筛选（带 ⚠ 标记）")
        self.info_label.setStyleSheet("color:#aaa; font-size:13px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # 网格区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:#1a1a1a; border:none; }")
        grid_widget = QWidget()
        self.grid = QGridLayout(grid_widget)
        self.grid.setSpacing(8)
        self._cols = 5
        for i, p in enumerate(photos):
            card = BigPhotoCard(p, cache, keep=False, show_mark=False,
                                blurry=getattr(p, 'is_blurry', False))
            card.setMinimumSize(220, 180)
            card.setCursor(Qt.PointingHandCursor)
            card._blur_path = p.path
            card.mousePressEvent = lambda e, c=card: self._toggle_card(c, e)
            card.mouseDoubleClickEvent = lambda e, c=card: self._preview_card(c)
            self.grid.addWidget(card, i // self._cols, i % self._cols)
            self._cards[p.path] = card
        self._photo_order = [p.path for p in photos]   # ←→ 导航顺序
        self._cursor = 0                                # 当前光标位置
        self._grid_widget = grid_widget
        self._scroll = scroll
        # app 级事件过滤器：任何控件获得焦点时 ←→ 都有效（滚动区/按钮都抢不走）
        QApplication.instance().installEventFilter(self)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, 1)

        # 底部操作栏：全选（左） + 删除选中 + 下一步（右）
        bottom = QHBoxLayout()
        self.sel_all_btn = QPushButton("☑ 全选")
        self.sel_all_btn.setStyleSheet(
            "background:#1a3a5f; color:#7dd3fc; border:1px solid #2a7de1;"
            "font-weight:bold;")
        self.sel_all_btn.setToolTip("选中所有模糊照片（再点删除选中可全部移入待删除）")
        self.sel_all_btn.clicked.connect(self._select_all)
        self.sel_all_btn.setFocusPolicy(Qt.NoFocus)
        bottom.addWidget(self.sel_all_btn)
        bottom.addStretch()
        self.counter_label = QLabel("已选 0 张")
        self.counter_label.setStyleSheet("color:#ccc; font-size:14px;")
        bottom.addWidget(self.counter_label)
        bottom.addSpacing(12)
        del_sel_btn = QPushButton("🗑 删除选中")
        del_sel_btn.setStyleSheet("background:#dc2626; color:white;"
                                  "font-weight:bold;")
        del_sel_btn.clicked.connect(self._delete_selected)
        del_sel_btn.setToolTip("选中的照片移入待删除，未选中的保留继续筛选")
        del_sel_btn.setEnabled(False)
        del_sel_btn.setFocusPolicy(Qt.NoFocus)
        self.del_sel_btn_ref = del_sel_btn
        bottom.addWidget(del_sel_btn)
        next_btn = QPushButton("下一步 →")
        next_btn.setStyleSheet("background:#2e9e5b; color:white;"
                               "font-weight:bold;")
        next_btn.setToolTip("不删除，保留所有模糊照片继续进入分组总览")
        next_btn.clicked.connect(self.accept)
        next_btn.setFocusPolicy(Qt.NoFocus)
        bottom.addWidget(next_btn)
        # 重新分析：放弃本次分析，回到主界面重新开始（保留设置）
        self.reanalyze = False
        reanalyze_btn = QPushButton("🔄 重新分析")
        reanalyze_btn.setStyleSheet("background:#333; color:#ccc;"
                                    "border:1px solid #666; font-weight:bold;")
        reanalyze_btn.setToolTip("放弃本次分析，回到主界面重新分析（保留文件夹/模式/阈值设置）")
        reanalyze_btn.clicked.connect(self._request_reanalyze)
        reanalyze_btn.setFocusPolicy(Qt.NoFocus)
        bottom.addWidget(reanalyze_btn)
        layout.addLayout(bottom)

    def _request_reanalyze(self):
        self.reanalyze = True
        self.accept()

    def _update_sel_all_btn(self):
        """根据是否已全选实时更新「全选/取消全选」按钮"""
        total = len(self._photo_order)
        n = len(self.selected_paths)
        if total > 0 and n >= total:
            self.sel_all_btn.setText("☑ 取消全选")
            self._all_selected = True
        else:
            self.sel_all_btn.setText("☑ 全选")
            self._all_selected = False

    def _toggle_card(self, card, event):
        """单击切换选中状态"""
        path = card._blur_path
        if path in self.selected_paths:
            self.selected_paths.discard(path)
            card.setStyleSheet(
                "QFrame { background:#1e1e1e; border:2px solid #555; }")
        else:
            self.selected_paths.add(path)
            card.setStyleSheet(
                "QFrame { background:#1e1e1e; border:3px solid #d97706; }")
        n_sel = len(self.selected_paths)
        self.counter_label.setText(f"已选 {n_sel} 张")
        self.del_sel_btn_ref.setEnabled(n_sel > 0)
        self._update_sel_all_btn()

    def _preview_card(self, card):
        """双击卡片 → 全屏预览（可翻页 + 直接选中，退出后状态同步回网格）"""
        paths = self._photo_order
        idx = paths.index(card._blur_path) if card._blur_path in paths else 0
        preview = FullscreenPreview(paths, self.cache, set(), idx, self,
                                    preview_only=True,
                                    selected_paths=self.selected_paths,
                                    on_select_toggled=self._on_fullscreen_toggle)
        preview.exec()
        # 退出后刷新卡片选中样式
        self._refresh_cards_selection()

    def _on_fullscreen_toggle(self, path):
        """全屏预览里切换选中状态（直接改引用集合 + 更新计数）"""
        if path in self.selected_paths:
            self.selected_paths.discard(path)
        else:
            self.selected_paths.add(path)
        n = len(self.selected_paths)
        self.counter_label.setText(f"已选 {n} 张")
        self.del_sel_btn_ref.setEnabled(n > 0)
        self._update_sel_all_btn()

    def _refresh_cards_selection(self):
        """把网格卡片边框刷新到与 selected_paths 一致"""
        for path, card in self._cards.items():
            if path in self.selected_paths:
                card.setStyleSheet(
                    "QFrame { background:#1e1e1e; border:3px solid #d97706; }")
            else:
                card.setStyleSheet(
                    "QFrame { background:#1e1e1e; border:2px solid #555; }")

    def _move_cursor(self, delta):
        """←→ 键移动选择光标"""
        if not self._photo_order:
            return
        self._cursor = (self._cursor + delta) % len(self._photo_order)
        self._update_cursor()

    def _update_cursor(self):
        """高亮光标所在的卡片并滚动到可见"""
        if not self._photo_order:
            return
        path = self._photo_order[self._cursor]
        card = self._cards.get(path)
        if card is None:
            return
        # 光标 = 蓝色边框（优先于选中橙框显示）
        if path in self.selected_paths:
            card.setStyleSheet(
                "QFrame { background:#1e1e1e; border:3px solid #3b82f6; }")
        else:
            card.setStyleSheet(
                "QFrame { background:#1e1e1e; border:3px solid #3b82f6; }")
        self._scroll.ensureWidgetVisible(card, 10, 10)

    def _remove_cards(self, paths):
        """从网格中移除指定路径的卡片（可视化反馈）"""
        for path in paths:
            card = self._cards.pop(path, None)
            if card is not None:
                card.setParent(None)
                card.deleteLater()
        # 重排网格
        remaining = [p for p in self._photo_order if p in self._cards]
        self._photo_order = remaining
        self._cursor = 0
        for i, path in enumerate(remaining):
            self.grid.addWidget(self._cards[path],
                                i // self._cols, i % self._cols)
        self._grid_widget.adjustSize()

    def _remove_paths(self, paths):
        """从 result 中移除指定路径的照片（JPG+RAW 配对一起移除）"""
        paths = set(paths)
        pairs = getattr(self.result, 'pairs', {}) or {}
        expanded = set(paths)
        for p in list(paths):
            if p in pairs:
                expanded.add(pairs[p])
        folder = os.path.dirname(list(expanded)[0])
        move_to_trash(list(expanded), folder)
        for p in list(self.result.blurry_photos):
            if p.path in paths:
                self.result.photos.pop(p.path, None)
        self.result.singles = [s for s in self.result.singles
                               if s.path not in paths]
        for g in self.result.groups:
            g.photos = [p for p in g.photos if p.path not in paths]
        for g in list(self.result.groups):
            if len(g.photos) <= 1:
                if len(g.photos) == 1:
                    self.result.singles.append(g.photos[0])
                self.result.groups.remove(g)
        self.result.blurry_photos = [
            p for p in self.result.blurry_photos if p.path not in paths]

    def _delete_selected(self):
        """删除选中：选中的移入待删除，未选中的保留继续筛选"""
        if not self.selected_paths:
            return
        n_del = len(self.selected_paths)
        n_keep = len(self.result.blurry_photos) - n_del
        ret = QMessageBox.question(
            self, "删除选中",
            f"确定将选中的 {n_del} 张移入「待删除」吗？\n"
            f"其余 {n_keep} 张保留继续筛选。\n\n（不会真正删除，可在文件夹中找到）",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        paths = set(self.selected_paths)
        self._remove_paths(paths)
        self._remove_cards(paths)
        self.selected_paths.clear()
        if not self._photo_order:
            self.accept()
            return
        self.counter_label.setText(f"已删除 {n_del} 张 · 剩余 {n_keep} 张")
        self.del_sel_btn_ref.setEnabled(False)
        self.sel_all_btn.setEnabled(True)
        self._update_sel_all_btn()
        self.info_label.setText(
            f"✅ 已删除 {n_del} 张，保留 {n_keep} 张继续筛选")

    def _select_all(self):
        """全选/取消全选（根据当前状态切换）"""
        if self._all_selected:
            # 取消全选
            for path in self._photo_order:
                card = self._cards.get(path)
                if card is not None:
                    card.setStyleSheet(
                        "QFrame { background:#1e1e1e; border:2px solid #555; }")
            self.selected_paths.clear()
            self.counter_label.setText("已选 0 张")
            self.del_sel_btn_ref.setEnabled(False)
        else:
            # 全选
            for path in self._photo_order:
                card = self._cards.get(path)
                if card is not None:
                    self.selected_paths.add(path)
                    card.setStyleSheet(
                        "QFrame { background:#1e1e1e; border:3px solid #d97706; }")
            n = len(self.selected_paths)
            self.counter_label.setText(f"已选 {n} 张")
            self.del_sel_btn_ref.setEnabled(n > 0)
        self._update_sel_all_btn()

    def eventFilter(self, obj, event):
        """app 级拦截 ←→/回车：无论焦点在哪个控件都生效"""
        if not self.isVisible():
            return False
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Left:
                self._move_cursor(-1)
                return True
            if key == Qt.Key_Right:
                self._move_cursor(1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                # 回车：切换光标所在卡片的选择状态
                if self._photo_order:
                    path = self._photo_order[self._cursor]
                    card = self._cards.get(path)
                    if card is not None:
                        self._toggle_card(card, None)
                return True
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


# ── 分组总览（分析完成后自动进入） ──────────────────────────────
class GroupOverviewPanel(QWidget):
    """分析完成后的分组总览：显示所有组 + 未分组照片，
    支持把照片加入某组 / 组内预览移出 / 合并组"""

    def __init__(self, result, cache, parent=None):
        super().__init__(parent)
        self.result = result
        self.cache = cache
        self._selected_group = None      # 当前操作的组 (Group)
        self._multi_select = set()       # 未分组照片的多选
        self._singles_page = 0
        self._singles_per_page = 6

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(8)

        title = QLabel("📋 分组总览 — 检查分组结果，可手动调整")
        title.setStyleSheet("font-size:17px; font-weight:bold;")
        outer.addWidget(title)

        # 页面上方信息栏（不弹窗）
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(
            "color:#4ade80; font-size:13px; background:#1a2a1a;"
            "border:1px solid #2e9e5b; border-radius:6px; padding:8px;")
        self.notice_label.setVisible(False)
        outer.addWidget(self.notice_label)

        tip = QLabel("左侧：分组（点击选中，双击预览该组）· 右侧：未分组照片\n"
                     "「组内预览」查看组内照片并移出 · 「加入组」把未分组照片并入某组 · 「合并组」把两组并成一组\n"
                     "🖱 也可以直接把未分组照片拖拽到分组上（已确认的组锁定不可拖入）")
        tip.setStyleSheet("color:#888; font-size:12px;")
        tip.setWordWrap(True)
        outer.addWidget(tip)

        # 分割：左=组列表，右=未分组
        split = QHBoxLayout()
        split.setSpacing(10)

        # 左：组列表（带代表缩略图）
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("分组列表（双击预览）"))
        self.group_scroll = QScrollArea()
        self.group_scroll.setWidgetResizable(True)
        self.group_scroll.setFixedWidth(520)
        self.group_container = QWidget()
        self.group_vlay = QVBoxLayout(self.group_container)
        self.group_vlay.setSpacing(10)
        self.group_vlay.addStretch()
        self.group_scroll.setWidget(self.group_container)
        ll.addWidget(self.group_scroll, 1)

        merge_row = QHBoxLayout()
        self.merge_btn = QPushButton("🔗 合并组（多选）")
        self.merge_btn.setObjectName("ghost")
        self.merge_btn.clicked.connect(self._merge_groups)
        merge_row.addWidget(self.merge_btn)
        ll.addLayout(merge_row)
        split.addWidget(left, 2)

        # 右：未分组照片（可多选 + 分页）
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("未分组照片（点击多选，再点「加入组」）"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件名...")
        self.search.textChanged.connect(self._refresh_singles)
        rl.addWidget(self.search)

        self.singles_scroll = QScrollArea()
        self.singles_scroll.setWidgetResizable(True)
        self.singles_container = QWidget()
        self.singles_grid = QGridLayout(self.singles_container)
        self.singles_grid.setSpacing(8)
        self.singles_scroll.setWidget(self.singles_container)
        # 滚轮翻页（光标在未分组区域时）
        self.singles_scroll.viewport().installEventFilter(self)
        rl.addWidget(self.singles_scroll, 1)

        # 未分组分页条
        page_bar = QHBoxLayout()
        self.prev_s_btn = QPushButton("◀")
        self.prev_s_btn.setObjectName("ghost")
        self.prev_s_btn.setFixedWidth(50)
        self.s_page_label = QLabel("")
        self.s_page_label.setAlignment(Qt.AlignCenter)
        self.next_s_btn = QPushButton("▶")
        self.next_s_btn.setObjectName("ghost")
        self.next_s_btn.setFixedWidth(50)
        self.prev_s_btn.clicked.connect(lambda: self._set_singles_page(self._singles_page - 1))
        self.next_s_btn.clicked.connect(lambda: self._set_singles_page(self._singles_page + 1))
        page_bar.addStretch()
        page_bar.addWidget(self.prev_s_btn)
        page_bar.addWidget(self.s_page_label)
        page_bar.addWidget(self.next_s_btn)
        page_bar.addStretch()
        rl.addLayout(page_bar)

        add_row = QHBoxLayout()
        self.add_btn = QPushButton("➕ 将选中的未分组照片加入组...")
        self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(self._add_to_group)
        add_row.addWidget(self.add_btn)
        self.trash_btn = QPushButton("🗑 移入选中的照片到待删除")
        self.trash_btn.setObjectName("ghost")
        self.trash_btn.clicked.connect(self._trash_selected_singles)
        add_row.addWidget(self.trash_btn)
        rl.addLayout(add_row)
        split.addWidget(right, 3)

        outer.addLayout(split, 1)

        # 底部：统计 + 开始选图
        bottom = QHBoxLayout()
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color:#aaa; font-size:13px;")
        bottom.addWidget(self.stats_label)
        bottom.addStretch()
        self.start_btn = QPushButton("✅ 开始选图 →")
        self.start_btn.setObjectName("success")
        self.start_btn.clicked.connect(self._on_start)
        bottom.addWidget(self.start_btn)
        outer.addLayout(bottom)

        # 全部按钮 NoFocus
        for _b in self.findChildren(QPushButton):
            _b.setFocusPolicy(Qt.NoFocus)

        self._refresh_groups()
        self._refresh_singles()

    # ── 组列表（带代表缩略图） ──────────────────────────────────
    def _refresh_groups(self):
        # 清空（保留 stretch）
        while self.group_vlay.count() > 1:
            item = self.group_vlay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._group_widgets = []
        for i, g in enumerate(self.result.groups):
            w = self._make_group_row(i, g)
            self.group_vlay.insertWidget(self.group_vlay.count() - 1, w)
            self._group_widgets.append(w)
        self._update_stats()
        # 默认选中第一组
        if self._group_widgets:
            self._select_group(0)

    def _make_group_row(self, i, g):
        """一行：代表缩略图 + 组名 + 预览按钮"""
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background:#2a2a2a; border:1px solid #444;"
            "border-radius:8px; }"
            "QFrame#sel { background:#1e3a5f; border:2px solid #2a7de1; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        # 代表缩略图：优先用可见（未删除）照片；全删组用原组第一张
        visible = g.visible_photos()
        rep = visible[0] if visible else g.photos[0]
        thumb = QLabel()
        thumb.setFixedSize(100, 70)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background:#111; border-radius:4px;")
        img = self.cache.get(rep.path, 300)
        if img:
            img = img.convert('RGB')
            data = img.tobytes('raw', 'RGB')
            qimg = QImage(data, img.width, img.height, img.width * 3,
                          QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                100, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pix)
        lay.addWidget(thumb)

        # 文本区（点击选中 + 双击预览）
        lock = "🔒 已确认" if g.confirmed else ""
        n_vis = len(visible)
        n_blur = sum(1 for p in g.photos if getattr(p, 'is_blurry', False))
        blur_note = f" · ⚠{n_blur}模糊" if n_blur else ""
        if g.confirmed and not visible:
            txt = QLabel(f"组 {i+1}（空组 · 已全部删除）{lock}\n"
                         f"{rep.name}")
        else:
            txt = QLabel(f"组 {i+1}（{n_vis}张{blur_note}）{lock}\n"
                         f"{rep.name}")
        txt.setStyleSheet("color:#ddd; font-size:13px;")
        txt.setCursor(Qt.PointingHandCursor)
        lay.addWidget(txt, 1)

        # 组内预览按钮（宽度足够显示完整文字，减小 padding）
        preview_btn = QPushButton("预览")
        preview_btn.setObjectName("ghost")
        preview_btn.setFixedWidth(96)
        preview_btn.setStyleSheet(
            "QPushButton { background:#2a2a2a; color:#e0e0e0;"
            "border:1px solid #555; border-radius:6px; padding:2px 4px;"
            "font-size:13px; }"
            "QPushButton:hover { background:#444; }")
        preview_btn.clicked.connect(lambda _, idx=i: self._preview_group(idx))
        lay.addWidget(preview_btn)

        row._index = i
        row._label = txt
        row._group_ref = g
        # 拖放目标：接受未分组照片拖入（第 3 点）
        # 关键：row 和所有子控件（文字/缩略图/按钮）都要接受拖放，
        # 否则鼠标停在子控件上时 drop 事件被拦截，不传到 row
        def _bind_drop(w):
            w.setAcceptDrops(True)
            w.dragEnterEvent = lambda e: self._drag_enter_group(e)
            w.dropEvent = lambda e: self._drop_on_group(row._group_ref, e)
        _bind_drop(row)
        _bind_drop(txt)
        _bind_drop(thumb)
        _bind_drop(preview_btn)
        # 单击选中 / 双击预览
        row.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        row.mouseDoubleClickEvent = lambda e, r=row: self._preview_group(r._index)
        txt.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        txt.mouseDoubleClickEvent = lambda e, r=row: self._preview_group(r._index)
        thumb.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        thumb.mouseDoubleClickEvent = lambda e, r=row: self._preview_group(r._index)
        return row

    def _row_click(self, row, event):
        if event.button() == Qt.LeftButton:
            self._select_group(row._index)
        event.accept()

    def _select_group(self, i):
        if 0 <= i < len(self.result.groups):
            self._selected_group = self.result.groups[i]
        else:
            self._selected_group = None
        for wi, w in enumerate(self._group_widgets):
            sel = (wi == i)
            w.setStyleSheet(
                "QFrame { background:#1e3a5f; border:2px solid #2a7de1;"
                "border-radius:8px; }" if sel else
                "QFrame { background:#2a2a2a; border:1px solid #444;"
                "border-radius:8px; }")

    def _preview_group(self, i, removable=True):
        """双击组/点预览按钮 → 弹出该组大图预览（未确认组可移出，已确认组锁定）"""
        if 0 <= i < len(self.result.groups):
            g = self.result.groups[i]
            if g.confirmed:
                # 已确认 → 只预览，不允许移出
                dlg = PickRemoveDialog(g, self.cache,
                                       title=f"组 {i+1} 预览（已锁定）",
                                       mode="preview", parent=self)
                dlg.exec()
                return
            dlg = PickRemoveDialog(g, self.cache,
                                   title=f"组 {i+1} 预览",
                                   mode="remove", parent=self)
            if dlg.exec():
                paths = dlg.selected_paths
                if paths:
                    removed = g.remove_photos(paths)
                    self.result.singles.extend(removed)
                    # 若组内照片被全部移出或只剩1张 → 解散该组
                    if len(g.photos) <= 1:
                        if len(g.photos) == 1:
                            self.result.singles.append(g.photos[0])
                        self.result.groups.remove(g)
                        self._selected_group = None
                    self._refresh_groups()
                    self._refresh_singles()

    # ── 合并多个组 ──────────────────────────────────────────────
    def _merge_groups(self):
        """点击按钮 → 弹窗多选 n 组 → 合并为一个大组（已确认组锁定）"""
        available = [g for g in self.result.groups if not g.confirmed]
        if len(available) < 2:
            QMessageBox.warning(
                self, "提示",
                "至少需要 2 个未确认的组才能合并！\n"
                "（已确认的组已锁定，如需修改请先在选图中撤销）")
            return
        dlg = PickGroupsDialog(available, self.cache,
                               "勾选要合并的组（至少 2 组）", self)
        if not dlg.exec():
            return
        sel = dlg.selected_groups
        if len(sel) < 2:
            QMessageBox.warning(self, "提示", "请至少勾选 2 个组！")
            return
        # 合并成一个新组
        base = sel[0]
        merged_photos = []
        for g in sel:
            merged_photos.extend(g.photos)
            if g is not base:
                self.result.groups.remove(g)
        base.photos = merged_photos
        base.recalc()
        base.photos.sort(key=lambda p: p.taken)
        self._refresh_groups()
        QMessageBox.information(
            self, "已合并",
            f"已将 {len(sel)} 组合并为「组 {self.result.groups.index(base)+1}」"
            f"（共 {len(base.photos)} 张）。")

    # ── 未分组照片（分页） ──────────────────────────────────────
    def _set_singles_page(self, page):
        photos = self.result.singles
        text = self.search.text().strip().lower()
        if text:
            photos = [p for p in photos if text in p.name.lower()]
        total_pages = max(1, (len(photos) + self._singles_per_page - 1)
                          // self._singles_per_page)
        self._singles_page = max(0, min(total_pages - 1, page))
        self._refresh_singles()

    def _refresh_singles(self):
        while self.singles_grid.count():
            item = self.singles_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # 未分组照片按拍摄时间排序（第 1 点）
        photos = sorted(self.result.singles, key=lambda p: p.taken)
        text = self.search.text().strip().lower()
        if text:
            photos = [p for p in photos if text in p.name.lower()]
        total_pages = max(1, (len(photos) + self._singles_per_page - 1)
                          // self._singles_per_page)
        if self._singles_page >= total_pages:
            self._singles_page = total_pages - 1
        start = self._singles_page * self._singles_per_page
        end = min(len(photos), start + self._singles_per_page)
        page_photos = photos[start:end]

        cols = 3
        self._single_cards = {}
        for i, photo in enumerate(page_photos):
            card = BigPhotoCard(photo, self.cache,
                                keep=(photo.path in self._multi_select),
                                show_mark=False,
                                blurry=getattr(photo, 'is_blurry', False))
            # 原生点击/双击（选中 + 预览）保留，仅覆盖按下记录起点 + 移动/松开做自制拖放
            card.clicked.connect(lambda c, p=photo: self._toggle_single(p))
            card.double_clicked.connect(lambda c, p=photo: self._preview_single(p))
            card.setAttribute(Qt.WA_DeleteOnClose, False)
            card.setMouseTracking(True)
            card._drag_photo = photo
            card._drag_panel = self
            card._orig_press = BigPhotoCard.mousePressEvent  # 原始按下（emit clicked）
            card.mousePressEvent = lambda e, c=card: self._drag_press(c, e)
            card.mouseMoveEvent = lambda e, c=card: self._drag_move(c, e)
            card.mouseReleaseEvent = lambda e, c=card: self._drag_release(c, e)
            self._single_cards[photo.path] = card
            self.singles_grid.addWidget(card, i // cols, i % cols)
            self.singles_grid.setColumnStretch(i % cols, 1)
            self.singles_grid.setRowStretch(i // cols, 1)

        self.s_page_label.setText(f"{self._singles_page+1}/{total_pages}")
        self.prev_s_btn.setEnabled(self._singles_page > 0)
        self.next_s_btn.setEnabled(self._singles_page < total_pages - 1)
        self._update_stats()

    # ── 自制拖放（带跟随鼠标的缩略图 ghost，不依赖系统 QDrag） ──
    def _drag_press(self, card, event):
        """按下：先让原生 clicked 触发（选中），再记录拖拽起点"""
        # 调用 BigPhotoCard 原始 mousePressEvent 触发 clicked 信号
        try:
            card._orig_press(card, event)
        except Exception:
            pass
        # 双击（第二击）不记录起点，避免误拖
        if event.type() == QEvent.MouseButtonDblClick:
            return
        self._press_pos = event.globalPosition().toPoint()
        self._press_card = card

    def _drag_move(self, card, event):
        """移动：超过阈值启动拖拽 + 显示 ghost；拖拽中更新 ghost 位置"""
        if not (event.buttons() & Qt.LeftButton):
            return
        if not hasattr(self, '_drag_active'):
            self._drag_active = False
            self._drag_ghost = None
            self._drag_card = None
        cur = event.globalPosition().toPoint()
        if not self._drag_active:
            # 检查是否按下在当前卡片（未分组照片）上
            if card._drag_photo is None:
                return
            if not hasattr(self, '_press_pos') or self._press_pos is None:
                return
            if (cur - self._press_pos).manhattanLength() < 6:
                return
            # 启动拖拽
            self._drag_active = True
            self._drag_card = card
            paths = [card._drag_photo.path]
            for p in self._multi_select:
                if p != card._drag_photo.path:
                    paths.append(p)
            self._drag_paths = paths
            card.grabMouse()
            self._show_drag_ghost(card, cur)
        else:
            # 更新 ghost 位置
            if self._drag_ghost is not None:
                self._drag_ghost.move(cur.x() - 60, cur.y() - 45)

    def _drag_release(self, card, event):
        """松开：落在组行上 → 加入该组；否则取消拖拽"""
        if getattr(self, '_drag_active', False):
            card.releaseMouse()
            self._drag_active = False
            if self._drag_ghost is not None:
                self._drag_ghost.hide()
                self._drag_ghost.deleteLater()
                self._drag_ghost = None
            pos = event.globalPosition().toPoint()
            target = self._group_at_global(pos)
            if target is not None:
                n = self._move_singles_to_group(target, set(self._drag_paths))
                self._show_overview_notice(
                    f"✅ 已将 {n} 张照片拖入"
                    f"「组 {self.result.groups.index(target)+1}」。")
            else:
                self._show_overview_notice(
                    "⚠️ 请拖到左侧「分组列表」的组行上再松手。")
            self._drag_paths = None
            self._press_pos = None
            return
        # 非拖拽的松开：不处理（点击选中由 clicked 信号负责）

    def _show_drag_ghost(self, card, global_pos):
        """显示跟随鼠标的拖拽缩略图"""
        try:
            from PySide6.QtWidgets import QLabel
            ghost = QLabel(None)
            ghost.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
            ghost.setAttribute(Qt.WA_TranslucentBackground)
            ghost.setStyleSheet(
                "background: rgba(20,20,20,200); border: 2px solid #2a7de1;"
                "border-radius: 6px;")
            pix = QPixmap()
            if card._orig_pixmap is not None:
                pix = card._orig_pixmap.scaled(
                    120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pix.isNull():
                ghost.setPixmap(pix)
                ghost.adjustSize()
                ghost.move(global_pos.x() - 60, global_pos.y() - 45)
                ghost.show()
            self._drag_ghost = ghost
        except Exception:
            self._drag_ghost = None

    def _group_at_global(self, global_pos):
        """返回全局坐标落在哪个组行对应的 Group"""
        for w in self._group_widgets:
            local = w.mapFromGlobal(global_pos)
            if w.rect().contains(local):
                return w._group_ref
        return None

    def eventFilter(self, obj, event):
        """未分组照片区域滚轮翻页（分组列表区域独立滚动）"""
        if obj is self.singles_scroll.viewport() and \
                event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self._set_singles_page(self._singles_page - 1)
            else:
                self._set_singles_page(self._singles_page + 1)
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _preview_single(self, photo):
        """双击未分组照片 → 大图预览（纯预览，无保留/删除按钮）"""
        paths = [p.path for p in self.result.singles]
        idx = paths.index(photo.path)
        preview = FullscreenPreview(paths, self.cache, set(), idx, self,
                                    preview_only=True)
        preview.exec()

    def _toggle_single(self, photo):
        if photo.path in self._multi_select:
            self._multi_select.discard(photo.path)
        else:
            self._multi_select.add(photo.path)
        card = self._single_cards.get(photo.path)
        if card:
            card.set_keep(photo.path in self._multi_select)
        self._update_stats()

    # ── 拖放支持 ────────────────────────────────────────────────
    def _start_drag(self, card, event):
        """按住未分组照片拖动 → 拖拽到组列表（左键 + 移动）"""
        from PySide6.QtGui import QDrag, QPixmap
        from PySide6.QtCore import QMimeData
        # mouseMoveEvent 中按钮状态在 event.buttons()，button() 是 NoButton
        if not (event.buttons() & Qt.LeftButton):
            return
        # 拖拽的照片集合：拖当前这张 + 已选中的多选（无论当前张是否被 toggle）
        drag_paths = list(self._multi_select)
        if card._drag_photo.path not in drag_paths:
            drag_paths.append(card._drag_photo.path)
        mime = QMimeData()
        mime.setData("application/x-photoselect-paths",
                     "\n".join(drag_paths).encode('utf-8'))
        # Windows 系统拖放兜底：同时设置 text/plain（部分平台会丢弃自定义格式）
        mime.setText("\n".join(drag_paths))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # 拖拽图标：当前卡片缩略图
        pix = QPixmap()
        if card._orig_pixmap is not None:
            pix = card._orig_pixmap.scaled(
                120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not pix.isNull():
            drag.setPixmap(pix)
        drag.exec(Qt.CopyAction)

    def _drag_enter_group(self, event):
        """组行接受拖放：只接受照片拖拽"""
        if event.mimeData().hasFormat("application/x-photoselect-paths"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drop_on_group(self, row_group, event):
        """拖放到组行：把照片加入该组（已确认组锁定）"""
        if row_group.confirmed:
            self._show_overview_notice(
                "🔒 该组已确认锁定，请先撤销确认再操作。")
            event.ignore()
            return
        mime = event.mimeData()
        if mime.hasFormat("application/x-photoselect-paths"):
            raw = mime.data("application/x-photoselect-paths").data()
        else:
            raw = mime.text().encode('utf-8')
        if not raw:
            event.ignore()
            return
        paths = set(raw.decode('utf-8').split("\n"))
        paths = {p for p in paths if p}  # 去空
        # 只拖未分组的照片
        valid = {p for p in self.result.singles if p.path in paths}
        if valid:
            n = self._move_singles_to_group(row_group, valid)
            self._show_overview_notice(
                f"✅ 已将 {n} 张照片拖入"
                f"「组 {self.result.groups.index(row_group)+1}」。")
        else:
            # 拖的路径都不在未分组里（可能是已确认组的照片，或已移动过）
            self._show_overview_notice(
                "⚠️ 没有可加入的照片：这些照片可能已在某个组里，"
                "或目标组已确认锁定。")
        event.acceptProposedAction()

    # ── 加入组（弹窗选目标组） ──────────────────────────────────
    def _move_singles_to_group(self, target, paths):
        """把指定未分组照片加入目标组（拖放和点选共用）"""
        moved = []
        for p in self.result.singles:
            if p.path in paths:
                target.photos.append(p)
                moved.append(p)
        self.result.singles = [p for p in self.result.singles
                               if p.path not in paths]
        target.recalc()
        target.photos.sort(key=lambda p: p.taken)
        self._multi_select.clear()
        self._refresh_groups()
        self._refresh_singles()
        return len(moved)

    def _add_to_group(self):
        if not self._multi_select:
            QMessageBox.warning(self, "提示", "请先在右侧选择要加入的照片！")
            return
        # 弹窗：选择目标组（排除已确认锁定组），或新建组
        available = [g for g in self.result.groups if not g.confirmed]
        if available:
            dlg = PickGroupDialog(available, "选择要加入的目标组（或新建）",
                                  self, cache=self.cache,
                                  allow_new_group=True,
                                  new_photo_count=len(self._multi_select))
            if dlg.exec():
                if dlg.new_group:
                    # 新建组
                    photos = [p for p in self.result.singles
                              if p.path in self._multi_select]
                    grp = Group(photos)
                    grp.recalc()
                    grp.photos.sort(key=lambda p: p.taken)
                    self.result.groups.append(grp)
                    self.result.singles = [p for p in self.result.singles
                                           if p.path not in self._multi_select]
                    self._multi_select.clear()
                    self._refresh_groups()
                    self._refresh_singles()
                    QMessageBox.information(
                        self, "已新建组",
                        f"已新建组（{len(photos)} 张），组号"
                        f" {len(self.result.groups)}。")
                    return
                target = dlg.selected_group
                moved = []
                for p in self.result.singles:
                    if p.path in self._multi_select:
                        target.photos.append(p)
                        moved.append(p)
                self.result.singles = [p for p in self.result.singles
                                       if p.path not in self._multi_select]
                target.recalc()
                target.photos.sort(key=lambda p: p.taken)
                self._multi_select.clear()
                self._refresh_groups()
                self._refresh_singles()
                QMessageBox.information(
                    self, "已加入组",
                    f"已将 {len(moved)} 张照片加入"
                    f"「组 {self.result.groups.index(target)+1}」。")
        else:
            # 所有组都已确认 → 只能新建组
            photos = [p for p in self.result.singles
                      if p.path in self._multi_select]
            if len(photos) < 2:
                QMessageBox.warning(self, "提示", "至少选择 2 张照片才能建组！")
                return
            grp = Group(photos)
            grp.recalc()
            self.result.groups.append(grp)
            self.result.singles = [p for p in self.result.singles
                                   if p.path not in self._multi_select]
            self._multi_select.clear()
            self._refresh_groups()
            self._refresh_singles()
            QMessageBox.information(self, "已新建组",
                                    f"已新建组（{len(photos)} 张）。")

    # ── 未分组照片 → 待删除 ─────────────────────────────────────
    def _trash_selected_singles(self):
        """把选中的未分组照片直接移入 待删除"""
        if not self._multi_select:
            QMessageBox.warning(self, "提示", "请先在右侧选择要移入待删除的照片！")
            return
        folder = os.path.dirname(self.result.singles[0].path) \
            if self.result.singles else os.path.dirname(
                list(self._multi_select)[0])
        to_delete = [p for p in self.result.singles
                     if p.path in self._multi_select]
        # JPG+RAW 配对：一起移入待删除（计数按「照片」算，对=1张）
        pairs = getattr(self.result, 'pairs', {}) or {}
        expanded = []
        seen = set()
        n_photos = 0
        for p in to_delete:
            if p.path not in seen:
                n_photos += 1
            seen.add(p.path)
            expanded.append(p.path)
            if p.path in pairs:
                seen.add(pairs[p.path])
                expanded.append(pairs[p.path])
        n_moved = move_to_trash(expanded, folder)
        # 从未分组移除
        self.result.singles = [p for p in self.result.singles
                               if p.path not in self._multi_select]
        self._multi_select.clear()
        self._refresh_singles()
        self._show_overview_notice(
            f"🗑 已将 {n_photos} 张未分组照片移入「{TRASH_DIR_NAME}」\n"
            f"（确认无误后可手动删除该文件夹释放空间）")

    def _show_overview_notice(self, text):
        """在分组总览标题下显示提示（不弹窗）"""
        if hasattr(self, 'notice_label'):
            self.notice_label.setText(text)
            self.notice_label.setVisible(True)
            QTimer.singleShot(4000,
                              lambda: self.notice_label.setVisible(False))

    # ── 统计 ────────────────────────────────────────────────────
    def _update_stats(self):
        n_total = len(self.result.photos)
        n_in_groups = sum(len(g.photos) for g in self.result.groups)
        n_singles = len(self.result.singles)
        n_groups = len(self.result.groups)
        self.stats_label.setText(
            f"共 {n_total} 张 · 组内 {n_in_groups} 张（{n_groups}组）"
            f" · 未分组 {n_singles} 张")

    def _on_start(self):
        self.start_selected = True


class PickGroupsDialog(QDialog):
    """多选组（带缩略图）：用于合并组"""
    def __init__(self, groups, cache, prompt, parent=None):
        super().__init__(parent)
        self.groups = groups
        self.cache = cache
        self.selected_groups = []
        self.setWindowTitle("选择组")
        self.resize(560, 500)

        layout = QVBoxLayout(self)
        lbl = QLabel(prompt)
        lbl.setStyleSheet("color:#ccc; font-size:14px;")
        layout.addWidget(lbl)

        tip = QLabel("点击组行切换勾选（蓝色高亮=选中）")
        tip.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setSpacing(8)
        vlay.addStretch()
        self._rows = []
        for i, g in enumerate(groups):
            row, cb = self._make_row(i, g)
            vlay.insertWidget(vlay.count() - 1, row)
            self._rows.append((row, cb))
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        btns = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定合并")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _make_row(self, i, g):
        """一行：代表缩略图 + 组名 + 勾选框"""
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background:#2a2a2a; border:1px solid #444;"
            "border-radius:8px; }"
            "QFrame#sel { background:#1e3a5f; border:2px solid #2a7de1; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        rep = min(g.photos, key=lambda p: p.taken)
        thumb = QLabel()
        thumb.setFixedSize(80, 56)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background:#111; border-radius:4px;")
        _cache = getattr(self, '_cache', None) or getattr(self, 'cache', None)
        if _cache is not None:
            img = _cache.get(rep.path, 240)
            if img:
                img = img.convert('RGB')
                data = img.tobytes('raw', 'RGB')
                qimg = QImage(data, img.width, img.height, img.width * 3,
                              QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg).scaled(
                    80, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb.setPixmap(pix)
        lay.addWidget(thumb)

        names = " / ".join(p.name for p in g.photos[:2])
        if len(g.photos) > 2:
            names += f" ...(+{len(g.photos)-2})"
        txt = QLabel(f"组 {i+1}（{len(g.photos)}张）\n{names}")
        txt.setStyleSheet("color:#ddd; font-size:12px;")
        lay.addWidget(txt, 1)

        cb = QCheckBox()
        lay.addWidget(cb)

        row._index = i
        row.mousePressEvent = lambda e, r=row, c=cb: self._row_click(r, c, e)
        txt.mousePressEvent = lambda e, r=row, c=cb: self._row_click(r, c, e)
        thumb.mousePressEvent = lambda e, r=row, c=cb: self._row_click(r, c, e)
        cb.toggled.connect(lambda checked, r=row: self._cb_toggle(r, checked))
        return row, cb

    def _row_click(self, row, cb, event):
        if event.button() == Qt.LeftButton:
            cb.setChecked(not cb.isChecked())
        event.accept()

    def _cb_toggle(self, row, checked):
        row.setStyleSheet(
            "QFrame { background:#1e3a5f; border:2px solid #2a7de1;"
            "border-radius:8px; }" if checked else
            "QFrame { background:#2a2a2a; border:1px solid #444;"
            "border-radius:8px; }")

    def _accept(self):
        self.selected_groups = [
            g for (row, cb), g in zip(self._rows, self.groups) if cb.isChecked()]
        if len(self.selected_groups) < 2:
            QMessageBox.warning(self, "提示", "请至少勾选 2 个组！")
            return
        self.accept()


class PickGroupDialog(QDialog):
    """单选组（带缩略图）：用于把未分组照片加入某组；可选新建组"""
    def __init__(self, groups, prompt, parent=None, cache=None,
                 allow_new_group=False, new_photo_count=0):
        super().__init__(parent)
        self.groups = groups
        self.selected_group = None
        self.new_group = False
        self._cache = cache
        self._allow_new_group = allow_new_group
        self._new_photo_count = new_photo_count
        self.setWindowTitle("选择组")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        lbl = QLabel(prompt)
        lbl.setStyleSheet("color:#ccc; font-size:14px;")
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setSpacing(8)
        vlay.addStretch()
        self._rows = []
        for i, g in enumerate(groups):
            row = self._make_row(i, g)
            vlay.insertWidget(vlay.count() - 1, row)
            self._rows.append(row)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        btns = QHBoxLayout()
        if self._allow_new_group:
            new_btn = QPushButton(f"➕ 新建组（{self._new_photo_count}张）")
            new_btn.setObjectName("primary")
            new_btn.clicked.connect(self._accept_new)
            btns.addWidget(new_btn)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

        # 默认选中第一行
        if self._rows:
            self._select_row(0)

    def _make_row(self, i, g):
        from PySide6.QtWidgets import QRadioButton
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background:#2a2a2a; border:1px solid #444;"
            "border-radius:8px; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        rep = min(g.photos, key=lambda p: p.taken)
        thumb = QLabel()
        thumb.setFixedSize(80, 56)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background:#111; border-radius:4px;")
        _cache = getattr(self, '_cache', None) or getattr(self, 'cache', None)
        if _cache is not None:
            img = _cache.get(rep.path, 240)
            if img:
                img = img.convert('RGB')
                data = img.tobytes('raw', 'RGB')
                qimg = QImage(data, img.width, img.height, img.width * 3,
                              QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg).scaled(
                    80, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb.setPixmap(pix)
        lay.addWidget(thumb)

        names = " / ".join(p.name for p in g.photos[:2])
        if len(g.photos) > 2:
            names += f" ...(+{len(g.photos)-2})"
        txt = QLabel(f"组 {i+1}（{len(g.photos)}张）\n{names}")
        txt.setStyleSheet("color:#ddd; font-size:12px;")
        lay.addWidget(txt, 1)

        rb = QRadioButton()
        rb.setChecked(i == 0)
        lay.addWidget(rb)

        row._index = i
        row._rb = rb
        row.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        txt.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        thumb.mousePressEvent = lambda e, r=row: self._row_click(r, e)
        rb.toggled.connect(lambda checked, r=row: self._select_row(r._index)
                           if checked else None)
        return row

    def _row_click(self, row, event):
        if event.button() == Qt.LeftButton:
            self._select_row(row._index)
        event.accept()

    def _select_row(self, i):
        for r in self._rows:
            sel = (r._index == i)
            r._rb.setChecked(sel)
            r.setStyleSheet(
                "QFrame { background:#1e3a5f; border:2px solid #2a7de1;"
                "border-radius:8px; }" if sel else
                "QFrame { background:#2a2a2a; border:1px solid #444;"
                "border-radius:8px; }")
        if 0 <= i < len(self.groups):
            self.selected_group = self.groups[i]

    def _accept(self):
        if self.selected_group is None and self.groups:
            self.selected_group = self.groups[0]
        if self.selected_group is not None:
            self.accept()
        else:
            QMessageBox.warning(self, "提示", "请先选择一组！")

    def _accept_new(self):
        self.new_group = True
        self.accept()


class PickRemoveDialog(QDialog):
    """组内预览 + 勾选移出照片（红色标记=移出，与选图页绿勾保留区分）"""
    def __init__(self, group, cache, title="组内预览", mode="remove",
                 parent=None):
        super().__init__(parent)
        self.group = group
        self.cache = cache
        self.selected_paths = []
        self._mode = mode
        self._cards = {}          # path -> [card, marked_label]
        self.setWindowTitle(f"{title} — 组（{len(group.photos)}张）")
        self.resize(1000, 650)

        layout = QVBoxLayout(self)
        if mode == "remove":
            tip = QLabel("🖱 点击照片标记为「移出」（红色边框）\n"
                         "选好后点「将勾选照片移出本组」——移出只是退回未分组，不会删除照片！")
        else:
            tip = QLabel("本组照片预览（双击任意照片可放大查看）")
        tip.setStyleSheet("color:#aaa;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)
        cols = 3
        # 只显示可见（未被删除）的照片；已确认组已删除的不显示
        photos = group.visible_photos()
        self._all_photos = list(group.photos)   # 完整列表（供全选/解散用）
        self.setWindowTitle(f"{title} — 组（{len(photos)}张可见）")
        if not photos:
            empty = QLabel("⚠️ 该组没有可见照片（已全部删除）")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#888; font-size:14px; padding:40px;")
            grid.addWidget(empty, 0, 0)
        for i, photo in enumerate(photos):
            card = BigPhotoCard(photo, cache, keep=False, show_mark=False, blurry=getattr(photo, 'is_blurry', False))
            card.clicked.connect(lambda c, p=photo: self._toggle(p))
            card.double_clicked.connect(self._on_dbl)
            self._cards[photo.path] = (card, None)
            grid.addWidget(card, i // cols, i % cols)
            grid.setColumnStretch(i % cols, 1)
            grid.setRowStretch(i // cols, 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        btns = QDialogButtonBox()
        if mode == "remove":
            ok = btns.addButton("移出分组", QDialogButtonBox.AcceptRole)
            ok.setStyleSheet("background:#d97706; color:white; padding:8px 18px;")
            ok.clicked.connect(self._accept)
            diss = btns.addButton("🗑 解散该组（全部移出）", QDialogButtonBox.ActionRole)
            diss.setStyleSheet(
                "background:#7c2d12; color:#fbbf24; padding:8px 14px;"
                "border:1px solid #f59e0b; border-radius:6px;")
            diss.clicked.connect(self._dissolve)
        cancel = btns.addButton("关闭", QDialogButtonBox.RejectRole)
        cancel.setStyleSheet("padding:8px 18px;")
        cancel.clicked.connect(self.reject)
        layout.addWidget(btns)

    def _toggle(self, photo):
        card, _ = self._cards[photo.path]
        # 移出模式：勾选=红色边框
        if self._mode == "remove":
            card.toggle()
            # 用 set_keep 会显示绿/红标记——直接改边框样式
            marked = card.keep
            if marked:
                card.setStyleSheet(
                    "QFrame { background:#1e1e1e; border:4px solid #d97706;"
                    "border-radius:8px; }")
            else:
                card.setStyleSheet(
                    "QFrame { background:#1e1e1e; border:3px solid #555555;"
                    "border-radius:8px; }")
        else:
            card.toggle()

    def _on_dbl(self, card):
        """双击卡片 → 大图预览（只翻本组可见照片，纯预览无按钮）"""
        paths = [p.path for p in self.group.visible_photos()]
        idx = paths.index(card.photo.path) if card.photo.path in paths else 0
        preview = FullscreenPreview(paths, self.cache, set(), idx, self,
                                    preview_only=True)
        preview.exec()

    def _accept(self):
        # 移出模式：keep=True 表示勾选要移出；全部勾选 = 解散该组
        self.selected_paths = [p.path for p in self.group.visible_photos()
                               if self._cards[p.path][0].keep]
        if not self.selected_paths:
            QMessageBox.warning(self, "提示", "请至少勾选 1 张要移出的照片！")
            return
        # 允许移出全部（=解散该组），不再阻止
        self.accept()

    def _dissolve(self):
        """解散该组：全部可见照片移出，退回未分组"""
        visible = self.group.visible_photos()
        n = len(visible)
        if n == 0:
            QMessageBox.information(self, "解散该组", "该组已没有可见照片。")
            return
        ret = QMessageBox.question(
            self, "解散该组",
            f"确定要解散该组吗？\n\n组内 {n} 张照片将全部退回未分组照片。\n"
            "（不会删除任何照片，只是不再分组）",
            QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.selected_paths = [p.path for p in visible]
            self.accept()


# ── 简易深色列表组件 ──────────────────────────────────────────────
class QListWidgetDark(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget
        self._list = QListWidget(self)
        self._list.setStyleSheet(
            "QListWidget { background:#2a2a2a; color:#ccc; border:1px solid #444;"
            "border-radius:8px; padding:4px; font-size:12px; }"
            "QListWidget::item { padding:8px; border-radius:4px; margin:2px; }"
            "QListWidget::item:selected { background:#2a7de1; color:white; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)

    def blockSignals(self, b):
        self._list.blockSignals(b)

    def clear(self):
        self._list.clear()

    def addItem(self, item):
        self._list.addItem(item)

    def setCurrentRow(self, r):
        self._list.setCurrentRow(r)

    def on_row_changed(self, slot):
        self._list.currentRowChanged.connect(slot)


class QListWidgetItem2:
    """与 QListWidgetItem 兼容的简单封装"""
    def __init__(self, text):
        from PySide6.QtWidgets import QListWidgetItem
        self._item = QListWidgetItem(text)
        self._item.setSizeHint(self._item.sizeHint())

    def setData(self, role, value):
        self._item.setData(role, value)

    def __getattr__(self, name):
        return getattr(self._item, name)


# ── 导出范围对话框（下拉选择） ────────────────────────────────────
class ExportDialog(QDialog):
    def __init__(self, n_kept, n_singles, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出照片")
        self.resize(520, 220)
        layout = QVBoxLayout(self)

        title = QLabel("导出范围：")
        title.setStyleSheet("font-size:15px; font-weight:bold;")
        layout.addWidget(title)

        self.export_combo = QComboBox()
        self.export_combo.addItem(f"所有保留照片 + 未分组独张"
                                  f"（{n_kept} + {n_singles} = {n_kept+n_singles} 张）", "all")
        self.export_combo.addItem(f"仅保留照片（{n_kept} 张）", "kept")
        self.export_combo.addItem(f"仅未分组独张照片（{n_singles} 张）", "singles")
        self.export_combo.setStyleSheet(
            "QComboBox { background:#2a2a2a; color:#e0e0e0;"
            "border:1px solid #444; border-radius:6px; padding:8px 12px;"
            "font-size:13px; }"
            "QComboBox QAbstractItemView { background:#2a2a2a; color:#e0e0e0;"
            "selection-background-color:#2a7de1; }")
        layout.addWidget(self.export_combo)

        tip = QLabel("提示：组内保留 = 每组你确认保留的照片；\n"
                     "独张 = 没有进入任何相似组的照片。")
        tip.setStyleSheet("color:#888; font-size:12px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()

        btns = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("导出")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def selected_mode(self):
        return self.export_combo.currentData()


# ── 设置对话框（集成配置类控件 + 次要操作） ──────────────────────
# ── 关于/许可对话框 ───────────────────────────────────────────────
class AboutDialog(QDialog):
    """软件信息 + 使用许可"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 PhotoSelect")
        self.resize(520, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        title = QLabel("📸 PhotoSelect 照片优选")
        title.setStyleSheet("font-size:20px; font-weight:bold; color:#2a7de1;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"版本 {APP_VERSION} · by nfd")
        ver.setStyleSheet("color:#aaa; font-size:13px;")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#444;")
        layout.addWidget(sep)

        lic = QLabel(
            "📜 使用许可\n\n"
            "· 本软件免费供个人使用，欢迎大家分享给朋友\n"
            "· 允许自由使用、复制、分享（非商业用途）\n"
            "· 禁止将本软件或其修改版本用于商业用途\n"
            "· 如需商业使用，请先联系作者获取授权\n\n"
            "📮 联系方式\n"
            "· 邮箱：745936837@qq.com\n"
            "· 微信：13917034098\n\n"
            "🎨 技术栈：Python · PySide6 · OpenCV · PIL")
        lic.setStyleSheet("color:#ddd; font-size:13px; line-height:1.6;")
        lic.setWordWrap(True)
        layout.addWidget(lic)

        layout.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("好的")
        ok_btn.setObjectName("primary")
        ok_btn.setFixedWidth(120)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        play_success_sound()


# ── 筛选结果总览对话框 ────────────────────────────────────────────
class DoneOverviewDialog(QDialog):
    """全部确认后：显示所有保留的照片（每组保留的+独张），可确认或返回调整"""
    def __init__(self, result, cache, parent=None):
        super().__init__(parent)
        self.result = result
        self.cache = cache
        self.confirmed = False
        self._page = 0
        self._per_page = 6
        # 所有保留的照片（组内全部保留 + 独张；全删组保留为空集）
        self._kept_paths = []
        self._kept_labels = []   # 每张的标签（组 N / 独张）
        for gi, g in enumerate(result.groups):
            if g.kept_paths:
                kept_paths = g.kept_paths
            elif g.confirmed and g.user_keep is not None:
                kept_paths = {g.user_keep.path}
            elif not g.confirmed and g.recommended_keep is not None:
                kept_paths = {g.recommended_keep.path}
            else:
                kept_paths = set()   # 全删组/空组：无保留照片
            for p in g.photos:
                if p.path in kept_paths:
                    self._kept_paths.append(p.path)
                    self._kept_labels.append(f"组 {gi+1}")
        for s in result.singles:
            self._kept_paths.append(s.path)
            self._kept_labels.append("独张")

        self.setWindowTitle("✅ 筛选结果总览")
        self.resize(1100, 720)

        layout = QVBoxLayout(self)

        title = QLabel(f"🎉 所有组都已筛选完成！共保留 {len(self._kept_paths)} 张：")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(title)

        tip = QLabel("确认无误请点「✅ 确认完成」；想调整某组，点「↩ 返回修改」。")
        tip.setStyleSheet("color:#888; font-size:12px;")
        layout.addWidget(tip)

        # 分页条
        page_bar = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setObjectName("ghost")
        self.prev_btn.setFixedWidth(50)
        self.page_label = QLabel("")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_btn = QPushButton("▶")
        self.next_btn.setObjectName("ghost")
        self.next_btn.setFixedWidth(50)
        self.prev_btn.clicked.connect(lambda: self._set_page(self._page - 1))
        self.next_btn.clicked.connect(lambda: self._set_page(self._page + 1))
        page_bar.addStretch()
        page_bar.addWidget(self.prev_btn)
        page_bar.addWidget(self.page_label)
        page_bar.addWidget(self.next_btn)
        page_bar.addStretch()
        layout.addLayout(page_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.container)
        self.scroll.viewport().installEventFilter(self)
        layout.addWidget(self.scroll, 1)

        btns = QHBoxLayout()
        self.back_btn = QPushButton("↩ 返回修改")
        self.back_btn.setObjectName("ghost")
        self.back_btn.clicked.connect(self.reject)
        btns.addWidget(self.back_btn)
        btns.addStretch()
        self.done_btn = QPushButton("✅ 确认完成")
        self.done_btn.setObjectName("success")
        self.done_btn.clicked.connect(self._accept_done)
        btns.addWidget(self.done_btn)
        layout.addLayout(btns)

        self._rebuild()

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        n = len(self._kept_paths)
        total_pages = max(1, (n + self._per_page - 1) // self._per_page)
        if self._page >= total_pages:
            self._page = total_pages - 1
        start = self._page * self._per_page
        end = min(n, start + self._per_page)

        cols = 3
        idx = 0
        for i in range(start, end):
            path = self._kept_paths[i]
            label = self._kept_labels[i]
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background:#1e1e1e; border:1px solid #444;"
                "border-radius:8px; }")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(6, 6, 6, 6)

            # 组标识（小）
            badge = QLabel(f"[{label}]")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "color:#2a7de1; font-size:11px; font-weight:bold;"
                "background:#1a1a1a; border-radius:4px; padding:2px;")
            cl.addWidget(badge)

            img = self.cache.get(path, 480)
            if img:
                img = img.convert('RGB')
                data = img.tobytes('raw', 'RGB')
                qimg = QImage(data, img.width, img.height, img.width * 3,
                              QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg).scaled(
                    240, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl = QLabel()
                lbl.setPixmap(pix)
                lbl.setAlignment(Qt.AlignCenter)
                cl.addWidget(lbl)
            name = QLabel(f"✓ {os.path.basename(path)}")
            name.setWordWrap(True)
            name.setStyleSheet("color:#4ade80; font-size:11px;")
            name.setAlignment(Qt.AlignCenter)
            cl.addWidget(name)

            self.grid.addWidget(card, idx // cols, idx % cols)
            self.grid.setColumnStretch(idx % cols, 1)
            idx += 1

        self.page_label.setText(f"{self._page+1}/{total_pages}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < total_pages - 1)

    def _set_page(self, page):
        n = len(self._kept_paths)
        total_pages = max(1, (n + self._per_page - 1) // self._per_page)
        self._page = max(0, min(total_pages - 1, page))
        self._rebuild()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self._set_page(self._page - 1)
            else:
                self._set_page(self._page + 1)
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _accept_done(self):
        self.confirmed = True
        self.accept()


# ── 主窗口 ────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.result = None
        self._analyzing = False   # 防止重复点分析导致并发线程崩溃
        self.cache = ThumbnailCache()
        self.current_group_index = 0
        self.threshold = DEFAULT_THRESHOLD
        self.mode = MODE_STRICT
        self.enable_blur = False
        self.blur_threshold = 900   # 模糊识别敏感度（FFT 高频比×1500）
        self.file_filter = FILTER_ALL
        self.confirmed_groups = set()

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1420, 900)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── 顶栏 ────────────────────────────────────────────────
        top = QHBoxLayout()
        icon_path = asset("icon_256.png")
        if os.path.exists(icon_path):
            icon = QLabel()
            icon.setPixmap(QPixmap(icon_path).scaled(
                40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            top.addWidget(icon)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size:22px; font-weight:bold; color:#2a7de1;")
        top.addWidget(title)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet("color:#666; font-size:11px;")
        top.addWidget(ver)
        top.addStretch()

        # 关于按钮（右上角固定）
        about_btn = QPushButton("ℹ️ 关于")
        about_btn.setObjectName("ghost")
        about_btn.setFixedWidth(100)
        about_btn.setStyleSheet(
            "QPushButton { background:#2a2a2a; color:#e0e0e0;"
            "border:1px solid #555; border-radius:6px; padding:2px 6px;"
            "font-size:13px; }"
            "QPushButton:hover { background:#444; }")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        top.addWidget(about_btn)

        self.folder_label = QLabel("未选择文件夹")
        self.folder_label.setStyleSheet("color:#888;")
        top.addWidget(self.folder_label)
        self.browse_btn = QPushButton("📁 选择文件夹")
        self.browse_btn.clicked.connect(self._browse)
        top.addWidget(self.browse_btn)

        # ── 设置栏 ──────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel("照片格式:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("全部照片", FILTER_ALL)
        self.filter_combo.addItem("仅 JPG", FILTER_JPG)
        self.filter_combo.addItem("仅 RAW", FILTER_RAW)
        self.filter_combo.currentIndexChanged.connect(self._on_filter)
        self.filter_combo.currentIndexChanged.connect(
            lambda i: self.w_filter.setCurrentIndex(i)
            if hasattr(self, 'w_filter') else None)
        bar.addWidget(self.filter_combo)

        bar.addSpacing(14)
        bar.addWidget(QLabel("模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("严格去重（适用于大量连拍筛选）", MODE_STRICT)
        self.mode_combo.addItem("同主体筛选（适用于人像选片）", MODE_SUBJECT)
        self.mode_combo.currentIndexChanged.connect(
            lambda i: self.w_mode.setCurrentIndex(i)
            if hasattr(self, 'w_mode') else None)
        bar.addWidget(self.mode_combo)

        bar.addSpacing(14)
        bar.addWidget(QLabel("相似程度:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(1, 15)
        self.threshold_slider.setValue(self.threshold)
        self.threshold_slider.setFixedWidth(160)
        self.threshold_slider.valueChanged.connect(self._on_threshold)
        bar.addWidget(self.threshold_slider)
        self.threshold_value = QLabel(f"{self.threshold}")
        self.threshold_value.setStyleSheet(
            "color:#2a7de1; font-weight:bold; font-size:14px;")
        bar.addWidget(self.threshold_value)
        self.threshold_tip = QLabel("值越大 → 越多照片被归为一组")
        self.threshold_tip.setStyleSheet("color:#666; font-size:11px;")
        bar.addWidget(self.threshold_tip)

        # 模糊识别开关 + 敏感度
        bar.addSpacing(14)
        self.blur_check = QCheckBox("模糊识别")
        self.blur_check.setToolTip("分析后先预览模糊照片，可按回车快速删除")
        self.blur_check.setStyleSheet(
            "QCheckBox { color:#ccc; font-size:13px; spacing:6px; }"
            "QCheckBox::indicator { width:16px; height:16px; "
            "background:#2a2a2a; border:2px solid #555; border-radius:3px; }"
            "QCheckBox::indicator:checked { background:#2a7de1; border-color:#2a7de1; }")
        self.blur_check.toggled.connect(
            lambda v: self.w_blur_check.setChecked(v)
            if hasattr(self, 'w_blur_check') else None)
        bar.addWidget(self.blur_check)
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(0, 100)
        self.blur_slider.setValue(self.blur_threshold // 10)
        self.blur_slider.setFixedWidth(120)
        self.blur_slider.setToolTip(
            "模糊敏感度（0-100）：\n"
            "60-80：只标极端模糊\n"
            "80-88：中等——轻微失焦也标\n"
            "88-95：默认推荐范围\n"
            "95+：几乎全标（可能有误标）")
        self.blur_slider.valueChanged.connect(
            lambda v: setattr(self, 'blur_threshold', v * 10))
        self.blur_slider.valueChanged.connect(
            lambda v: self.blur_spin.setValue(v))
        self.blur_slider.valueChanged.connect(
            lambda v: self.w_blur_slider.setValue(v)
            if hasattr(self, 'w_blur_slider') else None)
        self.blur_slider.valueChanged.connect(
            lambda v: self.w_blur_spin.setValue(v)
            if hasattr(self, 'w_blur_spin') else None)
        bar.addWidget(self.blur_slider)
        # 精确输入框（无上下按钮，深色高对比边框）
        self.blur_spin = QSpinBox()
        self.blur_spin.setRange(0, 100)
        self.blur_spin.setValue(self.blur_threshold // 10)
        self.blur_spin.setFixedWidth(64)
        self.blur_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.blur_spin.setStyleSheet(
            "QSpinBox { background:#1e1e1e; color:#fff;"
            "border:2px solid #2a7de1; border-radius:4px;"
            "padding:2px 6px; font-weight:bold; font-size:13px; }")
        self.blur_spin.valueChanged.connect(
            lambda v: setattr(self, 'blur_threshold', v * 10))
        self.blur_spin.valueChanged.connect(
            lambda v: self.blur_slider.setValue(v))
        self.blur_spin.setToolTip("精确输入模糊阈值（0-100）")
        bar.addWidget(self.blur_spin)
        bar.addStretch()

        self.analyze_btn = QPushButton("🚀 开始分析")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self._start_analysis)
        bar.addWidget(self.analyze_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        # JPG+RAW 共同移动提示条（分析时醒目显示）
        self.pair_hint = QLabel("")
        self.pair_hint.setWordWrap(True)
        self.pair_hint.setStyleSheet(
            "color:#fbbf24; font-size:13px; background:#2a1a00;"
            "border:1px solid #d97706; border-radius:6px; padding:8px;")
        self.pair_hint.setVisible(False)
        root.addWidget(self.pair_hint)

        # ── 主工作区 ────────────────────────────────────────────
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # 欢迎页（居中显示选择/开始，分析后顶部栏才出现）
        self.welcome_page = QWidget()
        wl = QVBoxLayout(self.welcome_page)
        wl.addStretch()
        wmsg = QLabel("🎉 欢迎使用 PS！\n\n"
                      "不是 Photoshop，是 PhotoSelect ！\n"
                      "— by nfd")
        wmsg.setAlignment(Qt.AlignCenter)
        wmsg.setStyleSheet("color:#aaa; font-size:20px;")
        wl.addWidget(wmsg)
        wl.addSpacing(16)

        # 居中设置面板
        center_panel = QWidget()
        center_panel.setFixedWidth(520)
        cp = QVBoxLayout(center_panel)
        cp.setSpacing(10)

        self.welcome_folder_label = QLabel("📁 未选择文件夹")
        self.welcome_folder_label.setAlignment(Qt.AlignCenter)
        self.welcome_folder_label.setStyleSheet(
            "color:#888; font-size:13px; background:#2a2a2a;"
            "border:1px solid #444; border-radius:8px; padding:12px;")
        cp.addWidget(self.welcome_folder_label)

        browse_btn = QPushButton("📁 选择照片文件夹...")
        browse_btn.setObjectName("primary")
        browse_btn.clicked.connect(self._browse)
        cp.addWidget(browse_btn)

        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("照片格式:"))
        self.w_filter = QComboBox()
        self.w_filter.addItem("全部照片", FILTER_ALL)
        self.w_filter.addItem("仅 JPG", FILTER_JPG)
        self.w_filter.addItem("仅 RAW", FILTER_RAW)
        self.w_filter.currentIndexChanged.connect(
            lambda i: self.filter_combo.setCurrentIndex(i))
        opt_row.addWidget(self.w_filter)
        opt_row.addSpacing(10)
        opt_row.addWidget(QLabel("模式:"))
        self.w_mode = QComboBox()
        self.w_mode.addItem("严格去重（适用于大量连拍筛选）", MODE_STRICT)
        self.w_mode.addItem("同主体筛选（适用于人像选片）", MODE_SUBJECT)
        self.w_mode.currentIndexChanged.connect(
            lambda i: self.mode_combo.setCurrentIndex(i))
        opt_row.addWidget(self.w_mode)
        cp.addLayout(opt_row)

        # 相似程度滑块（带 i 信息）
        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel("相似程度:"))
        self.w_threshold = QSlider(Qt.Horizontal)
        self.w_threshold.setRange(1, 15)
        self.w_threshold.setValue(self.threshold)
        self.w_threshold.valueChanged.connect(self._on_threshold)
        sim_row.addWidget(self.w_threshold, 1)
        self.w_threshold_value = QLabel(f"{self.threshold}")
        self.w_threshold_value.setStyleSheet(
            "color:#2a7de1; font-weight:bold; font-size:14px;")
        sim_row.addWidget(self.w_threshold_value)
        info_btn = QLabel("ⓘ")
        info_btn.setToolTip(
            "相似程度含义：\n\n"
            "值越大，系统越宽松——差异稍大的照片也会被分进同一组（适合快速粗筛）；\n"
            "值越小越严格——只有几乎完全相同的照片才分一组（适合精确去重）。\n\n"
            "默认 7 是中间偏严。")
        info_btn.setStyleSheet("color:#2a7de1; font-size:16px; "
                               "background:#2a2a2a; border:1px solid #444;"
                               "border-radius:10px; padding:0 6px;")
        info_btn.setCursor(Qt.PointingHandCursor)
        sim_row.addWidget(info_btn)
        cp.addLayout(sim_row)

        # 模糊识别开关 + 敏感度
        blur_row = QHBoxLayout()
        self.w_blur_check = QCheckBox("🔍 识别模糊照片（分析后可快速删除）")
        self.w_blur_check.setStyleSheet(
            "QCheckBox { color:#ccc; font-size:13px; spacing:6px; }"
            "QCheckBox::indicator { width:16px; height:16px; "
            "background:#2a2a2a; border:2px solid #555; border-radius:3px; }"
            "QCheckBox::indicator:checked { background:#2a7de1; border-color:#2a7de1; }")
        self.w_blur_check.toggled.connect(
            lambda v: self.blur_check.setChecked(v)
            if hasattr(self, 'blur_check') else None)
        blur_row.addWidget(self.w_blur_check)
        self.w_blur_slider = QSlider(Qt.Horizontal)
        self.w_blur_slider.setRange(0, 100)
        self.w_blur_slider.setValue(self.blur_threshold // 10)
        self.w_blur_slider.valueChanged.connect(
            lambda v: setattr(self, 'blur_threshold', v * 10))
        self.w_blur_slider.valueChanged.connect(
            lambda v: self.blur_slider.setValue(v)
            if hasattr(self, 'blur_slider') else None)
        self.w_blur_slider.valueChanged.connect(
            lambda v: self.w_blur_spin.setValue(v)
            if hasattr(self, 'w_blur_spin') else None)
        blur_row.addWidget(self.w_blur_slider, 1)
        self.w_blur_spin = QSpinBox()
        self.w_blur_spin.setRange(0, 100)
        self.w_blur_spin.setValue(self.blur_threshold // 10)
        self.w_blur_spin.setFixedWidth(64)
        self.w_blur_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.w_blur_spin.setStyleSheet(
            "QSpinBox { background:#1e1e1e; color:#fff;"
            "border:2px solid #2a7de1; border-radius:4px;"
            "padding:2px 6px; font-weight:bold; font-size:13px; }")
        self.w_blur_spin.valueChanged.connect(
            lambda v: setattr(self, 'blur_threshold', v * 10))
        self.w_blur_spin.valueChanged.connect(
            lambda v: self.w_blur_slider.setValue(v))
        self.w_blur_spin.valueChanged.connect(
            lambda v: self.blur_slider.setValue(v)
            if hasattr(self, 'blur_slider') else None)
        self.w_blur_spin.setToolTip("直接输入模糊阈值（0-100）")
        blur_row.addWidget(self.w_blur_spin)
        blur_info = QLabel("ⓘ")
        blur_info.setToolTip(
            "模糊敏感度含义（0-100）：\n\n"
            "软件用 FFT 频域分析扫描整张照片——\n"
            "清晰照片有丰富的高频细节（边缘锐利），\n"
            "模糊照片能量集中在低频（画面平滑）。\n\n"
            "60-80：只标极端模糊（对焦失败、严重手抖）\n"
            "80-88：中等——轻微失焦也会标\n"
            "88-95：默认推荐范围——平衡准确率\n"
            "95+：宽松——几乎全标，可能误标\n\n"
            "建议：先用 90 跑一次 → 有漏标就降低\n"
            "有误标就提高，几次就找到适合你的值\n\n"
            "⚠ 注意：FFT 算法对极其轻微的失焦有局限。\n"
            "模糊判断不完美，仅供辅助参考。")
        blur_info.setStyleSheet("color:#2a7de1; font-size:16px; "
                                "background:#2a2a2a; border:1px solid #444;"
                                "border-radius:10px; padding:0 6px;")
        blur_info.setCursor(Qt.PointingHandCursor)
        blur_row.addWidget(blur_info)
        cp.addLayout(blur_row)

        self.w_start_btn = QPushButton("🚀 开始分析")
        self.w_start_btn.setObjectName("success")
        self.w_start_btn.setFixedHeight(44)
        self.w_start_btn.clicked.connect(self._start_analysis)
        cp.addWidget(self.w_start_btn)

        wl.addWidget(center_panel, 0, Qt.AlignCenter)
        wl.addStretch()

        # 底部许可小字
        license_tip = QLabel(
            "免费个人使用 · 禁止商业用途 · by nfd\n"
            "商用请邮件 745936837@qq.com 或微信 13917034098")
        license_tip.setAlignment(Qt.AlignCenter)
        license_tip.setStyleSheet("color:#666; font-size:11px;")
        wl.addWidget(license_tip)
        self.stack.addWidget(self.welcome_page)

        # 顶部栏/设置栏（初始隐藏，分析后显示）
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)
        top_layout.addLayout(top)
        top_layout.addLayout(bar)
        top_widget.setVisible(False)
        self.top_widget = top_widget
        root.addWidget(top_widget)

        # 分组总览页
        self.overview_page = QWidget()
        ol = QVBoxLayout(self.overview_page)
        ol.setContentsMargins(0, 0, 0, 0)
        self.overview_host = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_host)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(self.overview_host)
        self.stack.addWidget(self.overview_page)

        # 选图页
        self.review_page = QWidget()
        rl = QVBoxLayout(self.review_page)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀ 上一组")
        self.prev_btn.setObjectName("ghost")
        self.prev_btn.clicked.connect(lambda: self._nav_group(-1))
        self.next_btn = QPushButton("下一组 ▶")
        self.next_btn.setObjectName("ghost")
        self.next_btn.clicked.connect(lambda: self._nav_group(1))
        self.group_indicator = QLabel("")
        self.group_indicator.setAlignment(Qt.AlignCenter)
        self.group_indicator.setStyleSheet(
            "color:#ccc; font-size:14px; font-weight:bold;")
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.group_indicator, 1)
        nav.addWidget(self.next_btn)

        self.overview_btn = QPushButton("📋 分组总览")
        self.overview_btn.setObjectName("ghost")
        self.overview_btn.clicked.connect(self._show_overview)
        nav.addWidget(self.overview_btn)
        self.done_btn = QPushButton("✅ 筛选完毕")
        self.done_btn.setObjectName("success")
        self.done_btn.setVisible(False)
        self.done_btn.clicked.connect(self._show_done_overview)
        nav.addWidget(self.done_btn)
        self.export_btn = QPushButton("📤 导出")
        self.export_btn.setObjectName("warning")
        self.export_btn.clicked.connect(self._export_kept)
        nav.addWidget(self.export_btn)
        rl.addLayout(nav)

        self.review_host = QWidget()
        self.review_layout = QVBoxLayout(self.review_host)
        self.review_layout.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.review_host, 1)

        self.stack.addWidget(self.review_page)

        QShortcut(QKeySequence(Qt.Key_Left), self, self._prev_group_shortcut)
        QShortcut(QKeySequence(Qt.Key_Right), self, self._next_group_shortcut)

        # 全部按钮 NoFocus：防止 ←→ 键被按钮焦点吃掉（←→ 始终用于翻页/切组）
        for _b in self.findChildren(QPushButton):
            _b.setFocusPolicy(Qt.NoFocus)

        self.statusBar().showMessage(
            "选择照片文件夹 → 选择类型/模式/阈值 → 开始分析")

    def _current_panel(self):
        if self.review_layout.count():
            return self.review_layout.itemAt(0).widget()
        return None

    def _prev_group_shortcut(self):
        if self.stack.currentWidget() is not self.review_page:
            return
        panel = self._current_panel()
        # 先翻页，翻到第一页再切上一组
        if panel is not None and panel.has_prev_page():
            panel._set_page(panel.page - 1)
        else:
            self._nav_group(-1)

    def _next_group_shortcut(self):
        if self.stack.currentWidget() is not self.review_page:
            return
        panel = self._current_panel()
        # 先翻页，翻到最后一页再切下一组
        if panel is not None and panel.has_next_page():
            panel._set_page(panel.page + 1)
        else:
            self._nav_group(1)

    # ── 设置 ────────────────────────────────────────────────────
    def _on_filter(self, idx):
        self.file_filter = self.filter_combo.currentData()

    def _on_threshold(self, val):
        self.threshold = val
        self.threshold_value.setText(f"{val}")
        self.w_threshold_value.setText(f"{val}")
        # 双向同步滑块（避免信号循环）
        if hasattr(self, 'w_threshold') and self.threshold_slider.value() != val:
            self.threshold_slider.blockSignals(True)
            self.threshold_slider.setValue(val)
            self.threshold_slider.blockSignals(False)
        if hasattr(self, 'w_threshold') and self.w_threshold.value() != val:
            self.w_threshold.blockSignals(True)
            self.w_threshold.setValue(val)
            self.w_threshold.blockSignals(False)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "选择照片文件夹")
        if folder:
            self.folder_label.setText(folder)
            self.folder_label.setToolTip(folder)
            self.welcome_folder_label.setText(f"📁 {folder}")
            self.welcome_folder_label.setToolTip(folder)

    # ── 分析 ────────────────────────────────────────────────────
    def _start_analysis(self, skip_confirm=False):
        # 防止重复点击导致多个分析线程并发崩溃
        if self._analyzing:
            return
        folder = self.folder_label.text()
        if not folder or folder == "未选择文件夹":
            QMessageBox.warning(self, "提示", "请先选择照片文件夹！")
            return
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "提示", "文件夹不存在！")
            return

        # 已有分析结果（已进入分组总览/选图）→ 提示会丢失当前操作
        if self.result is not None and not skip_confirm:
            ret = QMessageBox.question(
                self, "重新分析",
                "重新分析将丢弃当前的分组和保留选择，"
                "\n已移入「待删除」的照片会保留在文件夹中不受影响。"
                "\n\n确定要重新开始吗？",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return

        # 从顶部栏读取设置（欢迎页与顶部栏已双向同步）
        self.mode = self.mode_combo.currentData()
        self.file_filter = self.filter_combo.currentData()
        self.threshold = self.threshold_slider.value()
        self.enable_blur = self.blur_check.isChecked()
        self.blur_threshold = self.blur_slider.value() * 10
        self._analyzing = True
        self.analyze_btn.setEnabled(False)
        self.w_start_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.top_widget.setVisible(True)
        self.stack.setCurrentWidget(self.welcome_page)

        # JPG+RAW 配对醒目提示（全部照片模式）
        self.pair_hint.setVisible(False)
        if self.file_filter == FILTER_ALL:
            try:
                n_pairs = count_jpg_raw_pairs(folder)
                if n_pairs > 0:
                    self.pair_hint.setText(
                        f"🔗 已启用 JPG+RAW 共同移动：{n_pairs} 对同名 JPG/RAW "
                        f"将合并为一张显示（如 xxx.JPG/NEF），选择/移动/导出时一起移动。"
                        "\n如需分离两类图片，请进文件夹自行调整，"
                        f"或改用「仅 JPG」/「仅 RAW」模式。")
                    self.pair_hint.setVisible(True)
            except Exception:
                pass

        self.thread = AnalyzeThread(folder, self.threshold, self.mode,
                                    self.file_filter,
                                    enable_blur=self.enable_blur,
                                    blur_threshold=self.blur_threshold)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished_ok.connect(self._on_analysis_done)
        self.thread.failed.connect(self._on_analysis_failed)
        self.thread.start()

    def _on_progress(self, cur, total, msg):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(cur)
        self.statusBar().showMessage(msg)

    def _on_analysis_failed(self, err):
        self.progress.setVisible(False)
        self._analyzing = False
        self.analyze_btn.setEnabled(True)
        self.w_start_btn.setEnabled(True)
        QMessageBox.critical(self, "分析失败", str(err))

    def _on_analysis_done(self, result):
        self.result = result
        self._analyzing = False
        self.progress.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.w_start_btn.setEnabled(True)
        self.confirmed_groups = set()

        # JPG+RAW 配对（仅全部照片模式）：同名 JPG/RAW 视为一张
        self.pairs = {}
        if self.file_filter == FILTER_ALL:
            self.pairs = build_jpg_raw_pairs(result)
            result.pairs = self.pairs
            if self.pairs:
                self.statusBar().showMessage(
                    f"已启用 JPG+RAW 共同移动：{len(self.pairs)//2} 对同名 JPG/RAW "
                    f"已合并为一张显示（如 xxx.JPG/NEF）\n"
                    f"如需分离两类图片，请进文件夹自行调整或改用「仅 JPG/仅 RAW」模式")

        # 统计
        n_total = len(result.photos)
        n_in_groups = sum(len(g.photos) for g in result.groups)
        n_singles = len(result.singles)
        n_groups = len(result.groups)

        mode_name = "同主体筛选" if result.mode == MODE_SUBJECT else "严格去重"
        failed = getattr(result, 'failed_count', 0)
        self.statusBar().showMessage(
            f"分析完成（{mode_name}）：共 {n_total} 张照片，"
            f"{n_in_groups} 张进入筛选（{n_groups}组），"
            f"{n_singles} 张独张"
            + (f"，{failed} 张读取失败已跳过" if failed else ""))

        # 模糊预览（如果有模糊照片且开关已启用）
        blurry = getattr(result, 'blurry_photos', [])
        if blurry and self.enable_blur:
            dlg = BlurPreviewDialog(result, self.cache, parent=self)
            dlg.exec()
            if dlg.reanalyze:
                # 放弃本次分析，回到主界面（保留设置，由用户自己点开始分析）
                self.result = None
                self.progress.setVisible(False)
                self.top_widget.setVisible(True)
                self.stack.setCurrentWidget(self.welcome_page)
                return

        if result.groups:
            # 进入分组总览
            self._show_overview()
            QMessageBox.information(
                self, "分析完成",
                f"📊 共 {n_total} 张照片\n\n"
                f"• 需要筛选：{n_in_groups} 张（分成 {n_groups} 组）\n"
                f"• 未进入筛选：{n_singles} 张独张\n\n"
                f"已进入「分组总览」，可检查/调整分组后开始选图。")
        else:
            self.stack.setCurrentWidget(self.welcome_page)
            QMessageBox.information(
                self, "分析完成",
                f"共 {n_total} 张照片，未发现相似组（{n_singles} 张独张）。")

    # ── 分组总览 ────────────────────────────────────────────────
    def _show_overview(self):
        if not self.result:
            return
        while self.overview_layout.count():
            item = self.overview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        panel = GroupOverviewPanel(self.result, self.cache)
        panel._on_start = self._start_review_from_overview
        self.overview_layout.addWidget(panel)
        self.stack.setCurrentWidget(self.overview_page)

    def _start_review_from_overview(self):
        """从分组总览进入选图"""
        if not self.result or not self.result.groups:
            QMessageBox.warning(self, "提示", "还没有分组！")
            return
        self.current_group_index = 0
        self.stack.setCurrentWidget(self.review_page)
        self._show_group(0)

    # ── 大图选图 ────────────────────────────────────────────────
    def _show_group(self, index):
        if not self.result or not self.result.groups:
            return
        if 0 <= index < len(self.result.groups):
            self.current_group_index = index
            while self.review_layout.count():
                item = self.review_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            panel = ReviewPanel(self.result.groups[index], self.cache, index,
                                pairs=getattr(self, 'pairs', {}))
            panel.confirmed.connect(self._on_group_confirmed)
            panel.undone.connect(self._on_group_undone)
            panel.confirmed_with_msg.connect(self._on_group_confirmed_msg)
            panel.reset_all_requested.connect(self._reset_all_groups)
            self.review_layout.addWidget(panel)
            self._update_indicator()

    def _on_group_confirmed_msg(self, index, msg):
        """组确认后：跳转完成时在目标面板显示提示"""
        # 若还有下一组（自动跳转），跳到后显示；若已全部确认，显示在当前面板
        all_done = (len(self.confirmed_groups) == len(self.result.groups))
        if not all_done:
            # 等跳转完成（_on_group_confirmed 里已 _show_group）
            QTimer.singleShot(0, lambda: self._show_notice_on_current(msg))
        else:
            self._show_notice_on_current(msg)

    def _show_notice_on_current(self, msg):
        """在当前显示的 ReviewPanel 上显示提示"""
        if self.review_layout.count():
            panel = self.review_layout.itemAt(0).widget()
            if hasattr(panel, '_show_notice'):
                panel._show_notice(msg)

    def _reset_all_groups(self):
        """一键重置全部筛选：撤销所有确认，恢复所有照片，重新开始"""
        n_confirmed = sum(1 for g in self.result.groups if g.confirmed)
        # 强警示确认
        ret = QMessageBox.warning(
            self, "⚠️ 重置全部筛选",
            f"确定要重置全部筛选吗？\n\n"
            f"· 将撤销 {n_confirmed} 个已确认的组\n"
            f"· 把已移入「{TRASH_DIR_NAME}」的照片全部恢复\n"
            f"· 所有组的保留选择清空，重新开始\n\n"
            f"此操作不可撤销，确定继续？",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        # 恢复所有已删除的照片（每个组各自恢复自己组的）
        n_restored = 0
        for g in self.result.groups:
            if g.confirmed:
                folder = os.path.dirname(g.photos[0].path)
                deleted = [p.path for p in g.photos
                           if p.path not in (g.kept_paths or set())]
                n_restored += restore_from_trash(deleted, folder)
            # 重置状态
            g.confirmed = False
            g.kept_paths = None
            g.user_keep = None
            g.pending_kept_paths = None
        self.confirmed_groups.clear()
        self.done_btn.setVisible(False)
        self.current_group_index = 0
        self._show_group(0)
        play_success_sound()
        panel = self.review_layout.itemAt(0).widget() \
            if self.review_layout.count() else None
        if panel is not None:
            panel._show_notice(
                f"↺ 已重置全部筛选：恢复 {n_restored} 张照片，"
                f"所有组回到未确认状态。")

    def _nav_group(self, delta):
        if not self.result or not self.result.groups:
            return
        n = len(self.result.groups)
        new_idx = (self.current_group_index + delta) % n
        self._show_group(new_idx)

    def _update_indicator(self):
        n = len(self.result.groups)
        confirmed = sum(1 for g in self.result.groups if g.confirmed)
        self.group_indicator.setText(
            f"组 {self.current_group_index + 1} / {n}"
            f"    （已确认 {confirmed} / {n}）")

    def _on_group_confirmed(self, index):
        self.confirmed_groups.add(index)
        self._update_indicator()
        # 全部确认完 → 显示筛选完毕按钮
        all_done = (len(self.confirmed_groups) == len(self.result.groups))
        self.done_btn.setVisible(all_done)
        # 自动跳转到下一组（还没确认的）
        if not all_done:
            n = len(self.result.groups)
            nxt = index
            for _ in range(n):
                nxt = (nxt + 1) % n
                if nxt not in self.confirmed_groups:
                    break
            self._show_group(nxt)

    def _on_group_undone(self, index):
        self.confirmed_groups.discard(index)
        self._update_indicator()
        self.done_btn.setVisible(False)

    # ── 筛选结果总览 ────────────────────────────────────────────
    def _show_done_overview(self):
        """筛选完毕：显示每组保留的照片总览，可确认完成或返回调整"""
        if not self.result or not self.result.groups:
            return
        # 检查是否全部确认
        if len(self.confirmed_groups) != len(self.result.groups):
            QMessageBox.warning(self, "提示", "还有未确认的组，请先完成所有组的筛选！")
            return

        dlg = DoneOverviewDialog(self.result, self.cache, self)
        if dlg.exec() and dlg.confirmed:
            play_success_sound()
            # 可选导出
            self._export_kept()
            QMessageBox.information(
                self, "🎉 全部完成",
                "终于选完啦，辛苦啦！🌟\n\n"
                "被删除的照片在「待删除」文件夹中，\n"
                "确认无误后可手动删除释放空间。\n\n"
                "保留的照片都留在原文件夹里了，随时可用~")

    # ── 导出 ────────────────────────────────────────────────────
    def _export_kept(self):
        if not self.result:
            return
        # 所有保留的照片（每组可能保留多张；全删组跳过）
        kept = []
        for g in self.result.groups:
            if g.kept_paths:
                kept.extend(p.path for p in g.photos
                            if p.path in g.kept_paths)
            elif g.confirmed and g.user_keep is not None:
                kept.append(g.user_keep.path)
            elif not g.confirmed and g.recommended_keep is not None:
                kept.append(g.recommended_keep.path)
        singles = [s.path for s in self.result.singles]
        all_paths = [p.path for p in self.result.photos.values()]

        dlg = ExportDialog(len(kept), len(singles), self)
        if not dlg.exec():
            return

        dest = QFileDialog.getExistingDirectory(self, "选择导出目标文件夹")
        if not dest:
            return

        mode = dlg.selected_mode()
        to_copy = []
        desc = []
        # JPG+RAW 配对：导出时一起导出
        def _expand(p):
            out = [p]
            if p in self.pairs:
                out.append(self.pairs[p])
            return out
        if mode == "kept":
            to_copy = []
            for k in kept:
                to_copy.extend(_expand(k))
            desc.append(f"保留照片 {len(kept)} 张")
        elif mode == "singles":
            to_copy = []
            for s in singles:
                to_copy.extend(_expand(s))
            desc.append(f"独张 {len(singles)} 张")
        else:  # all
            to_copy = []
            for k in kept:
                to_copy.extend(_expand(k))
            for s in singles:
                to_copy.extend(_expand(s))
            desc.append(f"保留照片 {len(kept)} 张 + 独张 {len(singles)} 张")

        if not to_copy:
            QMessageBox.warning(self, "提示", "没有选择要导出的照片！")
            return

        ok, skipped = copy_kept(to_copy, dest)
        QMessageBox.information(
            self, "导出完成",
            f"已导出 {ok} 张（{' + '.join(desc)}）到：\n{dest}\n"
            + (f"（跳过已存在的 {skipped} 张）" if skipped else ""))


def main():
    try:
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 替换系统弹窗为自定义（消 Windows 系统音，播专属音效）
    _patch_message_boxes()

    icon_path = asset("icon_256.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.show()
    # 启动许可提醒（等窗口显示后再弹）
    QTimer.singleShot(400, lambda: LicenseReminderDialog(win).exec())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
