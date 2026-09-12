# -*- coding: utf-8 -*-
"""
奶蛙的爱意提醒物语 · Windows 版
================================

把 macOS 原版（SwiftUI + AppKit，见 naiwa-love-reminder-1.0.0/app/NaiwaApp.swift，584 行）
迁移到 Windows（Python 3 + PySide6 / Qt 6）。

模块对照表（保持一一对应，方便跟原版对照阅读）：

    Swift 原版                       本文件
    ----------------------------     -----------------------------------------
    struct Reminder                  class Reminder        数据模型
    enum Assets                      class Assets          资源缓存
    final class PopupManager         class PopupManager    弹窗管理
    struct PopupView                 class PopupWindow     弹窗视图
    final class ReminderStore        class ReminderStore   提醒引擎
    struct ContentView               class MainWindow      主界面
    @main struct NaiwaApp            main() + build_tray() 入口 + 托盘

平台差异（完整对照表见 README.md）：

    MenuBarExtra（菜单栏）          -> QSystemTrayIcon（系统托盘）
    NSWindow.level = .floating      -> Qt.WindowStaysOnTopHint + WindowDoesNotAcceptFocus
    AVAudioPlayer                   -> QMediaPlayer（QtMultimedia）
    Bundle.main.url(forResource:)   -> sys._MEIPASS（打包后）/ 项目 assets（源码运行）
    ~/Library/Application Support   -> %APPDATA%\\NaiwaReminder\\
    DatePicker(.hourAndMinute)      -> QTimeEdit
    beginActivity()（防 App Nap）    -> 无需处理（Windows 没有 App Nap 机制）

数据文件与原版共用同一套 JSON 字段名（id/label/intervalSec/start/end/paused），
macOS 与 Windows 两边的提醒列表可以直接互相拷贝。
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# PyInstaller 打包后，PySide6 的扩展模块（QtCore.pyd 等）要按名字去加载
# shiboken6.abi3.dll，而 PySide6 6.11 把它放在单独的 shiboken6\ 目录里，
# 那个目录不在默认的 DLL 搜索路径上，直接 import 会报
# "DLL load failed while importing QtCore"。所以先挂进去再 import PySide6。
# （句柄要留着，被垃圾回收的话目录就失效了）
_DLL_DIR_HANDLES = []
if getattr(sys, "frozen", False):
    _bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    for _candidate in (_bundle_root, _bundle_root / "shiboken6", _bundle_root / "PySide6"):
        if _candidate.is_dir():
            _DLL_DIR_HANDLES.append(os.add_dll_directory(str(_candidate)))

from PySide6.QtCore import (QEasingCurve, QObject, Qt, QTime, QTimer, QUrl,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame,
                               QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QSpinBox,
                               QSystemTrayIcon, QTimeEdit, QVBoxLayout, QWidget)


# MARK: - 常量

APP_NAME = "奶蛙的爱意提醒物语"

YELLOW = "#FFC93C"        # 主色，原版 Color(1, 0.788, 0.235)
YELLOW_TEXT = "#6B4F00"   # 黄底上的文字，原版 Color(0.42, 0.31, 0)
INK = "#2B2B2B"           # 正文，原版 Color(0.17, 0.17, 0.17)
GRAY = "#8A8A8E"
LINE = "#ECECEC"          # 描边，原版 Color(0.925, 0.925, 0.925)
RED = "#FF3B30"

ST_ON, ST_WAIT, ST_OFF, ST_PAUSE = "on", "wait", "off", "pause"
STATUS_INFO = {
    ST_ON:    ("进行中",       "#33C759"),
    ST_WAIT:  ("未到开始时间", "#FF9400"),
    ST_OFF:   ("今天已结束",   "#C7C7CC"),
    ST_PAUSE: ("已暂停",       "#0A85FF"),
}


def resource_root() -> Path:
    """资源目录：打包后是 PyInstaller 临时目录，源码运行时是项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


ASSETS_DIR = resource_root() / "assets"
DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "NaiwaReminder"
REMINDERS_FILE = DATA_DIR / "reminders.json"
SETTINGS_FILE = DATA_DIR / "settings.json"


# MARK: - 资源缓存（原版 enum Assets）

class Assets:
    images: list[QPixmap] = []      # laugh1~7.png，弹窗轮播用
    sound_path: Path | None = None  # naiwa_laugh.mp3

    @classmethod
    def load(cls) -> None:
        cls.images = []
        for i in range(1, 8):
            path = ASSETS_DIR / f"laugh{i}.png"
            pixmap = QPixmap(str(path))
            if path.exists() and not pixmap.isNull():
                cls.images.append(pixmap)
        sound = ASSETS_DIR / "naiwa_laugh.mp3"
        cls.sound_path = sound if sound.exists() else None

    @classmethod
    def icon(cls) -> QIcon:
        """应用 / 托盘图标：优先用抠掉背景的 naiwa_tray.png。"""
        for name in ("naiwa_tray.png", "laugh2.png"):
            path = ASSETS_DIR / name
            if path.exists():
                return QIcon(str(path))
        return QIcon()


