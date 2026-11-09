#!/usr/bin/env python3
# Winter Desktop — macOS edition
# Requirements: python3 -m pip install PySide6 pyobjc-framework-Cocoa pyobjc-framework-Quartz

import json
import math
import os
import random
import sys
import time
from pathlib import Path
from ctypes import c_void_p

from PySide6.QtCore import Qt, QTimer, QRect, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPainterPath, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QComboBox, QMessageBox
)

APP_NAME = "Winter Desktop"
CONFIG_DIR = Path.home() / "Library" / "Application Support" / "WinterDesktop"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULTS = {
    "enabled": True,
    "density": 1.0,
    "speed": 1.0,
    "flake_size": 1.0,
    "brightness": 1.0,
    "behind_ratio": 35,
    "shake_sensitivity": 12,
    "fps": 60,
}

def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def install_autostart(enabled):
    """Create/remove a standard macOS LaunchAgent."""
    agent_dir = Path.home() / "Library" / "LaunchAgents"
    plist = agent_dir / "com.winterdesktop.app.plist"
    if not enabled:
        try:
            plist.unlink()
        except FileNotFoundError:
            pass
        return
    agent_dir.mkdir(parents=True, exist_ok=True)
    import plistlib
    if getattr(sys, "frozen", False):
        # In a PyInstaller .app, sys.executable points to Contents/MacOS/WinterDesktop.
        program_arguments = [sys.executable]
    else:
        program_arguments = [sys.executable, str(Path(__file__).resolve())]
    payload = {
        "Label": "com.winterdesktop.app",
        "ProgramArguments": program_arguments,
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    plist.write_bytes(plistlib.dumps(payload))
    os.system(f'launchctl unload "{plist}" >/dev/null 2>&1; launchctl load "{plist}" >/dev/null 2>&1')

def screen_geometry():
    screens = QApplication.screens()
    rect = screens[0].geometry()
    for s in screens[1:]:
        rect = rect.united(s.geometry())
    return rect

def snowflake_path(cx, cy, radius, angle=0.0):
    path = QPainterPath()
    ca, sa = math.cos(angle), math.sin(angle)
    for arm in range(6):
        a = angle + arm * math.pi / 3
        x2, y2 = cx + math.cos(a) * radius, cy + math.sin(a) * radius
        path.moveTo(cx, cy)
        path.lineTo(x2, y2)
        for side in (-1, 1):
            bx = cx + math.cos(a) * radius * 0.62
            by = cy + math.sin(a) * radius * 0.62
            ba = a + side * 0.72
            path.moveTo(bx, by)
            path.lineTo(bx - math.cos(ba) * radius * 0.25,
                        by - math.sin(ba) * radius * 0.25)
    return path

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "r", "phase", "spin", "angle", "clump", "seed", "alpha")
    def __init__(self, x, y, cfg, clump=False):
        self.x, self.y = x, y
        self.clump = clump
        self.seed = random.random() * 1000
        self.phase = random.random() * math.tau
        self.angle = random.random() * math.tau
        if clump:
            scale = cfg["flake_size"]
            self.r = random.uniform(7, 15) * scale
            self.vx = random.uniform(-65, 65)
            self.vy = random.uniform(30, 95)
            self.spin = random.uniform(-3.4, 3.4)
            self.alpha = random.randint(210, 255)
        else:
            self.r = random.uniform(1.4, 4.2) * cfg["flake_size"]
            self.vx = random.uniform(-13, 13)
            self.vy = random.uniform(32, 95)
            self.spin = random.uniform(-1.2, 1.2)
            self.alpha = random.randint(150, 255)

