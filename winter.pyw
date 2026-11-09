"""
Winter Desktop - снег на рабочем столе Windows 11 + окно настроек.
"""
import sys, os, json, math, random, ctypes, subprocess, webbrowser, re
from ctypes import wintypes as wt

APP = "WinterDesktop"
MUTEX = "WinterDesktopMutex"
EV_QUIT = "WinterDesktopQuit"
EV_CLEAR = "WinterDesktopClear"
CFG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "WinterDesktop")
CFG = os.path.join(CFG_DIR, "config.json")

DEFAULT = dict(mode="snow", speed=1.0, density=1.0, pile_rate=1.0, max_pile=16, fps=60,
               flake_size=1.0, brightness=1.0, behind_ratio=35)

MODES = {
    "snow":   dict(ru="Снег",   n=200, vy=(40, 90),   wob=0.8, wind=0.10, rain=False,
                   pile_top=(255, 255, 255, 250), pile_bot=(212, 229, 252, 250)),
    "sakura": dict(ru="Сакура", n=70,  vy=(35, 70),   wob=1.6, wind=0.50, rain=False,
                   pile_top=(255, 226, 237, 250), pile_bot=(244, 168, 198, 250)),
    "leaves": dict(ru="Листья", n=55,  vy=(40, 85),   wob=1.8, wind=0.60, rain=False,
                   pile_top=(238, 154, 62, 250),  pile_bot=(166, 82, 30, 250)),
    "rain":   dict(ru="Дождь",  n=260, vy=(520, 820), wob=0.0, wind=1.20, rain=True,
                   pile_top=(143, 186, 255, 0),   pile_bot=(143, 186, 255, 0)),
}
ORDER = list(MODES)

HINTS = {
    "snow": {
        "speed": "Как быстро летят снежинки. ×1.0 — обычно, левее — медленно, правее — быстро.",
        "density": "Сколько снежинок на экране сразу: от лёгкой позёмки до метели.",
        "pile_rate": "Как быстро снег копится на окнах, панели задач и курсоре."
    },
    "sakura": {
        "speed": "Как быстро кружат лепестки. ×1.0 — обычно, левее — медленно, правее — быстро.",
        "density": "Сколько лепестков на экране сразу: от пары штук до весенней бури.",
        "pile_rate": "Как быстро лепестки скапливаются на окнах. Совсем влево — отключить."
    },
    "leaves": {
        "speed": "Как быстро летят листья. ×1.0 — обычно, левее — медленно, правее — быстро.",
        "density": "Сколько листьев на экране сразу: от лёгкого листопада до осенней бури.",
        "pile_rate": "Как быстро листья копятся на окнах. Совсем влево — отключить."
    },
    "rain": {
        "speed": "Как быстро падают капли. ×1.0 — обычно, левее — медленно, правее — ливень.",
        "density": "Сколько капель на экране сразу: от мелкого дождика до проливного.",
        "pile_rate": "Дождь не образует сугробов (настройка не влияет на дождь)."
    }
}

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.OpenMutexW.restype = wt.HANDLE
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.OpenEventW.restype = wt.HANDLE
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.SetEvent.argtypes = [wt.HANDLE]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


# ---------- конфиг ----------
def load_cfg():
    d = dict(DEFAULT)
    try:
        with open(CFG, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    if d["mode"] not in MODES:
        d["mode"] = "snow"
    return d

def save_cfg(d):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

# ---------- запуск / автозапуск ----------
def overlay_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--overlay"]
    py = sys.executable
    if py.lower().endswith("python.exe"):
        py = py[:-10] + "pythonw.exe"
    return [py, os.path.abspath(__file__), "--overlay"]

def is_running():
    h = kernel32.OpenMutexW(0x100000, False, MUTEX)
    if h:
        kernel32.CloseHandle(h)
        return True
    return False

def start_overlay():
    if not is_running():
        subprocess.Popen(overlay_cmd(), creationflags=0x00000008 | 0x00000200, close_fds=True)

def signal(name):
    h = kernel32.OpenEventW(0x0002, False, name)
    if h:
        kernel32.SetEvent(h)
        kernel32.CloseHandle(h)

def autostart_get():
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(k, APP)
        winreg.CloseKey(k)
        return True
    except OSError:
        return False

def autostart_set(on):
    import winreg
    try:
        # CreateKey надежнее OpenKey, так как сразу дает права на запись
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        if on:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}" --overlay'
            else:
                py = sys.executable
                if py.lower().endswith("python.exe"):
                    py = py[:-10] + "pythonw.exe"
                cmd = f'"{py}" "{os.path.abspath(__file__)}" --overlay'
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP)
            except FileNotFoundError:
                pass
        winreg.CloseKey(k)
    except Exception:
        pass

# =====================================================================
#                      ИКОНКА И ЯРЛЫКИ
# =====================================================================
def get_clean_b64():
    # Жесткая очистка base64: удаляем всё кроме валидных символов, восстанавливаем паддинг
    clean = re.sub(r'[^A-Za-z0-9+/]', '', ICO_B64)
    pad = 4 - (len(clean) % 4)
    if pad != 4:
        clean += "=" * pad
    return clean

def ensure_icon():
    import base64
    path = os.path.join(CFG_DIR, "winter.ico")
    try:
        data = base64.b64decode(get_clean_b64())
        current = None
        try:
            with open(path, "rb") as f:
                current = f.read()
        except OSError:
            pass
        if current != data:
            os.makedirs(CFG_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return path
    except Exception:
        return None

def icon_png_b64(size=64):
    import base64, struct
    try:
        data = base64.b64decode(get_clean_b64())
        count = struct.unpack_from("<H", data, 4)[0]
        for i in range(count):
            w, h, _, _, _, _, ln, off = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
            if (w or 256) == size:
                return base64.b64encode(data[off:off + ln]).decode()
    except Exception:
        pass
    return None

def make_shortcut(where):
    ico = ensure_icon() or ""
    if getattr(sys, "frozen", False):
        target, args = sys.executable, ""
        wd = os.path.dirname(sys.executable)
    else:
        py = sys.executable
        if py.lower().endswith("python.exe"):
            py = py[:-10] + "pythonw.exe"
        target, args = py, f'"{os.path.abspath(__file__)}"'
        wd = os.path.dirname(os.path.abspath(__file__))
    ps = (
        "$w = New-Object -ComObject WScript.Shell\n"
        "if ($env:WD_WHERE -eq 'start') { $dir = Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs' }\n"
        "else { $dir = [Environment]::GetFolderPath('Desktop') }\n"
        "$s = $w.CreateShortcut((Join-Path $dir 'Winter Desktop.lnk'))\n"
        "$s.TargetPath = $env:WD_TARGET; $s.Arguments = $env:WD_ARGS; $s.WorkingDirectory = $env:WD_DIR\n"
        "if ($env:WD_ICON) { $s.IconLocation = $env:WD_ICON + ',0' }\n"
        "$s.Description = 'Winter Desktop - снег на рабочем столе'; $s.Save()\n"
    )
    env = dict(os.environ, WD_WHERE=where, WD_TARGET=target, WD_ARGS=args, WD_DIR=wd, WD_ICON=ico)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           env=env, capture_output=True, text=True, creationflags=0x08000000)
        return r.returncode == 0, (r.stderr or "").strip()
    except Exception as e:
        return False, str(e)