# MARK: - 数据模型（原版 struct Reminder）

@dataclass
class Reminder:
    label: str
    interval_sec: int
    start: str                          # "HH:mm"
    end: str                            # "HH:mm"
    paused: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    next_fire: datetime | None = None   # 仅运行时使用，不持久化

    # 与原版 JSON 字段名保持一致（camelCase），两边数据可互拷
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "intervalSec": self.interval_sec,
            "start": self.start,
            "end": self.end,
            "paused": self.paused,
        }

    @staticmethod
    def from_dict(d: dict) -> "Reminder":
        return Reminder(
            id=str(d.get("id") or uuid.uuid4()),
            label=str(d.get("label", "")),
            interval_sec=int(d.get("intervalSec", 60)),
            start=str(d.get("start", "00:00")),
            end=str(d.get("end", "23:59")),
            paused=bool(d.get("paused", False)),
        )


def minutes_of_day(moment: datetime) -> float:
    """时刻换算成"当天第几分钟"，对应原版 minutesNow。"""
    return moment.hour * 60 + moment.minute + moment.second / 60.0


def parse_hm(text: str) -> int:
    try:
        hour, minute = text.split(":")
        return int(hour) * 60 + int(minute)
    except Exception:
        return 0


def fmt_interval(sec: int) -> str:
    if sec % 3600 == 0:
        return f"{sec // 3600} 小时"
    if sec % 60 == 0:
        return f"{sec // 60} 分钟"
    return f"{sec} 秒"


# MARK: - 提醒引擎（原版 final class ReminderStore）

class ReminderStore(QObject):
    """0.5 秒心跳 + 生效时间段判定 + JSON 持久化。"""

    changed = Signal()   # 增删改：界面需要重建列表
    ticked = Signal()    # 每 0.5 秒心跳：界面刷新倒计时

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reminders: list[Reminder] = []
        self.load()
        self._timer = QTimer(self)
        self._timer.setInterval(500)              # 原版 Timer(timeInterval: 0.5)
        self._timer.timeout.connect(self.tick)
        self._timer.start()

    # --- 增删改 ---

    def get(self, rid: str) -> Reminder | None:
        for r in self.reminders:
            if r.id == rid:
                return r
        return None

    def add(self, label: str, interval_sec: int, start: str, end: str) -> None:
        self.reminders.append(Reminder(label=label, interval_sec=interval_sec,
                                       start=start, end=end))
        self.save()
        self.changed.emit()

    def update(self, rid: str, label: str, interval_sec: int, start: str, end: str) -> None:
        r = self.get(rid)
        if r is None:
            return
        r.label, r.interval_sec, r.start, r.end = label, interval_sec, start, end
        r.next_fire = None                        # 改了设置就重新起算
        self.save()
        self.changed.emit()

    def delete(self, rid: str) -> None:
        self.reminders = [r for r in self.reminders if r.id != rid]
        self.save()
        self.changed.emit()

    def toggle_pause(self, rid: str) -> None:
        r = self.get(rid)
        if r is None:
            return
        r.paused = not r.paused
        r.next_fire = None                        # 同原版：暂停/继续都重新起算
        self.save()
        self.changed.emit()

    # --- 时间逻辑（原版 inRange / status）---

    def in_range(self, r: Reminder, now: datetime) -> bool:
        m = minutes_of_day(now)
        s, e = float(parse_hm(r.start)), float(parse_hm(r.end))
        if s == e:
            return True                           # 开始 = 结束 视为全天生效
        if s < e:
            return s <= m < e
        return m >= s or m < e                    # 跨午夜，例如 22:00 ~ 02:00

    def status(self, r: Reminder, now: datetime) -> str:
        if r.paused:
            return ST_PAUSE
        if self.in_range(r, now):
            return ST_ON
        m = minutes_of_day(now)
        s, e = parse_hm(r.start), parse_hm(r.end)
        if s < e:
            return ST_OFF if m >= e else ST_WAIT
        # 跨午夜时"不在范围内"的时段是 [结束时间, 开始时间)，
        # 用中午 12 点分界：凌晨 = 今天那场刚结束，傍晚 = 今晚那场还没开始。
        # （原版这里一律显示"今天已结束"，本版顺手修正了文案，触发逻辑不变）
        return ST_OFF if m < 12 * 60 else ST_WAIT

    def countdown(self, r: Reminder, now: datetime) -> str:
        if self.status(r, now) != ST_ON or r.next_fire is None:
            return "—"
        diff = max(0, int((r.next_fire - now).total_seconds()))
        minute, second = divmod(diff, 60)
        return f"{minute}分{second}秒" if minute > 0 else f"{second}秒"

    # --- 心跳（原版 tick）---

    def tick(self) -> None:
        now = datetime.now()
        for r in self.reminders:
            if r.paused:
                continue
            if not self.in_range(r, now):
                r.next_fire = None                # 过了结束时间就停，第二天到点自动恢复
                continue
            if r.next_fire is None:
                r.next_fire = now + timedelta(seconds=r.interval_sec)
            if now >= r.next_fire:
                r.next_fire = now + timedelta(seconds=r.interval_sec)
                PopupManager.instance().fire(r.label)
        self.ticked.emit()

    # --- 持久化（原版 save / load）---

    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = [r.to_dict() for r in self.reminders]
            REMINDERS_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[naiwa] 保存失败: {exc}")

    def load(self) -> None:
        try:
            data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
            self.reminders = [Reminder.from_dict(d) for d in data]
        except FileNotFoundError:
            self.reminders = []
        except Exception as exc:
            print(f"[naiwa] 读取失败: {exc}")
            self.reminders = []