class SnowOverlay(QWidget):
    def __init__(self, rect, cfg, foreground):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if foreground:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.cfg = cfg
        self.foreground = foreground
        self.setGeometry(rect)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.particles = []
        self.last = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(8, int(1000 / max(30, min(120, cfg["fps"])))))
        self._set_native_level()

        for _ in range(int(170 * cfg["density"])):
            p = Particle(random.uniform(0, rect.width()), random.uniform(0, rect.height()), cfg)
            self.particles.append(p)

    def _set_native_level(self):
        # Native levels make the two layers sit on opposite sides of ordinary app windows.
        try:
            from AppKit import NSWindow, NSDesktopWindowLevel, NSFloatingWindowLevel
            from objc import objc_object
            native_view = objc_object(c_void_p=int(self.winId()))
            native_window = native_view.window()
            native_window.setLevel_(NSFloatingWindowLevel if self.foreground else NSDesktopWindowLevel)
        except Exception:
            # Qt's always-on-top flag remains a useful fallback for the front layer.
            pass

    def update_config(self, cfg):
        self.cfg = cfg
        self.timer.setInterval(max(8, int(1000 / max(30, min(120, cfg["fps"])))))
        target = int(170 * cfg["density"])
        while len(self.particles) < target:
            self.particles.append(Particle(random.uniform(0, self.width()), random.uniform(-30, self.height()), cfg))
        if len(self.particles) > target:
            self.particles = self.particles[:target]
        self.update()

    def add_clump(self, x, y, count=2):
        for _ in range(count):
            if len(self.particles) < 850:
                self.particles.append(Particle(x + random.uniform(-18, 18),
                                               y + random.uniform(-8, 8), self.cfg, True))

    def tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.last)
        self.last = now
        w, h = self.width(), self.height()
        for p in self.particles:
            p.phase += dt * (0.8 if not p.clump else 1.6)
            p.angle += p.spin * dt
            p.vy += (26 if p.clump else 4) * dt * self.cfg["speed"]
            p.x += (p.vx + math.sin(p.phase) * (12 if not p.clump else 20)) * dt * self.cfg["speed"]
            p.y += p.vy * dt * self.cfg["speed"]
            p.vx *= (0.998 if not p.clump else 0.994)
            if p.y > h + p.r * 3 or p.x < -40 or p.x > w + 40:
                p.x = random.uniform(0, w)
                p.y = random.uniform(-90, -10)
                p.vx = random.uniform(-13, 13)
                p.vy = random.uniform(32, 95)
                p.clump = False
                p.r = random.uniform(1.4, 4.2) * self.cfg["flake_size"]
                p.alpha = random.randint(150, 255)
                p.spin = random.uniform(-1.2, 1.2)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        ratio = max(0, min(100, int(self.cfg["behind_ratio"])))
        # ratio is the percentage of particles shown behind normal windows.
        for index, p in enumerate(self.particles):
            is_behind = (index % 100) < ratio
            if is_behind != (not self.foreground):
                continue
            alpha = int(p.alpha * self.cfg["brightness"])
            alpha = max(0, min(255, alpha))
            if p.clump:
                self._draw_clump(painter, p, alpha)
            else:
                self._draw_flake(painter, p, alpha)
        painter.end()

    def _draw_flake(self, painter, p, alpha):
        r = p.r
        color = QColor(236, 248, 255, alpha)
        painter.setPen(QPen(color, max(0.8, r * 0.16), Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(snowflake_path(p.x, p.y, r, p.angle))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, int(alpha * 0.65)))
        painter.drawEllipse(QPointF(p.x, p.y), max(0.7, r * 0.13), max(0.7, r * 0.13))

    def _draw_clump(self, painter, p, alpha):
        # Irregular, rounded snow chunks instead of thin stick-like particles.
        painter.save()
        painter.translate(p.x, p.y)
        painter.rotate(math.degrees(p.angle))
        r = p.r
        path = QPainterPath()
        points = []
        for i in range(12):
            a = i * math.tau / 12
            rr = r * random.Random(int(p.seed + i * 17)).uniform(0.78, 1.12)
            points.append(QPointF(math.cos(a) * rr * 1.08, math.sin(a) * rr * 0.82))
        path.moveTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        painter.setPen(QPen(QColor(195, 220, 244, int(alpha * 0.8)), 1.0))
        painter.setBrush(QColor(235, 246, 255, alpha))
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, int(alpha * 0.85)))
        painter.drawEllipse(QPointF(-r * .22, -r * .18), r * .48, r * .32)
        painter.drawEllipse(QPointF(r * .28, r * .08), r * .35, r * .28)
        painter.restore()