# =====================================================================
#                              ОКНО НАСТРОЕК
# =====================================================================
C_BG, C_CARD, C_CARD2, C_HOVER = "#0a1218", "#12202b", "#1a2c3a", "#253d50"
C_TXT, C_MUTED, C_ACC, C_ACC_H = "#e6f2ff", "#829cb3", "#22d3ee", "#67e8f9"
C_GOOD, C_OFF, C_RED, C_RED_H, C_TRACK = "#34d399", "#4b5563", "#fb7185", "#fda4af", "#1f2937"
C_DARK = "#082f49"
SC = 1.0


def S(x):
    return int(round(x * SC))

def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def run_settings():
    import tkinter as tk
    global SC
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try: 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WinterDesktop.Settings")
    except Exception:
        pass

    cfg = load_cfg()
    root = tk.Tk()
    root.title("Winter Desktop")
    root.configure(bg=C_BG)
    root.resizable(False, False)
    SC = max(1.0, root.winfo_fpixels("1i") / 96.0)
    ico = ensure_icon()
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    def rrect(cv, x1, y1, x2, y2, r, **kw):
        p = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
             x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(p, smooth=True, **kw)

    class Pill(tk.Canvas):
        def __init__(self, parent, text, cmd, w, h=34, bg=C_CARD2, fg=C_TXT, hover=C_HOVER, pbg=C_CARD, bold=False):
            super().__init__(parent, width=S(w), height=S(h), bg=pbg, highlightthickness=0, bd=0, cursor="hand2")
            self.w, self.h, self.cmd = S(w), S(h), cmd
            self.style(text, bg, fg, hover, bold)
            self.bind("<Enter>", lambda e: self.paint(self.hov))
            self.bind("<Leave>", lambda e: self.paint(self.bg))
            self.bind("<ButtonRelease-1>", lambda e: self.cmd() if 0 <= e.x <= self.w and 0 <= e.y <= self.h else None)

        def style(self, text, bg, fg, hover, bold=None):
            self.text, self.bg, self.fg, self.hov = text, bg, fg, hover
            if bold is not None:
                self.bold = bold
            self.paint(bg)

        def paint(self, col):
            self.delete("all")
            rrect(self, 1, 1, self.w - 1, self.h - 1, self.h // 2, fill=col, outline="")
            self.create_text(self.w / 2, self.h / 2, text=self.text, fill=self.fg,
                             font=("Segoe UI", 9, "bold" if self.bold else "normal"))

    class Slider(tk.Canvas):
        def __init__(self, parent, lo, hi, val, cmd):
            super().__init__(parent, height=S(24), bg=C_CARD, highlightthickness=0, bd=0, cursor="hand2")
            self.lo, self.hi, self.v, self.cmd = lo, hi, val, cmd
            self.bind("<Configure>", lambda e: self.draw())
            self.bind("<Button-1>", self.pick)
            self.bind("<B1-Motion>", self.pick)

        def draw(self):
            self.delete("all")
            w, h, pad = self.winfo_width(), self.winfo_height(), S(10)
            if w < 30: return
            y = h // 2
            x = pad + (w - 2 * pad) * (self.v - self.lo) / (self.hi - self.lo)
            self.create_line(pad, y, w - pad, y, width=S(6), capstyle="round", fill=C_TRACK)
            self.create_line(pad, y, max(pad + 1, x), y, width=S(6), capstyle="round", fill=C_ACC)
            r = S(9)
            self.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline=C_ACC, width=S(3))

        def pick(self, e):
            w, pad = self.winfo_width(), S(10)
            t = min(1.0, max(0.0, (e.x - pad) / max(1, w - 2 * pad)))
            self.v = self.lo + t * (self.hi - self.lo)
            self.draw()
            self.cmd(self.v)

        def set(self, v):
            self.v = v
            self.draw()

    class Switch(tk.Canvas):
        def __init__(self, parent, on, cmd):
            super().__init__(parent, width=S(48), height=S(26), bg=C_CARD, highlightthickness=0, bd=0, cursor="hand2")
            self.on, self.cmd = on, cmd
            self.bind("<Button-1>", lambda e: self.toggle())
            self.draw()

        def toggle(self):
            self.on = not self.on
            self.draw()
            self.cmd(self.on)

        def draw(self):
            self.delete("all")
            w, h = S(48), S(26)
            rrect(self, 1, 1, w - 1, h - 1, h // 2, fill=C_ACC if self.on else C_OFF, outline="")
            r = h // 2 - S(4)
            cx = w - h // 2 if self.on else h // 2
            self.create_oval(cx - r, h // 2 - r, cx + r, h // 2 + r, fill="#ffffff", outline="")

    def card(parent, title=None):
        f = tk.Frame(parent, bg=C_CARD, padx=S(14), pady=S(12))
        f.pack(fill="x", pady=(0, S(10)))
        if title:
            tk.Label(f, text=title, bg=C_CARD, fg=C_MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, S(8)))
        return f

    # ---------- шапка со снегопадом ----------
    WIN_W, HEAD_H = S(740), S(104)
    head = tk.Canvas(root, width=WIN_W, height=HEAD_H, highlightthickness=0, bd=0, bg=C_BG)
    head.pack()
    for y in range(HEAD_H):
        head.create_line(0, y, WIN_W, y, fill=mix("#0f2a3f", C_BG, y / HEAD_H))
    flakes = []
    for _ in range(46):
        r = random.uniform(1.2, 3.2) * SC
        x, y = random.uniform(0, WIN_W), random.uniform(0, HEAD_H)
        item = head.create_oval(x - r, y - r, x + r, y + r, fill=mix("#a5f3fc", "#ffffff", random.random()), outline="")
        flakes.append([x, y, r, random.uniform(0.4, 1.3) * SC, random.uniform(0, 6.28), item])
    logo_b64 = icon_png_b64(64)
    if logo_b64:
        try:
            root._logo = tk.PhotoImage(data=logo_b64)
            head.create_image(S(24), HEAD_H // 2, image=root._logo, anchor="w")
        except Exception:
            pass
    head.create_text(S(24) + S(80), HEAD_H // 2 - S(12), text="Winter Desktop", anchor="w",
                     fill="#ffffff", font=("Segoe UI Semibold", 20))
    head.create_text(S(24) + S(82), HEAD_H // 2 + S(16), text="снег на рабочем столе", anchor="w",
                     fill="#67e8f9", font=("Segoe UI", 10))

    def snowfall():
        for f in flakes:
            f[1] += f[3]
            f[4] += 0.05
            f[0] += math.sin(f[4]) * 0.4 * SC
            if f[1] > HEAD_H + 6:
                f[1], f[0] = -6, random.uniform(0, WIN_W)
            head.coords(f[5], f[0] - f[2], f[1] - f[2], f[0] + f[2], f[1] + f[2])
        root.after(40, snowfall)

    snowfall()

    body = tk.Frame(root, bg=C_BG)
    body.pack(padx=S(16), pady=(S(14), 0), fill="x")
    left = tk.Frame(body, bg=C_BG, width=S(330))
    right = tk.Frame(body, bg=C_BG, width=S(360))
    left.pack(side="left", fill="y", anchor="n")
    right.pack(side="left", fill="both", expand=True, padx=(S(14), 0), anchor="n")

    # ---------- ЛЕВО: статус ----------
    c = card(left)
    row = tk.Frame(c, bg=C_CARD)
    row.pack(fill="x")
    dot = tk.Canvas(row, width=S(14), height=S(14), bg=C_CARD, highlightthickness=0, bd=0)
    dot.pack(side="left", padx=(0, S(8)))
    stat = tk.Label(row, text="", bg=C_CARD, fg=C_TXT, font=("Segoe UI Semibold", 11))
    stat.pack(side="left")
    power = Pill(row, "Включить", lambda: None, 112, 34, bg=C_ACC, fg=C_DARK, hover=C_ACC_H, bold=True)
    power.pack(side="right")

    def on_power():
        if is_running():
            signal(EV_QUIT)
            return
        if not getattr(sys, "frozen", False):
            import importlib.util
            if importlib.util.find_spec("PySide6") is None:
                from tkinter import messagebox
                if not messagebox.askyesno("Winter Desktop", "Установить модуль PySide6 (ок. 100 МБ)?"):
                    return
                root.update()
                py = sys.executable
                if py.lower().endswith("pythonw.exe"):
                    py = py[:-11] + "python.exe"
                subprocess.run([py, "-m", "pip", "install", "pyside6-essentials"],
                               capture_output=True, text=True, creationflags=0x08000000)
        start_overlay()

    power.cmd = on_power

    def refresh_status():
        dot.delete("all")
        if is_running():
            dot.create_oval(1, 1, S(13), S(13), fill=C_GOOD, outline="")
            stat.config(text="Снег идёт")
            power.style("Выключить", C_RED, C_DARK, C_RED_H, True)
        else:
            dot.create_oval(1, 1, S(13), S(13), fill=C_OFF, outline="")
            stat.config(text="Снег выключен")
            power.style("Включить", C_ACC, C_DARK, C_ACC_H, True)
        root.after(1000, refresh_status)

    # ---------- ЛЕВО: режим ----------
    save_job = [None]
    sliders = {}

    def save_later():
        if save_job[0]:
            root.after_cancel(save_job[0])
        save_job[0] = root.after(150, lambda: save_cfg(cfg))

    def update_hints():
        k = cfg["mode"]
        if "speed" in sliders:
            sliders["speed"][3].config(text=HINTS[k]["speed"])
            sliders["density"][3].config(text=HINTS[k]["density"])
            sliders["pile_rate"][3].config(text=HINTS[k]["pile_rate"])

    c = card(left, "ЧТО ПАДАЕТ")
    grid = tk.Frame(c, bg=C_CARD)
    grid.pack(fill="x")
    chips = {}

    def pick_mode(k):
        cfg["mode"] = k
        save_later()
        for kk, ch in chips.items():
            if kk == k:
                ch.style(MODES[kk]["ru"], C_ACC, C_DARK, C_ACC_H, True)
            else:
                ch.style(MODES[kk]["ru"], C_CARD2, C_TXT, C_HOVER, False)
        update_hints()

    for i, k in enumerate(ORDER):
        ch = Pill(grid, MODES[k]["ru"], (lambda kk=k: pick_mode(kk)), 142, 34)
        ch.grid(row=i // 2, column=i % 2, padx=(0, S(6)) if i % 2 == 0 else 0, pady=(0, S(6)))
        chips[k] = ch
    pick_mode(cfg["mode"])

    # ---------- ЛЕВО: система ----------
    c = card(left, "СИСТЕМА")
    row = tk.Frame(c, bg=C_CARD)
    row.pack(fill="x", pady=(0, S(10)))
    tk.Label(row, text="Запускать вместе с Windows", bg=C_CARD, fg=C_TXT, font=("Segoe UI", 10)).pack(side="left")

    def on_auto(state):
        autostart_set(state)

    sw = Switch(row, autostart_get(), on_auto)
    sw.pack(side="right")

    Pill(c, "Ярлык на рабочий стол", lambda: make_shortcut("desktop"), 302, 34).pack(pady=(0, S(6)))
    Pill(c, "Ярлык в меню Пуск", lambda: make_shortcut("start"), 302, 34).pack()

    # ---------- ЛЕВО: поддержка ----------
    c_don = card(left, "ПОДДЕРЖКА ПРОЕКТА")
    Pill(c_don, "☕ Поддержать автора (DonationAlerts)", 
         lambda: webbrowser.open("https://www.donationalerts.com/r/rna1n"), 
         302, 34, bg="#f97316", fg="#ffffff", hover="#fb923c", bold=True).pack()
    Pill(c_don, "🌟 Открытый код (GitHub)", 
         lambda: webbrowser.open("https://github.com/Dororofofofor"), 
         302, 34, bg="#374151", fg="#ffffff", hover="#4b5563", bold=True).pack(pady=(S(6), 0))

    # ---------- ПРАВО: ползунки ----------
    c = card(right, "НАСТРОЙКИ")

    def add_slider(title, key, lo, hi, fmt, hint):
        box = tk.Frame(c, bg=C_CARD)
        box.pack(fill="x", pady=(0, S(10)))
        top = tk.Frame(box, bg=C_CARD)
        top.pack(fill="x")
        tk.Label(top, text=title, bg=C_CARD, fg=C_TXT, font=("Segoe UI Semibold", 10)).pack(side="left")
        val = tk.Label(top, text=fmt(cfg[key]), bg=C_CARD, fg=C_ACC, font=("Segoe UI Semibold", 10))
        val.pack(side="right")

        def cb(v):
            x = round(v, 2)
            cfg[key] = x
            val.config(text=fmt(x))
            save_later()

        sl = Slider(box, lo, hi, cfg[key], cb)
        sl.pack(fill="x")
        hint_lbl = tk.Label(box, text=hint, bg=C_CARD, fg=C_MUTED, font=("Segoe UI", 8), wraplength=S(320), justify="left")
        hint_lbl.pack(anchor="w")
        sliders[key] = (sl, val, fmt, hint_lbl)

    add_slider("Скорость", "speed", 0.2, 3.0, lambda v: f"×{v:.1f}", "")
    add_slider("Количество", "density", 0.2, 2.5, lambda v: f"×{v:.1f}", "")
    add_slider("Рост сугробов", "pile_rate", 0.0, 4.0, lambda v: "выкл" if v < 0.05 else f"×{v:.1f}", "")
    add_slider("Высота сугробов", "max_pile", 0, 30, lambda v: f"{int(v)} px", "До какой высоты могут вырасти сугробы или кучки.")
    add_slider("Размер снежинок", "flake_size", 0.5, 2.0, lambda v: f"×{v:.1f}", "Масштаб снежинок и осыпающихся комочков.")
    add_slider("Яркость снежинок", "brightness", 0.15, 1.0, lambda v: f"{int(v * 100)}%", "Прозрачность и яркость частиц: вправо — ярче.")
    add_slider("Пролёт за окнами", "behind_ratio", 0, 100, lambda v: f"{int(v)}%", "Какая часть снежинок проходит за окнами. 0% — все поверх окон, 100% — все за окнами.")
    add_slider("Плавность", "fps", 30, 240, lambda v: f"{int(v)} к/с", "Максимальная частота кадров. Рекомендуется 60-144.")
    
    update_hints()

    btns = tk.Frame(right, bg=C_BG)
    btns.pack(fill="x")

    def reset():
        cfg.update(DEFAULT)
        for k, (sl, val, fmt, hint_lbl) in sliders.items():
            sl.set(cfg[k])
            val.config(text=fmt(cfg[k]))
        pick_mode(cfg["mode"])
        save_cfg(cfg)

    Pill(btns, "Убрать сугробы", lambda: signal(EV_CLEAR), 172, 34, pbg=C_BG).pack(side="left")
    Pill(btns, "Сбросить настройки", reset, 172, 34, pbg=C_BG).pack(side="right")

    tk.Label(root, text="Ctrl+Alt+M — режим    Ctrl+Alt+C — убрать сугробы    Ctrl+Alt+Q — выключить    \n"
                        "Потряси мышкой — снег красиво осыпется с курсора",
             bg=C_BG, fg=C_MUTED, font=("Segoe UI", 8)).pack(pady=(S(6), S(14)))

    root.update_idletasks()
    try:
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        one = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(one), 4)
        cap = ctypes.c_int(0x0026160D)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
    except Exception:
        pass
    refresh_status()
    root.mainloop()


# =====================================================================
#                              ОВЕРЛЕЙ СО СНЕГОМ (Qt, со сглаживанием)
# =====================================================================
def run_overlay():
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"
    import time
    from PySide6.QtCore import Qt, QTimer, QPointF, QRect
    from PySide6.QtGui import (QPainter, QColor, QPainterPath, QPixmap, QImage, QLinearGradient,
                               QRadialGradient, QPen, QRegion)
    from PySide6.QtWidgets import QApplication, QWidget

    mtx = kernel32.CreateMutexW(None, False, MUTEX)
    if kernel32.GetLastError() == 183:
        return
    ev_quit = kernel32.CreateEventW(None, True, False, EV_QUIT)
    ev_clear = kernel32.CreateEventW(None, False, False, EV_CLEAR)

    app = QApplication(sys.argv[:1])
    geo = app.primaryScreen().virtualGeometry()
    VX, VY, W, H = geo.x(), geo.y(), geo.width(), geo.height()
    try:
        UI = max(1.0, user32.GetDpiForSystem() / 96.0)
    except Exception:
        UI = 1.0
    CW = max(2, int(round(3 * UI)))
    dwm = ctypes.windll.dwmapi
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    WNDENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def mk_frames(draw, px, n, span):
        frames = []
        for i in range(n):
            img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.translate(px / 2.0, px / 2.0)
            p.rotate(span * i / float(n))
            draw(p)
            p.end()
            frames.append(QPixmap.fromImage(img))
        return frames

    def d_dot(s, a):
        def f(p):
            r = s / 2.0 - 1
            g = QRadialGradient(0, 0, r)
            g.setColorAt(0.0, QColor(255, 255, 255, a))
            g.setColorAt(0.5, QColor(255, 255, 255, int(a * 0.8)))
            g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(0, 0), r, r)
        return f

    def d_crystal(s, detail):
        def f(p):
            r = s / 2.0 - 1.2
            w = max(1.0, s / 12.0)
            g = QRadialGradient(0, 0, r)
            g.setColorAt(0.0, QColor(255, 255, 255, 90))
            g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(0, 0), r, r)
            p.setPen(QPen(QColor(255, 255, 255, 250), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            for k in range(6):
                p.save()
                p.rotate(60 * k)
                p.drawLine(QPointF(0, 0), QPointF(0, -r))
                if detail >= 1:
                    y, b = -r * 0.52, r * 0.30
                    p.drawLine(QPointF(0, y), QPointF(-b, y - b))
                    p.drawLine(QPointF(0, y), QPointF(b, y - b))
                if detail >= 2:
                    y, b = -r * 0.78, r * 0.18
                    p.drawLine(QPointF(0, y), QPointF(-b, y - b))
                    p.drawLine(QPointF(0, y), QPointF(b, y - b))
                p.restore()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(0, 0), w * 0.9, w * 0.9)
        return f

    def petal_path(L, Wd):
        pp = QPainterPath()
        pp.moveTo(0, 0)
        pp.cubicTo(-Wd * .9, -L * .25, -Wd * .8, -L * .85, -Wd * .18, -L)
        pp.quadTo(0, -L * .86, Wd * .18, -L)
        pp.cubicTo(Wd * .8, -L * .85, Wd * .9, -L * .25, 0, 0)
        pp.closeSubpath()
        return pp

    def d_petal(L, col):
        path = petal_path(L, L * 0.52)
        def f(p):
            p.translate(0, L / 2.0)
            g = QLinearGradient(0, 0, 0, -L)
            g.setColorAt(0.0, QColor(255, 246, 249))
            g.setColorAt(0.55, col)
            g.setColorAt(1.0, col.darker(110))
            p.setBrush(g)
            p.setPen(QPen(QColor(235, 130, 170, 110), 0.7))
            p.drawPath(path)
        return f

    def d_blossom(L, col):
        path = petal_path(L, L * 0.72)
        def f(p):
            for k in range(5):
                p.save()
                p.rotate(72 * k)
                g = QLinearGradient(0, 0, 0, -L)
                g.setColorAt(0.0, QColor(255, 236, 244))
                g.setColorAt(0.6, col)
                g.setColorAt(1.0, col.darker(108))
                p.setBrush(g)
                p.setPen(QPen(QColor(235, 130, 170, 110), 0.6))
                p.drawPath(path)
                p.restore()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(240, 105, 150))
            p.drawEllipse(QPointF(0, 0), L * 0.16, L * 0.16)
            p.setBrush(QColor(255, 214, 102))
            p.drawEllipse(QPointF(0, 0), L * 0.08, L * 0.08)
        return f

    def d_leaf(L, col):
        Wd = L * 0.33
        path = QPainterPath()
        path.moveTo(0, 0)
        path.cubicTo(Wd, -L * .15, Wd * .9, -L * .75, 0, -L)
        path.cubicTo(-Wd * .9, -L * .75, -Wd, -L * .15, 0, 0)
        path.closeSubpath()
        def f(p):
            p.translate(0, L / 2.0)
            g = QLinearGradient(-Wd, 0, Wd, 0)
            g.setColorAt(0.0, col.lighter(118))
            g.setColorAt(1.0, col.darker(118))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawPath(path)
            p.setPen(QPen(col.darker(165), max(0.8, L / 26.0), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(0, L * 0.12), QPointF(0, -L * 0.9))
            for fr in (0.3, 0.5, 0.7):
                y = -L * fr
                p.drawLine(QPointF(0, y), QPointF(Wd * 0.55, y - L * 0.12))
                p.drawLine(QPointF(0, y), QPointF(-Wd * 0.55, y - L * 0.12))
        return f

    SPRITES = {}

    def sprites(mode):
        if mode in SPRITES:
            return SPRITES[mode]
        sets = []
        def add(draw, diam, n, span, weight, spd):
            px = int(math.ceil(diam * UI)) + 4
            px += px % 2
            sets.append(dict(fr=mk_frames(draw, px, n, span), half=px / 2.0, w=weight, spd=spd))

        if mode == "snow":
            add(d_dot(5 * UI, 210), 5, 1, 0, 34, 0.75)
            add(d_dot(8 * UI, 220), 8, 1, 0, 24, 0.9)
            add(d_crystal(13 * UI, 0), 13, 12, 60, 18, 1.0)
            add(d_crystal(18 * UI, 1), 18, 12, 60, 16, 1.1)
            add(d_crystal(25 * UI, 2), 25, 12, 60, 8, 1.25)
        elif mode == "sakura":
            for L, wt_ in ((12, 22), (16, 16)):
                for c in ((255, 196, 218), (255, 180, 208), (255, 214, 228)):
                    add(d_petal(L * UI, QColor(*c)), L, 24, 360, wt_ / 3.0, 0.9 + L / 80.0)
            add(d_blossom(8 * UI, QColor(255, 192, 214)), 16, 12, 72, 6, 1.0)
            add(d_blossom(11 * UI, QColor(255, 178, 207)), 22, 12, 72, 4, 1.1)
        elif mode == "leaves":
            for L, wt_ in ((15, 16), (21, 10)):
                for c in ((232, 132, 40), (196, 64, 40), (224, 172, 40), (160, 96, 34)):
                    add(d_leaf(L * UI, QColor(*c)), L, 24, 360, wt_ / 2.0, 0.9 + L / 80.0)
        SPRITES[mode] = sets
        return sets

    # ---------------------------------------------------------------
    #  Сугробы с физикой
    # ---------------------------------------------------------------
    class Surf:
        __slots__ = ("l", "t", "r", "b", "hs", "path", "dirty", "maxh", "rem")

        def __init__(self, n):
            self.l = self.t = self.r = self.b = 0
            self.hs = [0.0] * n
            self.path = None
            self.dirty = True
            self.maxh = 0.0
            self.rem = 0.0

        def resize(self, n):
            self.hs = (self.hs + [0.0] * n)[:n]
            self.dirty = True

        def clear(self):
            self.hs[:] = [0.0] * len(self.hs)
            self.dirty = True

        def rebuild(self):
            hs = self.hs
            L = len(hs)
            path = QPainterPath()
            path.moveTo(0, 0)
            mx = 0.0
            for i in range(L):
                v = (hs[i - 1 if i else 0] + 2 * hs[i] + hs[i + 1 if i < L - 1 else L - 1]) / 4.0
                if v > mx:
                    mx = v
                path.lineTo(i * CW + CW / 2.0, -v)
            path.lineTo(L * CW, 0)
            path.closeSubpath()
            self.path, self.maxh, self.dirty = path, mx, False

    def add_pile(s, c, cap, rate):
        hs = s.hs
        L = len(hs)
        if 0 <= c < L:
            hs[c] = min(cap, hs[c] + rate)
            thr, stp = UI, 0.25 * UI
            for _ in range(2):
                for i in range(max(0, c - 4), min(L, c + 5)):
                    if i < 0 or i >= L: continue
                    for n in (i - 1, i + 1):
                        nh = hs[n] if 0 <= n < L else 0.0
                        if hs[i] - nh > thr:
                            hs[i] -= stp
                            if 0 <= n < L:
                                hs[n] += stp
            s.dirty = True

    # ---------------------------------------------------------------
    #  Окно-оверлей
    # ---------------------------------------------------------------
    class Overlay(QWidget):
        def __init__(self):
            super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                             Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setGeometry(VX, VY, W, H)
            self.show()
            self.hwnd = int(self.winId())
            ex = user32.GetWindowLongW(self.hwnd, -20)
            user32.SetWindowLongW(self.hwnd, -20, ex | 0x80000 | 0x20 | 0x80 | 0x8000000)
            try:
                user32.SetWindowDisplayAffinity(self.hwnd, 0x11)
            except Exception:
                pass

            self.cfg = load_cfg()
            try:
                self.mtime = os.path.getmtime(CFG)
            except OSError:
                self.mtime = 0
            self.piles, self.surf = {}, []
            self.cur = Surf(max(1, int(12 * UI) // CW))
            self.rect = wt.RECT()
            self.res = []
            self.enum_cb = WNDENUM(self._enum)
            self.lcx, self.ldir, self.shake = 0, 1, 0.0
            self.held = set()
            self.flakes, self.built, self.sets = [], None, []
            self.last = time.perf_counter()
            self.t_scan = self.t_cfg = self.t_top = 0.0
            self.rain_pen = QPen(QColor(170, 205, 255, 150), max(1.0, 1.4 * UI), Qt.SolidLine, Qt.RoundCap)
            self.rebuild()
            self.scan()
            self.timer = QTimer(self)
            self.timer.setTimerType(Qt.PreciseTimer)
            self.timer.timeout.connect(self.tick)
            self.timer.start(self.interval())

        def interval(self):
            fps = max(30, min(240, int(self.cfg["fps"])))
            return max(1, int(1000.0 / fps))

        def reload_cfg(self):
            try:
                mt = os.path.getmtime(CFG)
            except OSError:
                return
            if mt != self.mtime:
                self.mtime = mt
                self.cfg = load_cfg()
                self.timer.setInterval(self.interval())
                if (self.cfg["mode"], round(self.cfg["density"], 1)) != self.built:
                    self.rebuild()

        def rebuild(self):
            c = self.cfg
            self.built = (c["mode"], round(c["density"], 1))
            m = MODES[c["mode"]]
            self.sets = sprites(c["mode"]) if not m["rain"] else []
            self.weights = [s["w"] for s in self.sets]
            self.flakes = []
            for _ in range(max(10, int(m["n"] * c["density"]))):
                f = [0.0] * 10  # f[8] — горизонтальная инерция, f[9] — комок осыпавшегося снега
                f[3] = random.random() * 6.28
                self.respawn(f, True)
                self.flakes.append(f)

        def respawn(self, f, initial=False):
            m = MODES[self.cfg["mode"]]
            f[0] = random.random() * W
            f[1] = random.random() * H if initial else random.random() * -80 * UI
            base = random.uniform(*m["vy"]) * UI
            if self.sets:
                si = random.choices(range(len(self.sets)), self.weights)[0]
                st = self.sets[si]
                f[2] = base * st["spd"]
                f[4] = si
                f[5] = random.random() * len(st["fr"])
                f[6] = random.uniform(-6, 6) if len(st["fr"]) > 1 else 0.0
                f[7] = st["half"] * 0.5
            else:
                f[2] = base
                f[7] = 0.0
            f[8] = 0.0 # Сброс горизонтальной инерции
            f[9] = 0.0

        def shed_flake(self, x, y, vx=0.0, vy=None, clump=False):
            """Создаёт падающую частицу или объёмный комок осыпавшегося снега."""
            if len(self.flakes) >= 900:
                return
            f = [0.0] * 10
            self.respawn(f)
            # Для снега с окна можно создать отдельный объёмный комок,
            # не меняя внешний вид обычных снежинок в снегопаде.
            if clump and self.cfg["mode"] == "snow":
                # Комок заметно крупнее снежинки, слегка вращается и кувыркается.
                f[9] = 1.0
                f[7] = random.uniform(8.0, 13.0) * UI
                # У каждого комка своя скорость вращения и небольшой разброс формы.
                f[3] = random.uniform(0.0, 6.28)
                f[6] = random.uniform(-5.5, 5.5)
            elif self.cfg["mode"] == "snow" and len(self.sets) >= 5:
                si = random.choice((2, 3, 4))
                st = self.sets[si]
                f[4] = si
                f[5] = random.randrange(len(st["fr"]))
                f[6] = random.uniform(-7.0, 7.0)
                f[7] = st["half"]
            f[0] = x
            f[1] = y
            f[2] = vy if vy is not None else random.uniform(110, 260) * UI
            f[8] = vx
            if clump and self.cfg["mode"] == "snow":
                # Комок начинает падать с умеренной скоростью, затем разгоняется.
                f[2] = random.uniform(65, 125) * UI if vy is None else vy
                f[8] += random.uniform(-45, 45) * UI
            self.flakes.append(f)

        def next_mode(self):
            c = self.cfg
            c["mode"] = ORDER[(ORDER.index(c["mode"]) + 1) % len(ORDER)]
            save_cfg(c)
            try:
                self.mtime = os.path.getmtime(CFG)
            except OSError:
                pass
            self.rebuild()

        def clear(self):
            for s in self.surf:
                s.clear()
            self.cur.clear()

        def quit(self):
            try:
                app.quit()
            finally:
                os._exit(0)

        def _enum(self, h, _):
            if h == self.hwnd or not user32.IsWindowVisible(h) or user32.IsIconic(h):
                return True
            cl = ctypes.c_int(0)
            dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(cl), 4)
            if cl.value:
                return True
            buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, buf, 64)
            tray = "TrayWnd" in buf.value
            if not tray and user32.GetWindowTextLengthW(h) == 0:
                return True
            r = self.rect
            if dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), 16) != 0:
                user32.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left < 120 or r.bottom - r.top < 40:
                return True
            t = r.top - VY
            if t < 25:
                return True
            self.res.append((h, r.left - VX, t, r.right - VX, r.bottom - VY))
            return True

        def scan(self):
            self.res = []
            user32.EnumWindows(self.enum_cb, 0)
            new, alive = [], {}
            for h, l, t, r, b in self.res:
                s = self.piles.get(h)
                n = max(1, (r - l) // CW)
                if s is None:
                    s = Surf(n)
                elif len(s.hs) != n:
                    s.resize(n)
                s.l, s.t, s.r, s.b = l, t, r, b
                alive[h] = s
                new.append(s)
            self.piles, self.surf = alive, new

        def track(self):
            """Физика окон: инерция сдвига и осыпание вниз с горизонтальным разлетом."""
            r = self.rect
            for h, s in self.piles.items():
                if dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), 16) == 0:
                    nl, nt, nr, nb = r.left - VX, r.top - VY, r.right - VX, r.bottom - VY
                    
                    if (s.l != 0 or s.t != 0) and s.maxh > 0.5:
                        dx = nl - s.l
                        dy = nt - s.t

                        # Если окно резко сдвинули/встряхнули, снег с его верхнего
                        # края осыпаются отдельными объёмными комками снега.
                        movement = math.hypot(dx, dy)
                        # Срабатывает и от небольшого, но резкого движения окна.
                        if self.cfg["mode"] == "snow" and movement > 8 * UI and s.maxh > 1.0:
                            columns = [i for i, hh in enumerate(s.hs) if hh > 1.5]
                            random.shuffle(columns)
                            budget = min(65, max(5, int(movement / (6 * UI) * 5)))
                            drift = (1 if dx > 0 else -1) * min(7.0, abs(dx) / max(UI, 1.0) * 0.035)
                            for i in columns[:budget]:
                                hh = s.hs[i]
                                self.shed_flake(
                                    s.l + i * CW + random.uniform(0, CW),
                                    s.t - hh,
                                    drift + random.uniform(-3.5, 3.5) * UI,
                                    random.uniform(150, 260) * UI,
                                    clump=True
                                )
                                # Частично освобождаем место — снег не исчезает весь сразу.
                                s.hs[i] *= random.uniform(0.28, 0.52)
                            s.dirty = True

                        # Горизонтальная инерция и сваливание снега с краев
                        if abs(dx) > 0:
                            s.rem -= (dx / CW) * 0.85
                            shift = int(s.rem)
                            if shift != 0:
                                s.rem -= shift
                                if shift > 0:
                                    fallen = s.hs[-shift:]
                                    s.hs = ([0.0] * shift + s.hs)[:len(s.hs)]
                                    edge_x = s.r
                                else:
                                    fallen = s.hs[:-shift]
                                    s.hs = (s.hs[-shift:] + [0.0] * (-shift))[:len(s.hs)]
                                    edge_x = s.l
                                s.dirty = True
                                
                                # Падение снега с краев окна при горизонтальном сдвиге
                                for hh in fallen:
                                    if hh > 1.0 and random.random() > 0.3:
                                        self.shed_flake(
                                            edge_x + random.uniform(-CW, CW), s.t - hh,
                                            (dx / UI) * 0.1,
                                            random.uniform(140, 280) * UI,
                                            clump=True
                                        )
                                
                        # Вертикальная инерция (снег слетает при резком движении окна вниз)
                        if dy > 6 * UI:
                            for i, hh in enumerate(s.hs):
                                if hh > dy * 0.2 and random.random() > 0.4:
                                    self.shed_flake(
                                        s.l + i * CW, s.t - hh,
                                        random.uniform(-3, 3) * UI,
                                        random.uniform(220, 420) * UI,
                                        clump=True
                                    )
                            s.hs = [max(0.0, h_val - dy * 0.2) for h_val in s.hs]
                            s.dirty = True
                            
                    s.l, s.t, s.r, s.b = nl, nt, nr, nb
                    n = max(1, (s.r - s.l) // CW)
                    if n != len(s.hs):
                        s.resize(n)

        def tick(self):
            now = time.perf_counter()
            dt = min(0.1, max(0.001, now - self.last))
            self.last = now
            if now - self.t_scan > 0.35:
                self.t_scan = now
                self.scan()
            else:
                self.track()
            if now - self.t_cfg > 0.5:
                self.t_cfg = now
                self.reload_cfg()
            if now - self.t_top > 2.0:
                self.t_top = now
                user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x13)
            if kernel32.WaitForSingleObject(ev_quit, 0) == 0:
                self.quit()
            if kernel32.WaitForSingleObject(ev_clear, 0) == 0:
                self.clear()
            self.keys()

            c = self.cfg
            m = MODES[c["mode"]]
            speed = c["speed"]
            rate = c["pile_rate"] * 1.2 * UI
            cap = float(c["max_pile"]) * UI
            acc = (not m["rain"]) and rate > 0.05 * UI and cap > 0.5 * UI
            wob, wind = m["wob"], m["wind"]
            rain = m["rain"]

            if not acc and not rain:
                d = 1.5 * UI * dt
                for s in [self.cur] + self.surf:
                    if s.maxh > 0.01:
                        s.hs = [h - d if h > d else 0.0 for h in s.hs]
                        s.dirty = True

            pt = wt.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            cx, cy = pt.x - VX, pt.y - VY
            v = (cx - self.lcx) / dt
            self.lcx = cx
            
            if abs(v) > 190 * UI:
                if v * self.ldir < 0:
                    self.shake += 1
                self.ldir = 1 if v > 0 else -1
            self.shake *= 0.97 ** (dt * 30)
            
            # Физика стряхивания с курсора (осыпание + горизонтальная инерция мышки)
            cur = self.cur
            if self.shake > 2.2:
                if cur.maxh > 0.5:
                    v_dir = 1 if self.ldir > 0 else -1
                    for i, h_val in enumerate(cur.hs):
                        if h_val > 0.5 and random.random() > 0.2:
                            self.shed_flake(
                                cur.l + i * CW, cur.t - h_val,
                                v_dir * random.uniform(5, 20) * UI,
                                random.uniform(300, 700) * UI,
                                clump=(self.cfg["mode"] == "snow")
                            )
                cur.clear()
                self.shake = 0
                
            cur.l, cur.t, cur.r, cur.b = cx, cy + 1, cx + int(12 * UI), cy + int(14 * UI)

            sf = [(cur.l, cur.t, cur.r, cur.b, cur.hs, min(7.0 * UI, cap), cur)] + \
                 [(s.l, s.t, s.r, s.b, s.hs, cap, s) for s in self.surf]
            nsf = len(sf)
            sets = self.sets
            sin = math.sin
            k = dt * speed
            
            active_flakes = []
            max_flakes = max(10, int(m["n"] * c["density"]))
            
            for f in self.flakes:
                py = f[1]
                if f[9] > 0.5 and c["mode"] == "snow":
                    # Физика осыпавшегося сугроба: гравитация, инерция,
                    # сопротивление воздуха и настоящее кувыркание в полёте.
                    f[2] = min(f[2] + 620.0 * UI * k, 980.0 * UI)
                    f[1] = py + f[2] * k
                    f[0] += f[8] * k
                    f[8] *= 0.985 ** (dt * 30)
                    f[3] += f[6] * k
                else:
                    f[1] = py + f[2] * k
                    f[3] += k * 1.6
                    # f[8] — горизонтальная инерция обычных частиц.
                    f[0] += (sin(f[3]) * wob + wind + f[8]) * 30.0 * UI * k
                    f[8] *= 0.92 ** (dt * 30)
                
                if sets:
                    nfr = len(sets[f[4]]["fr"])
                    if nfr > 1:
                        f[5] = (f[5] + f[6] * k) % nfr
                        
                x = f[0]
                if acc:
                    rr = f[7] * (c.get("flake_size", 1.0) if f[9] < 0.5 else 1.0)
                    yb, pb = f[1] + rr, py + rr
                    hit = False
                    for i in range(nsf):
                        l, t, r_, b_, hs, cp, s = sf[i]
                        if l <= x < r_:
                            ci = int((x - l) // CW)
                            if 0 <= ci < len(hs):
                                top = t - hs[ci]
                                if pb <= top < yb:
                                    hidden = False
                                    for j in range(i):
                                        o = sf[j]
                                        if o[0] <= x < o[2] and o[1] <= top < o[3]:
                                            hidden = True
                                            break
                                    if not hidden:
                                        add_pile(s, ci, cp, rate)
                                        hit = True
                                        break
                    if hit:
                        if len(active_flakes) < max_flakes:
                            self.respawn(f)
                        else:
                            continue

                if f[1] > H + 30 or f[0] > W + 30 or f[0] < -30:
                    if len(active_flakes) < max_flakes:
                        self.respawn(f)
                    else:
                        continue

                active_flakes.append(f)
                
            self.flakes = active_flakes
            self.update()

        def keys(self):
            down = lambda vk: user32.GetAsyncKeyState(vk) & 0x8000
            if down(0x11) and down(0x12):
                for vk, act in ((0x51, self.quit), (0x4D, self.next_mode), (0x43, self.clear)):
                    if down(vk):
                        if vk not in self.held:
                            self.held.add(vk)
                            act()
                    else:
                        self.held.discard(vk)
            else:
                self.held.clear()

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            c = self.cfg
            m = MODES[c["mode"]]

            if not m["rain"]:
                cap = max(1.0, float(c["max_pile"]) * UI)
                g = QLinearGradient(0, -cap, 0, 0)
                g.setColorAt(0.0, QColor(*m["pile_top"]))
                g.setColorAt(1.0, QColor(*m["pile_bot"]))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                lst = [self.cur] + self.surf
                for i, s in enumerate(lst):
                    if s.dirty:
                        s.rebuild()
                    if s.maxh < 0.6:
                        continue
                    p.save()
                    bound = QRect(s.l, int(s.t - s.maxh) - 2, max(1, s.r - s.l), int(s.maxh) + 3)
                    hit = None
                    for j in range(1, i):
                        o = lst[j]
                        if o.l < bound.right() and o.r > bound.left() and o.t < bound.bottom() and o.b > bound.top():
                            if hit is None:
                                hit = QRegion(bound)
                            hit = hit.subtracted(QRegion(QRect(o.l, o.t, o.r - o.l, o.b - o.t)))
                    if hit is not None:
                        p.setClipRegion(hit)
                    p.translate(s.l, s.t)
                    p.drawPath(s.path)
                    p.restore()

            if m["rain"]:
                p.save()
                p.setOpacity(max(0.15, min(1.0, float(c.get("brightness", 1.0)))))
                p.setPen(self.rain_pen)
                kx = m["wind"] * 30.0 * UI * 0.022
                for f in self.flakes:
                    p.drawLine(QPointF(f[0], f[1]), QPointF(f[0] - kx, f[1] - f[2] * 0.022))
                p.restore()
            else:
                sets = self.sets
                size_mul = max(0.5, min(2.0, float(c.get("flake_size", 1.0))))
                opacity = max(0.15, min(1.0, float(c.get("brightness", 1.0))))
                behind_ratio = max(0, min(100, int(c.get("behind_ratio", 35))))
                # Частицы, назначенные «за окнами», рисуются только в свободных
                # областях экрана: прямоугольники окон вырезаются из области рисования.
                behind_region = QRegion(QRect(0, 0, W, H))
                if behind_ratio:
                    for surf in self.surf:
                        if surf.r > surf.l and surf.b > surf.t:
                            behind_region = behind_region.subtracted(
                                QRegion(QRect(surf.l, surf.t, surf.r - surf.l, surf.b - surf.t)))
                total = max(1, len(self.flakes))
                for idx, f in enumerate(self.flakes):
                    behind = behind_ratio > 0 and (idx * 100 // total) < behind_ratio
                    p.save()
                    if behind:
                        p.setClipRegion(behind_region)
                    p.setOpacity(opacity)
                    if f[9] > 0.5:
                        # Падающий рыхлый ком снега: компактный, округлый и неровный,
                        # с несколькими слипшимися снежными бугорками (не вытянутая полоска).
                        r = f[7]
                        x, y = f[0], f[1]
                        p.translate(x, y)
                        p.scale(size_mul, size_mul)
                        p.rotate(math.degrees(f[3]))
                        p.setPen(Qt.NoPen)

                        # Мягкая голубоватая тень снизу придаёт комку объём.
                        p.setBrush(QColor(130, 157, 193, 95))
                        p.drawEllipse(QPointF(0, r * 0.16), r * 0.82, r * 0.60)

                        grad = QLinearGradient(0, -r * 0.85, 0, r * 0.72)
                        grad.setColorAt(0.0, QColor(255, 255, 255, 255))
                        grad.setColorAt(0.48, QColor(246, 250, 255, 250))
                        grad.setColorAt(1.0, QColor(205, 220, 242, 245))
                        p.setBrush(grad)
                        mound = QPainterPath()
                        mound.moveTo(-r * 0.82, r * 0.28)
                        mound.cubicTo(-r * 1.02, -r * 0.08, -r * 0.76, -r * 0.58, -r * 0.34, -r * 0.57)
                        mound.cubicTo(-r * 0.20, -r * 0.98, r * 0.30, -r * 0.91, r * 0.43, -r * 0.52)
                        mound.cubicTo(r * 0.88, -r * 0.56, r * 1.00, -r * 0.08, r * 0.79, r * 0.30)
                        mound.cubicTo(r * 0.42, r * 0.70, -r * 0.43, r * 0.70, -r * 0.82, r * 0.28)
                        p.drawPath(mound)

                        # Небольшие слипшиеся округлые выступы делают силуэт похожим на ком снега.
                        p.setBrush(QColor(255, 255, 255, 220))
                        p.drawEllipse(QPointF(-r * 0.43, -r * 0.36), r * 0.24, r * 0.19)
                        p.drawEllipse(QPointF(r * 0.28, -r * 0.40), r * 0.22, r * 0.17)
                        p.setBrush(QColor(255, 255, 255, 115))
                        p.drawEllipse(QPointF(-r * 0.18, r * 0.08), r * 0.12, r * 0.07)
                    else:
                        st = sets[f[4]]
                        fr = st["fr"]
                        h = st["half"] * size_mul
                        p.translate(f[0], f[1])
                        p.scale(size_mul, size_mul)
                        p.drawPixmap(QPointF(-st["half"], -st["half"]), fr[int(f[5]) % len(fr)])
                    p.restore()
            p.end()

    ov = Overlay()
    app.exec()
    del ov, mtx


# =====================================================================
#                      ЗАШИТАЯ ИКОНКА (winter.ico, base64)
# =====================================================================
ICO_B64 = (
    "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"
)

if __name__ == "__main__":
    if "--overlay" in sys.argv:
        run_overlay()
    else:
        run_settings()