# MARK: - 偏好设置（音量，截图版有滑杆）

class Settings:
    def __init__(self):
        self.volume: float = 0.65
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.volume = max(0.0, min(1.0, float(data.get("volume", 0.65))))
        except Exception:
            pass

    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps({"volume": self.volume}, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as exc:
            print(f"[naiwa] 设置保存失败: {exc}")


# MARK: - 声音（原版 AVAudioPlayer）

class AudioEngine(QObject):
    """播放奶蛙笑声。QMediaPlayer 支持 mp3，音量可调（截图版的音量滑杆）。"""

    _instance: "AudioEngine | None" = None

    @classmethod
    def instance(cls) -> "AudioEngine":
        return cls._instance

    def __init__(self, volume: float = 0.65, parent=None):
        super().__init__(parent)
        self._output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._output)
        self.set_volume(volume)
        AudioEngine._instance = self

    def set_volume(self, value: float) -> None:
        self._output.setVolume(max(0.0, min(1.0, float(value))))

    def volume(self) -> float:
        return self._output.volume()

    def play(self) -> None:
        if Assets.sound_path is None:
            return
        source = QUrl.fromLocalFile(str(Assets.sound_path))
        # 原版每响一次新建一个 AVAudioPlayer（可以叠加），
        # 这里共用一个播放器：正在响时再触发就从头发声，避免几个提醒同时到点时炸耳朵。
        if self._player.source() != source:
            self._player.setSource(source)
        self._player.setPosition(0)
        self._player.play()

    def stop(self) -> None:
        self._player.stop()


# MARK: - 弹窗视图（原版 struct PopupView + 承载它的 NSWindow）