class WindowShakeWatcher:
    """Detects moved windows via Quartz and sheds small snow clumps from their edges."""
    def __init__(self, overlays, cfg):
        self.overlays = overlays
        self.cfg = cfg
        self.previous = {}
        self.timer = QTimer()
        self.timer.timeout.connect(self.scan)
        self.timer.start(90)

    def scan(self):
        try:
            import Quartz
            rows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
            current = {}
            for row in rows:
                owner = row.get(Quartz.kCGWindowOwnerName, "")
                layer = row.get(Quartz.kCGWindowLayer, 0)
                number = row.get(Quartz.kCGWindowNumber)
                bounds = row.get(Quartz.kCGWindowBounds, {})
                if not number or layer != 0 or owner in ("Winter Desktop", "Window Server"):
                    continue
                x, y = float(bounds.get("X", 0)), float(bounds.get("Y", 0))
                w, h = float(bounds.get("Width", 0)), float(bounds.get("Height", 0))
                current[number] = (x, y, w, h)
                old = self.previous.get(number)
                if old:
                    dx, dy = x - old[0], y - old[1]
                    dist = math.hypot(dx, dy)
                    threshold = max(4, float(self.cfg["shake_sensitivity"]))
                    if dist >= threshold:
                        # Snow spills from the upper edge and sides as the window is moved.
                        px = x + w * random.uniform(0.15, 0.85)
                        py = y + min(24, h * 0.08)
                        for overlay in self.overlays:
                            local_x = px - overlay.x()
                            local_y = py - overlay.y()
                            overlay.add_clump(local_x, local_y, min(8, max(2, int(dist / 10))))
            self.previous = current
        except Exception:
            # Quartz permissions/API may be unavailable; cursor shake remains supported below.
            return

