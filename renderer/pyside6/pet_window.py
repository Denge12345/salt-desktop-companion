"""PySide6 desktop-pet shell (alternative to the Electron shell).

Run from the repository root:

    pip install PySide6
    python renderer/pyside6/pet_window.py

It reads pets/salt/pet.json + spritesheet.webp, plays the atlas rows with the
same timing table as the web renderer, and supports drag / click / right-click
state menu / always-on-top.

This file is intentionally dependency-light: no Qt Designer, no resources.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QAction, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

ROOT = Path(__file__).resolve().parents[2]
PET_DIR = ROOT / "pets" / "salt"
CELL_W, CELL_H = 192, 208
STATES = [
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
]
FRAMES = [6, 8, 8, 4, 5, 8, 6, 6, 6]
DURATIONS = [
    [200] * 6,
    [100] * 8,
    [100] * 8,
    [180, 150, 150, 180],
    [140, 110, 150, 130, 180],
    [170] * 8,
    [220] * 6,
    [150] * 6,
    [180] * 6,
]
LOOP = {
    "idle": True,
    "running-right": True,
    "running-left": True,
    "waving": False,
    "jumping": False,
    "failed": False,
    "waiting": True,
    "running": True,
    "review": True,
}
FALLBACK = {"waving": "idle", "jumping": "idle", "failed": "idle"}


class PetWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("莎露朵 · Salt")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.manifest = json.loads((PET_DIR / "pet.json").read_text(encoding="utf-8"))
        sheet_path = PET_DIR / self.manifest.get("spritesheetPath", "spritesheet.webp")
        img = QImage(str(sheet_path))
        if img.isNull():
            raise SystemExit(f"cannot load spritesheet: {sheet_path}")
        if img.width() != 1536 or img.height() != 2288:
            print(f"warning: atlas is {img.width()}x{img.height()}, expected 1536x2288")
        self.sheet = QPixmap.fromImage(img)

        self.scale = 1.35
        self.resize(round(CELL_W * self.scale), round(CELL_H * self.scale))
        self.state = "idle"
        self.index = 0
        self.elapsed = 0
        self.dragging = False
        self.drag_offset = QPoint()
        self.look = None
        self.setMouseTracking(True)
        self.press_position = QPoint()
        self.moved = False
        self.double_click = False
        self.clock = QElapsedTimer()
        self.clock.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    # -- state machine -----------------------------------------------------
    def play(self, state: str, restart: bool = True) -> None:
        if state not in STATES:
            return
        if state == self.state and not restart:
            return
        self.state = state
        self.index = 0
        self.elapsed = 0
        self.update()

    def tick(self) -> None:
        self.elapsed += min(250, self.clock.restart())
        row = STATES.index(self.state)
        durations = DURATIONS[row]
        count = FRAMES[row]
        while self.elapsed >= durations[self.index]:
            self.elapsed -= durations[self.index]
            self.index += 1
            if self.index >= count:
                if LOOP[self.state]:
                    self.index = 0
                else:
                    self.state = FALLBACK.get(self.state, "idle")
                    self.index = 0
                    self.elapsed = 0
                    break
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self.state == "idle" and self.look is not None:
            row, col = 9 + self.look // 8, self.look % 8
        else:
            row = STATES.index(self.state)
            col = self.index
        target = QRect(0, 0, self.width(), self.height())
        painter.drawPixmap(target, self.sheet, QRect(col * CELL_W, row * CELL_H, CELL_W, CELL_H))

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.press_position = event.globalPosition().toPoint()
            self.moved = False
            self.double_click = False
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.moved |= (event.globalPosition().toPoint() - self.press_position).manhattanLength() > 4
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        # Follow the pointer while idle.
        center = self.geometry().center()
        vx = event.globalPosition().x() - center.x()
        vy = event.globalPosition().y() - center.y()
        if math.hypot(vx, vy) > 12:
            angle = math.degrees(math.atan2(vx, -vy)) % 360
            self.look = round(angle / 22.5) % 16
        else:
            self.look = None

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            if not self.moved and not self.double_click:
                self.play("waving")

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_click = True
            self.play("jumping")

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.look = None
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        for state, label in [
            ("idle", "待机"),
            ("waving", "挥手"),
            ("jumping", "点赞庆祝"),
            ("failed", "失败"),
            ("waiting", "等待确认"),
            ("running", "工作中"),
            ("review", "检查中"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda _=False, s=state: self.play(s))
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())


def main() -> int:
    app = QApplication(sys.argv)
    win = PetWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