class PopupWindow(QWidget):
    CARD_W = 320            # 原版 .frame(width: 320)
    IMG_BOX = 200           # 图片容器（留出旋转余量，摇摆时不切角）
    IMG_SIZE = 170          # 原版 .frame(width: 190)；旋转后包围盒仍小于容器
    WOBBLE_DEG = 6.0        # 原版 rotationEffect ±6°
    WOBBLE_PERIOD = 0.6     # 原版 0.3 秒单程、自动往复
    CYCLE_MS = 300          # 原版 Timer.publish(every: 0.3) 轮播
    AUTO_CLOSE_MS = 20000   # 原版 20 秒自动关闭（无条件，不是"无操作才关"）

    def __init__(self, label: str, on_close=None, animate: bool = True):
        flags = (Qt.FramelessWindowHint            # 原版 styleMask = [.borderless]
                 | Qt.WindowStaysOnTopHint         # 原版 window.level = .floating
                 | Qt.Tool                         # 不在任务栏显示
                 | Qt.WindowDoesNotAcceptFocus)    # 不抢当前窗口的焦点（Windows 版专属考量）
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle(APP_NAME)

        self._on_close = on_close
        self._animate = animate
        self._started = time.monotonic()
        self._frame = random.randrange(max(1, len(Assets.images)))
        self._base_pixmap = self._scaled_frame(self._frame)
        self._final_geo = (0, 0, self.CARD_W, 400)

        self._build_ui(label)

        self._wobble_timer = QTimer(self)
        self._wobble_timer.setInterval(33)         # ~30 fps 的摇摆动画
        self._wobble_timer.timeout.connect(self._redraw_image)

        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(self.CYCLE_MS)
        self._cycle_timer.timeout.connect(self._next_frame)

    # --- 界面 ---

    def _build_ui(self, label: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 30, 30, 30)   # 原版 .padding(30)，给阴影留空间

        card = QFrame(self)
        card.setObjectName("popCard")
        card.setFixedWidth(self.CARD_W)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 46))       # 原版 .shadow(opacity: 0.18, radius: 24, y: 12)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        box = QVBoxLayout(card)
        box.setContentsMargins(28, 28, 28, 28)     # 原版 .padding(28)
        box.setSpacing(10)

        self.image_label = QLabel(card)
        self.image_label.setFixedSize(self.IMG_BOX, self.IMG_BOX)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.image_label.mousePressEvent = lambda _event: self.close()   # 原版 onTapGesture
        box.addWidget(self.image_label, 0, Qt.AlignHCenter)

        hint = QLabel("奶 蛙 提 醒 你", card)
        hint.setObjectName("popHint")
        hint.setAlignment(Qt.AlignCenter)
        box.addWidget(hint)

        text = QLabel(label, card)
        text.setObjectName("popLabel")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        box.addWidget(text)

        button = QPushButton("知道啦 😄", card)
        button.setObjectName("popBtn")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.close)
        box.addWidget(button, 0, Qt.AlignHCenter)

    # --- 动画 ---

    def _scaled_frame(self, index: int) -> QPixmap:
        if not Assets.images:
            return QPixmap()
        source = Assets.images[index % len(Assets.images)]
        return source.scaled(self.IMG_SIZE, self.IMG_SIZE,
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _next_frame(self) -> None:
        if not Assets.images:
            return
        self._frame = (self._frame + 1) % len(Assets.images)
        self._base_pixmap = self._scaled_frame(self._frame)
        self._redraw_image()

    def _redraw_image(self) -> None:
        """按 sin 曲线左右摇摆（等价于原版 repeatForever 的 ±6° 摆动）。"""
        if self._base_pixmap.isNull():
            return
        elapsed = time.monotonic() - self._started
        angle = self.WOBBLE_DEG * math.sin(2 * math.pi * elapsed / self.WOBBLE_PERIOD)
        canvas = QPixmap(self.IMG_BOX, self.IMG_BOX)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.translate(self.IMG_BOX / 2, self.IMG_BOX / 2)
        painter.rotate(angle)
        painter.drawPixmap(-self._base_pixmap.width() // 2,
                           -self._base_pixmap.height() // 2,
                           self._base_pixmap)
        painter.end()
        self.image_label.setPixmap(canvas)

    def _apply_pop(self, value: float) -> None:
        """弹入动画：从 85% 尺寸弹到 100%（原版 spring(response: 0.35) 的近似）。"""
        x, y, w, h = self._final_geo
        scale = 0.85 + 0.15 * value
        new_w, new_h = int(w * scale), int(h * scale)
        self.setGeometry(x + (w - new_w) // 2, y + (h - new_h) // 2, new_w, new_h)

    # --- 显示 ---

    def show_popup(self, index: int = 0) -> None:
        self.adjustSize()
        width, height = self.width(), self.height()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            offset = (index % 5) * 34              # 原版多个弹窗按 34px 错位堆叠
            x = area.center().x() - width // 2 + offset
            y = area.center().y() - height // 2 - offset
            self._final_geo = (x, y, width, height)
        else:
            self._final_geo = (0, 0, width, height)

        if self._animate:
            self.setWindowOpacity(0.0)
            self._apply_pop(0.0)
        self.show()
        self.raise_()

        if self._animate:
            geometry_anim = QVariantAnimation(self)
            geometry_anim.setStartValue(0.0)
            geometry_anim.setEndValue(1.0)
            geometry_anim.setDuration(240)
            geometry_anim.setEasingCurve(QEasingCurve.OutBack)
            geometry_anim.valueChanged.connect(lambda v: self._apply_pop(float(v)))
            geometry_anim.start()
            self._geometry_anim = geometry_anim

            opacity_anim = QVariantAnimation(self)
            opacity_anim.setStartValue(0.0)
            opacity_anim.setEndValue(1.0)
            opacity_anim.setDuration(160)
            opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            opacity_anim.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
            opacity_anim.start()
            self._opacity_anim = opacity_anim
        else:
            self._apply_pop(1.0)
            self.setWindowOpacity(1.0)

        self._started = time.monotonic()
        self._redraw_image()
        self._wobble_timer.start()
        self._cycle_timer.start()
        QTimer.singleShot(self.AUTO_CLOSE_MS, self.close)   # 20 秒自动关闭

    def closeEvent(self, event) -> None:
        self._wobble_timer.stop()
        self._cycle_timer.stop()
        if self._on_close is not None:
            self._on_close(self)
        super().closeEvent(event)


# MARK: - 弹窗管理（原版 final class PopupManager）

class PopupManager(QObject):
    _instance: "PopupManager | None" = None

    @classmethod
    def instance(cls) -> "PopupManager":
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows: list[PopupWindow] = []
        PopupManager._instance = self

    def fire(self, label: str) -> None:
        audio = AudioEngine.instance()
        if audio is not None:
            audio.play()
        window = PopupWindow(label, self._on_closed)
        window.show_popup(len(self._windows))
        self._windows.append(window)

    def close_all(self) -> None:
        for window in list(self._windows):
            window.close()

    def _on_closed(self, window: PopupWindow) -> None:
        if window in self._windows:
            self._windows.remove(window)
        window.deleteLater()


# MARK: - 通用小控件

def field_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardTitle")
    return label


def small_button(text: str, danger: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("small")
    button.setCursor(Qt.PointingHandCursor)
    if danger:
        button.setProperty("danger", True)      # QSS 里用 [danger="true"] 选择器染红
    return button


WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


# MARK: - 表单字段组（原版 ContentView.formCard 里的那三个输入块）

class ReminderFields(QWidget):
    """标签 + 间隔 + 时间范围，新建表单和编辑对话框共用。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        # 标签
        label_col = QVBoxLayout()
        label_col.setSpacing(6)
        label_col.addWidget(field_title("提醒我干嘛（标签）"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("例如：喝水、站起来活动、吃药…")
        self.label_edit.setMinimumWidth(200)
        self.label_edit.setFixedHeight(32)
        label_col.addWidget(self.label_edit)
        row.addLayout(label_col, 1)

        # 间隔
        interval_col = QVBoxLayout()
        interval_col.setSpacing(6)
        interval_col.addWidget(field_title("每隔多久提醒一次"))
        interval_row = QHBoxLayout()
        interval_row.setSpacing(6)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 9999)
        self.interval_spin.setValue(30)
        self.interval_spin.setFixedSize(76, 32)
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("秒", 1)
        self.unit_combo.addItem("分钟", 60)
        self.unit_combo.addItem("小时", 3600)
        self.unit_combo.setCurrentIndex(1)          # 默认分钟，同原版
        self.unit_combo.setFixedSize(88, 32)
        interval_row.addWidget(self.interval_spin)
        interval_row.addWidget(self.unit_combo)
        interval_col.addLayout(interval_row)
        row.addLayout(interval_col)

        # 时间范围
        time_col = QVBoxLayout()
        time_col.setSpacing(6)
        time_col.addWidget(field_title("生效时间范围（过了就停）"))
        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        self.start_edit = QTimeEdit()
        self.end_edit = QTimeEdit()
        for editor in (self.start_edit, self.end_edit):
            editor.setDisplayFormat("HH:mm")
            editor.setFixedHeight(32)
        now = datetime.now()
        self.start_edit.setTime(QTime(now.hour, now.minute))                 # 原版 startDate = Date()
        later = now + timedelta(hours=2)
        self.end_edit.setTime(QTime(later.hour, later.minute))               # 原版 endDate = +7200 秒
        time_row.addWidget(self.start_edit)
        dash = QLabel("~")
        dash.setObjectName("dash")
        time_row.addWidget(dash)
        time_row.addWidget(self.end_edit)
        time_col.addLayout(time_row)
        row.addLayout(time_col)

    def values(self) -> tuple[str, int, str, str]:
        unit = int(self.unit_combo.currentData() or 60)
        return (self.label_edit.text().strip(),
                self.interval_spin.value() * unit,
                self.start_edit.time().toString("HH:mm"),
                self.end_edit.time().toString("HH:mm"))

    def set_values(self, r: Reminder) -> None:
        self.label_edit.setText(r.label)
        seconds = r.interval_sec
        if seconds % 3600 == 0:
            unit, number = 3600, seconds // 3600
        elif seconds % 60 == 0:
            unit, number = 60, seconds // 60
        else:
            unit, number = 1, seconds
        self.unit_combo.setCurrentIndex({1: 0, 60: 1, 3600: 2}.get(unit, 1))
        self.interval_spin.setValue(max(1, number))
        self.start_edit.setTime(QTime.fromString(r.start, "HH:mm"))
        self.end_edit.setTime(QTime.fromString(r.end, "HH:mm"))


# MARK: - 编辑对话框（原版没有，截图版新增的「编辑」按钮）

class EditDialog(QDialog):
    def __init__(self, reminder: Reminder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑提醒")
        self.setModal(True)
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.addWidget(section_title("✏️ 编辑提醒"))

        self.fields = ReminderFields(self)
        self.fields.set_values(reminder)
        layout.addWidget(self.fields)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = small_button("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.setFixedWidth(120)
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def values(self) -> tuple[str, int, str, str]:
        return self.fields.values()


# MARK: - 提醒行（原版 ContentView.row）

class ReminderRow(QFrame):
    def __init__(self, store: ReminderStore, reminder: Reminder, parent=None):
        super().__init__(parent)
        self.setObjectName("row")
        self._store = store
        self._rid = reminder.id

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)       # 已结束的提醒整行变淡（原版 .opacity(0.55)）

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        self.dot = QLabel(self)
        self.dot.setFixedSize(10, 10)
        row.addWidget(self.dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        self.title = QLabel(self)
        self.title.setObjectName("rowMain")
        self.sub = QLabel(self)
        self.sub.setObjectName("rowSub")
        text_col.addWidget(self.title)
        text_col.addWidget(self.sub)
        row.addLayout(text_col, 1)

        count_col = QVBoxLayout()
        count_col.setSpacing(2)
        count_hint = QLabel("下次提醒", self)
        count_hint.setObjectName("countHint")
        count_hint.setAlignment(Qt.AlignRight)
        self.count = QLabel("—", self)
        self.count.setObjectName("countValue")
        self.count.setAlignment(Qt.AlignRight)
        self.count.setMinimumWidth(80)
        count_col.addWidget(count_hint)
        count_col.addWidget(self.count)
        row.addLayout(count_col)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.edit_button = small_button("编辑")
        self.test_button = small_button("测试")
        self.pause_button = small_button("暂停")
        self.delete_button = small_button("删除", danger=True)
        self.edit_button.clicked.connect(self._edit)
        self.test_button.clicked.connect(self._test)
        self.pause_button.clicked.connect(lambda: self._store.toggle_pause(self._rid))
        self.delete_button.clicked.connect(self._delete)
        for button in (self.edit_button, self.test_button,
                       self.pause_button, self.delete_button):
            buttons.addWidget(button)
        row.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        reminder = self._store.get(self._rid)
        if reminder is None:
            return
        now = datetime.now()
        status = self._store.status(reminder, now)
        status_text, status_color = STATUS_INFO[status]

        self.dot.setStyleSheet(f"background: {status_color}; border-radius: 5px;")
        self.title.setText(reminder.label)
        self.sub.setText(
            f"每 {fmt_interval(reminder.interval_sec)} 一次 · "
            f"{reminder.start} ~ {reminder.end} · {status_text}")
        self.count.setText(self._store.countdown(reminder, now))
        self.pause_button.setText("继续" if reminder.paused else "暂停")
        self._opacity.setOpacity(0.55 if status == ST_OFF else 1.0)

    # --- 按钮 ---

    def _test(self) -> None:
        reminder = self._store.get(self._rid)
        if reminder is not None:
            PopupManager.instance().fire(reminder.label)

    def _edit(self) -> None:
        reminder = self._store.get(self._rid)
        if reminder is None:
            return
        dialog = EditDialog(reminder, self.window())
        if dialog.exec() == QDialog.Accepted:
            label, interval_sec, start, end = dialog.values()
            if not label:
                QMessageBox.warning(self, "提示", "先写一下这个提醒是干嘛的～")
                return
            self._store.update(self._rid, label, interval_sec, start, end)

    def _delete(self) -> None:
        reminder = self._store.get(self._rid)
        if reminder is None:
            return
        answer = QMessageBox.question(
            self, "删除提醒", f"确定删掉「{reminder.label}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._store.delete(self._rid)


# MARK: - 样式表（对应原版里散落各处的颜色和圆角）

APP_QSS = """
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    color: #2B2B2B;
}
QWidget#root { background: #FFFFFF; }
QWidget#header {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #FFFDF5, stop:1 #FFFFFF);
}
QFrame#divider { background: #ECECEC; border: none; }
QLabel#appTitle { color: #8A8A8E; font-size: 13px; }
QLabel#dateLine { color: #8A8A8E; font-size: 14px; }
QLabel#fieldLabel { color: #8A8A8E; font-size: 12px; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; }
QLabel#rowMain { font-size: 15px; font-weight: 600; }
QLabel#rowSub { color: #8A8A8E; font-size: 12px; }
QLabel#countHint { color: #8A8A8E; font-size: 11px; }
QLabel#countValue { color: #2B2B2B; }
QLabel#emptyState {
    color: #8A8A8E;
    font-size: 13px;
    border: 1px dashed #ECECEC;
    border-radius: 16px;
}
QLabel#dash { color: #8A8A8E; }
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #ECECEC;
    border-radius: 16px;
}
QFrame#row {
    background: #FFFFFF;
    border: 1px solid #ECECEC;
    border-radius: 14px;
}
QLineEdit, QSpinBox, QComboBox, QTimeEdit {
    background: #FFFFFF;
    border: 1px solid #D9D9DE;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 13px;
    selection-background-color: #FFC93C;
    selection-color: #2B2B2B;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
    border: 1px solid #7EA6F0;
}
QSpinBox::up-button, QSpinBox::down-button,
QTimeEdit::up-button, QTimeEdit::down-button {
    width: 16px;
    background: transparent;
    border: none;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #ECECEC;
    selection-background-color: #FFF3D6;
    selection-color: #2B2B2B;
    outline: none;
}
QPushButton#primary {
    background: #FFC93C;
    color: #6B4F00;
    border: none;
    border-radius: 12px;
    padding: 11px 0;
    font-size: 15px;
    font-weight: 600;
}
QPushButton#primary:hover { background: #FFD469; }
QPushButton#primary:pressed { background: #F2BC2C; }
QPushButton#small {
    background: #FFFFFF;
    border: 1px solid #ECECEC;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    color: #2B2B2B;
}
QPushButton#small:hover { background: #F7F7F8; }
QPushButton#small[danger="true"] { color: #FF3B30; }
QSlider::groove:horizontal {
    height: 4px;
    background: #E3E3E8;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #2B7FFF; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #D5D5DA;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 8px;
}
QFrame#popCard { background: #FFFFFF; border-radius: 22px; }
QLabel#popHint { color: #8A8A8E; font-size: 12px; }
QLabel#popLabel { font-size: 26px; font-weight: 700; }
QPushButton#popBtn {
    background: #FFC93C;
    color: #6B4F00;
    border: none;
    border-radius: 17px;
    padding: 10px 30px;
    font-size: 16px;
    font-weight: 600;
}
QPushButton#popBtn:hover { background: #FFD469; }
QScrollArea { border: none; background: #FFFFFF; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #D5D5DA; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #BFBFC6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #FFFFFF; border: 1px solid #ECECEC; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 6px; }
QMenu::item:selected { background: #FFF3D6; }
"""


def ui_font(pixel_size: int, bold: bool = False, tabular: bool = True) -> QFont:
    """统一字体；tabular=True 尝试开启等宽数字（对应原版 monospacedDigit）。"""
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(pixel_size)
    if bold:
        font.setWeight(QFont.Bold)
    if tabular:
        try:
            font.setFeature(QFont.Tag("tnum"), 1)   # 数字等宽，秒数跳动时不抖动
        except Exception:
            pass
    return font


# MARK: - 主界面（原版 struct ContentView）

class MainWindow(QWidget):
    def __init__(self, store: ReminderStore, settings: Settings,
                 audio: AudioEngine, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(Assets.icon())
        self.resize(860, 730)              # 原版 defaultSize 800x680
        self.setMinimumSize(760, 640)      # 原版 minWidth 760 / minHeight 640

        self._store = store
        self._settings = settings
        self._audio = audio
        self._tray: QSystemTrayIcon | None = None
        self._tray_notice_shown = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        divider = QFrame(self)
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("root")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(20, 20, 20, 20)
        inner_layout.setSpacing(20)
        inner_layout.addWidget(self._build_form_card())
        inner_layout.addWidget(self._build_list_section())
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(500)          # 原版 Timer.publish(every: 0.5)
        self._clock_timer.timeout.connect(self._refresh_clock)
        self._clock_timer.start()

        self._store.changed.connect(self._rebuild_list)
        self._store.ticked.connect(self._refresh_rows)
        self._rebuild_list()
        self._refresh_clock()

    # --- 顶部时钟 ---

    def _build_header(self) -> QWidget:
        header = QWidget(self)
        header.setObjectName("header")
        column = QVBoxLayout(header)
        column.setContentsMargins(0, 18, 0, 18)     # 原版 .padding(.vertical, 18)
        column.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addStretch(1)
        if len(Assets.images) > 1:
            icon = QLabel(header)
            icon.setPixmap(Assets.images[1].scaled(30, 30, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation))
            title_row.addWidget(icon)
        title = QLabel(APP_NAME, header)
        title.setObjectName("appTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        column.addLayout(title_row)

        self.clock_label = QLabel("--:--:--", header)
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setFont(ui_font(54, bold=True))
        column.addWidget(self.clock_label)

        self.date_label = QLabel("", header)
        self.date_label.setObjectName("dateLine")
        self.date_label.setAlignment(Qt.AlignCenter)
        column.addWidget(self.date_label)
        return header

    # --- 新建提醒表单 ---

    def _build_form_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("card")
        column = QVBoxLayout(card)
        column.setContentsMargins(18, 18, 18, 18)   # 原版 .padding(18)
        column.setSpacing(14)
        column.addWidget(section_title("⏰ 新建提醒"))

        self.fields = ReminderFields(card)
        column.addWidget(self.fields)

        add_button = QPushButton("＋ 添加提醒", card)
        add_button.setObjectName("primary")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_reminder)
        column.addWidget(add_button)
        column.addLayout(self._build_volume_row(card))
        return card

    def _build_volume_row(self, parent: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        speaker = QLabel("🔊 音效音量", parent)
        speaker.setObjectName("fieldLabel")
        row.addWidget(speaker)

        self.volume_slider = QSlider(Qt.Horizontal, parent)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self._settings.volume * 100)))
        self.volume_slider.setFixedWidth(240)
        self.volume_slider.setCursor(Qt.PointingHandCursor)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        row.addWidget(self.volume_slider)

        self.volume_label = QLabel(f"{self.volume_slider.value()}%", parent)
        self.volume_label.setObjectName("countHint")
        self.volume_label.setFixedWidth(40)
        row.addWidget(self.volume_label)

        preview = small_button("试听")
        preview.clicked.connect(self._preview_sound)
        row.addWidget(preview)
        row.addStretch(1)
        return row

    # --- 提醒列表 ---

    def _build_list_section(self) -> QWidget:
        box = QWidget(self)
        box.setObjectName("root")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(section_title("📋 我的提醒（可同时开多个）"))

        self.list_container = QWidget(box)
        self.list_container.setObjectName("root")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)
        outer.addWidget(self.list_container)
        return box

    def _rebuild_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not self._store.reminders:
            empty = QLabel("还没有提醒，在上面添加一个吧 👆", self.list_container)
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFixedHeight(100)
            self.list_layout.addWidget(empty)
            return

        for reminder in self._store.reminders:
            self.list_layout.addWidget(ReminderRow(self._store, reminder,
                                                   self.list_container))

    def _refresh_rows(self) -> None:
        for index in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(index).widget()
            if isinstance(widget, ReminderRow):
                widget.refresh()

    # --- 交互 ---

    def _refresh_clock(self) -> None:
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(
            f"{now.year} 年 {now.month} 月 {now.day} 日 · {WEEKDAYS[now.weekday()]}")

    def _add_reminder(self) -> None:
        label, interval_sec, start, end = self.fields.values()
        if not label:
            QMessageBox.warning(self, "提示", "先写一下这个提醒是干嘛的～")
            return
        if interval_sec <= 0:
            QMessageBox.warning(self, "提示", "间隔要大于 0 哦")
            return
        self._store.add(label, interval_sec, start, end)
        self.fields.label_edit.clear()          # 原版添加后把标签清空

    def _on_volume_changed(self, value: int) -> None:
        volume = value / 100.0
        self._settings.volume = volume
        if self._audio is not None:
            self._audio.set_volume(volume)
        self.volume_label.setText(f"{value}%")
        self._settings.save()

    def _preview_sound(self) -> None:
        if self._audio is not None:
            self._audio.play()

    # --- 窗口行为 ---

    def set_tray(self, tray: QSystemTrayIcon) -> None:
        self._tray = tray

    def show_from_tray(self) -> None:
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        # 原版 applicationShouldTerminateAfterLastWindowClosed -> false：
        # 关掉主窗口只是收起来，App 继续在后台盯着你。
        event.ignore()
        self.hide()
        if self._tray is not None and not self._tray_notice_shown:
            self._tray_notice_shown = True
            self._tray.showMessage(APP_NAME,
                                   "奶蛙去后台盯着你了，点托盘里的小奶蛙能把我叫回来 🐸",
                                   Assets.icon(), 4000)


# MARK: - 托盘（原版 MenuBarExtra）

def build_tray(app: QApplication, window: MainWindow) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(Assets.icon(), app)
    tray.setToolTip(APP_NAME)

    menu = QMenu()
    open_action = menu.addAction("打开主窗口")
    open_action.triggered.connect(window.show_from_tray)
    menu.addSeparator()
    quit_action = menu.addAction("退出奶蛙提醒")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            window.show_from_tray()

    tray.activated.connect(on_activated)
    tray.show()
    window.set_tray(tray)
    return tray


# MARK: - 入口（原版 @main struct NaiwaApp）

def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)     # 关掉主窗口 App 不退出
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(APP_QSS)
    return app


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--screenshot" in argv:
        return run_screenshot_mode(argv)

    app = create_app(argv)
    Assets.load()                            # QPixmap / QIcon 必须先有 QApplication 才能建
    app.setWindowIcon(Assets.icon())
    settings = Settings()
    audio = AudioEngine(settings.volume)
    PopupManager()                            # 建好弹窗管理器单例
    store = ReminderStore()                   # 启动提醒引擎
    window = MainWindow(store, settings, audio)
    build_tray(app, window)
    window.show()
    app.aboutToQuit.connect(settings.save)
    return app.exec()


def run_screenshot_mode(argv: list[str]) -> int:
    """开发用：离屏渲染主界面和弹窗并导出 PNG，方便在没有桌面的环境里检查界面。"""
    index = argv.index("--screenshot")
    out_dir = Path(argv[index + 1]) if len(argv) > index + 1 else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(argv[:index] + argv[index + 2:])
    Assets.load()
    app.setWindowIcon(Assets.icon())
    settings = Settings()
    audio = AudioEngine(settings.volume)
    PopupManager()

    store = ReminderStore()
    now = datetime.now()
    demo_a = Reminder(label="眨眼", interval_sec=1800, start="00:00", end="23:59")
    demo_a.next_fire = now + timedelta(minutes=18, seconds=59)
    demo_b = Reminder(label="护眼", interval_sec=1200, start="00:00", end="23:59")
    demo_b.next_fire = now + timedelta(minutes=14, seconds=18)
    demo_c = Reminder(label="喝水", interval_sec=1800,
                      start=(now + timedelta(hours=1)).strftime("%H:%M"),
                      end=(now + timedelta(hours=2)).strftime("%H:%M"))
    store.reminders = [demo_a, demo_b, demo_c]

    window = MainWindow(store, settings, audio)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.resize(880, 900)
    window.show()
    app.processEvents()
    window.grab().save(str(out_dir / "main.png"))

    popup = PopupWindow("远眺 20 秒", None, animate=False)
    popup.setAttribute(Qt.WA_DontShowOnScreen, True)
    popup.show_popup(0)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    popup.grab().save(str(out_dir / "popup.png"))

    print(f"[naiwa] 截图已保存到 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