class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.overlays = []
        self.watcher = None
        self.setWindowTitle(APP_NAME)
        self.setFixedWidth(520)
        self.setStyleSheet("""
            QWidget { background:#0a1218; color:#e6f2ff; font-family: -apple-system, sans-serif; }
            QLabel#muted { color:#829cb3; font-size:12px; }
            QFrame#card { background:#12202b; border:1px solid #203748; border-radius:12px; }
            QPushButton { background:#1a3445; color:#e6f2ff; border:0; border-radius:9px; padding:10px 14px; }
            QPushButton:hover { background:#25485d; }
            QPushButton#primary { background:#22d3ee; color:#082f49; font-weight:700; }
            QSlider::groove:horizontal { height:6px; background:#1f2937; border-radius:3px; }
            QSlider::sub-page:horizontal { background:#22d3ee; border-radius:3px; }
            QSlider::handle:horizontal { background:white; border:2px solid #22d3ee; width:15px; margin:-6px 0; border-radius:8px; }
            QComboBox { background:#1a2c3a; border:0; border-radius:7px; padding:7px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("❄  Winter Desktop")
        title.setStyleSheet("font-size:25px; font-weight:700;")
        root.addWidget(title)
        subtitle = QLabel("Снегопад и сугробы на рабочем столе macOS")
        subtitle.setObjectName("muted")
        root.addWidget(subtitle)

        self.status = QLabel("Снег выключен")
        self.status.setStyleSheet("font-size:14px; font-weight:600;")
        root.addWidget(self.status)
        self.toggle_btn = QPushButton("Включить снег")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.clicked.connect(self.toggle)
        root.addWidget(self.toggle_btn)

        self.controls = {}
        self.add_slider(root, "Размер снежинок", "flake_size", 40, 220, 100, lambda v: f"{v}%")
        self.add_slider(root, "Яркость", "brightness", 15, 100, 100, lambda v: f"{v}%")
        self.add_slider(root, "Снег за окнами ↔ перед окнами", "behind_ratio", 0, 100, 35,
                        lambda v: f"{v}% за окнами / {100-v}% перед окнами")
        self.add_slider(root, "Лёгкость стряхивания", "shake_sensitivity", 4, 35, 12,
                        lambda v: "Легко" if v <= 8 else ("Средне" if v <= 20 else "Требуется сильнее встряхнуть"))
        self.add_slider(root, "Количество снега", "density", 30, 200, 100, lambda v: f"{v}%")
        self.add_slider(root, "Скорость падения", "speed", 40, 200, 100, lambda v: f"{v}%")

        buttons = QHBoxLayout()
        auto = QPushButton("Автозапуск: включить")
        auto.clicked.connect(lambda: self.set_autostart(True))
        noauto = QPushButton("Автозапуск: выключить")
        noauto.clicked.connect(lambda: self.set_autostart(False))
        buttons.addWidget(auto)
        buttons.addWidget(noauto)
        root.addLayout(buttons)

        note = QLabel("Слой «за окнами» располагается на уровне рабочего стола macOS; слой «перед окнами» — поверх обычных окон. macOS может ограничивать отображение поверх защищённых или полноэкранных окон.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.sync_overlays)
        self.poll.start(500)

    def add_slider(self, parent, label, key, lo, hi, default, formatter):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        row = QHBoxLayout()
        name = QLabel(label)
        value = QLabel(formatter(int(self.cfg.get(key, default))))
        value.setObjectName("muted")
        row.addWidget(name)
        row.addStretch()
        row.addWidget(value)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        initial = int(float(self.cfg.get(key, default / 100 if key in ("flake_size", "brightness", "density", "speed") else default)) * (100 if key in ("flake_size", "brightness", "density", "speed") else 1))
        value.setText(formatter(initial))
        slider.setValue(max(lo, min(hi, initial)))
        def changed(v):
            value.setText(formatter(v))
            if key in ("flake_size", "brightness", "density", "speed"):
                self.cfg[key] = v / 100.0
            else:
                self.cfg[key] = v
            save_config(self.cfg)
            for overlay in self.overlays:
                overlay.update_config(self.cfg)
        slider.valueChanged.connect(changed)
        layout.addLayout(row)
        layout.addWidget(slider)
        parent.addWidget(card)
        self.controls[key] = slider

    def toggle(self):
        if self.overlays:
            for o in self.overlays:
                o.close()
            self.overlays = []
            if self.watcher:
                self.watcher.timer.stop()
                self.watcher = None
            self.status.setText("Снег выключен")
            self.toggle_btn.setText("Включить снег")
            self.cfg["enabled"] = False
        else:
            rect = screen_geometry()
            # Separate windows: desktop-level snow and floating snow.
            back = SnowOverlay(rect, self.cfg, False)
            front = SnowOverlay(rect, self.cfg, True)
            back.show()
            front.show()
            self.overlays = [back, front]
            self.watcher = WindowShakeWatcher(self.overlays, self.cfg)
            self.status.setText("❄ Снег идёт")
            self.toggle_btn.setText("Выключить снег")
            self.cfg["enabled"] = True
        save_config(self.cfg)

    def sync_overlays(self):
        if not self.overlays:
            return
        rect = screen_geometry()
        for o in self.overlays:
            if o.geometry() != rect:
                o.setGeometry(rect)

    def set_autostart(self, enabled):
        try:
            install_autostart(enabled)
            QMessageBox.information(self, APP_NAME,
                "Автозапуск включён." if enabled else "Автозапуск выключен.")
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Не удалось изменить автозапуск:\n{exc}")

    def closeEvent(self, event):
        # Keep the snow running when settings are closed.
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    settings = SettingsWindow()
    settings.show()
    if settings.cfg.get("enabled", False):
        settings.toggle()
    sys.exit(app.exec())

if __name__ == "__main__":
    if sys.platform != "darwin":
        print("Эта версия предназначена для macOS.")
        sys.exit(1)
    main()
