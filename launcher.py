"""SAO-style live desktop.

SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)

- Sets a still SAO-style picture as your normal Windows wallpaper.
- Middle-click an empty spot on the desktop -> the menu slides down.
- The menu lists every app in your Start menu, sorted into categories.

Usage (script):  pythonw launcher.py [--startup] | --stop | --intro | --list | --set key=value
Usage (installed): "SAO Desktop Menu.exe" with the same options.
"""
import ctypes
import ctypes.wintypes as wt
import fnmatch
import http.server
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import winreg

# Script: everything lives next to launcher.py (as before).
# Installed .exe: read-only files come from the install folder (RES); settings, icons, logs and the
# Edge profile go to %LOCALAPPDATA%\SAO Desktop Menu (DATA), where an installed app may write.
FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES = getattr(sys, "_MEIPASS", HERE)
DATA = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "SAO Desktop Menu") if FROZEN else HERE
os.makedirs(DATA, exist_ok=True)
PORT = 8770
PAGE = os.path.join(RES, "sao-desktop.html")
CONFIG = os.path.join(DATA, "apps.json")
STATE = os.path.join(DATA, ".running.json")
PROFILE = os.path.join(DATA, ".edge-profile")
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
NO_WINDOW = 0x08000000
LOG = os.path.join(DATA, "launcher.log")


def log(*parts):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")
    except OSError:
        pass

# ---------------------------------------------------------------- app scan

EXCLUDE = re.compile(
    r"uninstall|readme|\bhelp\b(?!.*get)|documentation|manual|module docs|website|on the web|"
    r"release notes|faq|support center|check for updates|getting started|sample|^visit |docs\b|"
    r"license manager|^setup$|reset settings|migrate from|import .* settings|export .* settings|"
    r"telemetry|diagnostics|redistributable|about java|troubleshooter|language preferences|"
    r"recording manager|background downloader|install additional tools",
    re.I)
EXCLUDE_EXT = (".url", ".pdf", ".txt", ".html", ".htm", ".chm", ".msi")

# (category, icon, regex) - first match wins
RULES = [
    ("Games", "game", r"league of legends|valorant|dota|apex legends|pubg|cardfight|solitaire|minecraft|"
                      r"fortnite|genshin|roblox|counter-strike|\bcs2\b|overwatch|elden|gta"),
    ("Gaming", "play", r"^steam$|epic games|riot client|garena|^xbox$|game bar|omen gaming|geforce|"
                       r"razer cortex|razer axon|wallpaper engine|battle\.net|ubisoft|ea app"),
    ("Trading", "chart", r"binance|metatrader|tradingview"),
    ("Engineering", "cube", r"solidworks|autocad|autodesk|edrawings|matlab|arcgis|qgis|grass gis|saga gis|osgeo|"
                            r"google earth|labplot|openrocket|drama|simutext|arduino|visualize|treehouse|composer|"
                            r"pdm|toolbox|property tab|costing|team render|commandline 20|reference manager|"
                            r"batch standards|attach digital|my products|^administration$|view setup|cinema 4d"),
    ("Creative", "image", r"adobe|clipchamp|^paint$|photos|camera|snipping|sound recorder"),
    ("Media", "music", r"spotify|music|itunes|media player|movies"),
    ("Office", "file", r"^word$|^excel$|^powerpoint$|^access$|^publisher$|onenote|outlook \(classic\)|microsoft to do|"
                       r"sticky notes|calendar|people|^files$|endnote|spreadsheet compare|power automate|"
                       r"skype for business"),
    ("Dev Tools", "code", r"visual studio|\bgit\b|python|idle|ipython|jupyter|anaconda|node\.js|developer|"
                          r"native tools|cross tools|terminal|command prompt|powershell|nsight|gpuview|"
                          r"windows performance|application verifier|app cert kit|software development kit|"
                          r"cloud sdk|cloud tools|visual profiler|qt designer|configure java|odbc|metaeditor"),
    ("Web & Chat", "globe", r"chrome|\bedge\b|firefox|opera|brave|discord|teams|skype|^outlook$|^mail$|"
                            r"phone link|vpn|anydesk|remote desktop|quick assist|onedrive|lockdown browser|"
                            r"safer web|claude|copilot|ollama|whatsapp|telegram|line\b|zoom"),
    ("System", "gear", r"settings|control panel|task manager|file explorer|windows tools|services|registry|"
                       r"event viewer|defender|security|firewall|backup|nvidia control|synapse|hp system|"
                       r"omen audio|thunderbolt|^run$|disk cleanup|defragment|recovery|system |"
                       r"computer management|performance monitor|resource monitor|task scheduler|"
                       r"component services|iscsi|memory diagnostic|endpoint protection"),
    ("Utilities", "grid", r"calculator|clock|weather|news|maps|notepad|character map|magnifier|narrator|"
                          r"keyboard|live captions|voice access|click to do|get help|feedback|family|"
                          r"mixed reality|store|scan|fax|steps recorder|get started"),
]
RULES = [(c, i, re.compile(r, re.I)) for c, i, r in RULES]
ICON_OF = {c: i for c, i, _ in RULES}
ICON_OF.update({"Files": "folder", "Other": "app"})

# Top-level buttons, and the subcategories inside some of them.
TOP_ORDER = ["Files", "Games", "Web & Chat", "Work", "Creative", "Media", "Trading", "Utilities", "Other"]
TOP_ICON = {"Files": "folder", "Games": "game", "Web & Chat": "globe", "Work": "file", "Creative": "image",
            "Media": "music", "Trading": "chart", "Utilities": "grid", "Other": "app"}
GROUP_ORDER = {"Games": ["Games", "Launchers"], "Web & Chat": ["Web", "Chat"],
               "Work": ["Office", "Dev Tools", "Engineering"], "Other": ["System", "Other"]}
SUBCAT_OF = {"Games": ("Games", "Games"), "Gaming": ("Games", "Launchers"),
             "Office": ("Work", "Office"), "Dev Tools": ("Work", "Dev Tools"),
             "Engineering": ("Work", "Engineering"),
             "System": ("Other", "System"), "Other": ("Other", "Other")}
CHAT_RX = re.compile(r"discord|teams|skype|^mail$|outlook|phone link|whatsapp|telegram|\bline\b|zoom|messenger", re.I)


def place(cat, name):
    """Old-style category name -> (top category, subcategory or None)."""
    if "/" in cat:                                   # "Work/Office" style
        top, sub = cat.split("/", 1)
        return top.strip(), sub.strip() or None
    if cat == "Web & Chat":
        return "Web & Chat", ("Chat" if CHAT_RX.search(name) else "Web")
    if cat in SUBCAT_OF:
        return SUBCAT_OF[cat]
    if cat in GROUP_ORDER:                           # a top name that has subcategories
        return cat, GROUP_ORDER[cat][-1]
    return cat, None


def save_user_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    _cache["t"] = 0


def default_user_config():
    return {
        "_help": "hide: app names to leave out (* wildcards ok). hide_categories: whole top categories to "
                 "leave out. move: put an app somewhere else, e.g. \"Work/Office\". extra: your own entries "
                 "(target = exe path, folder, or https:// link). Easiest: use 'Edit menu' inside Other.",
        "sound": True,
        "intro": False,
        "set_wallpaper": True,
        "hide": [],
        "hide_categories": [],
        "move": {"Wallpaper Engine": "Creative"},
        "extra": [
            {"category": "Web & Chat", "group": "Web", "name": "YouTube", "target": "https://www.youtube.com", "icon": "play"},
        ],
    }


VOICE_EXT = (".mp3", ".m4a", ".wav", ".ogg")


def intro_voice_file():
    """Voice for the LINK START intro, in this order:
    1. "intro_voice" in apps.json - your own clip (set it to false to always use Windows' built-in voice)
    2. sounds/link-start.mp3 (or .m4a/.wav/.ogg) that ships with the app
    3. nothing -> Windows' built-in voice says "Link start"."""
    p = load_user_config().get("intro_voice")
    if p is False:
        return None
    if p:
        p = p if os.path.isabs(p) else os.path.join(DATA, p)
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in VOICE_EXT:
            return p
    for ext in VOICE_EXT:
        q = os.path.join(RES, "sounds", "link-start" + ext)
        if os.path.isfile(q):
            return q
    return None


def load_user_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        if "categories" in cfg:          # old format from the first version -> replace
            raise ValueError
        return cfg
    except Exception:
        cfg = default_user_config()
        save_user_config(cfg)
        return cfg


def start_apps():
    cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
           "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                         capture_output=True, creationflags=NO_WINDOW, timeout=60).stdout
    data = json.loads(out.decode("utf-8-sig") or "[]")
    return data if isinstance(data, list) else [data]


def categorize(name, appid):
    if appid.lower().startswith("steam://rungameid") and "wallpaper engine" not in name.lower():
        return "Games"
    for cat, _icon, rx in RULES:
        if rx.search(name):
            return cat
    return "Other"


_cache = {"t": 0, "cats": None}
_cache_lock = threading.Lock()


def build_menu(force=False):
    """Returns [{name, icon, groups:[...], items:[{name, icon, target, group, extra}]}]."""
    with _cache_lock:
        if not force and _cache["cats"] and time.time() - _cache["t"] < 120:
            return _cache["cats"]
        cfg = load_user_config()
        hide = [h.lower() for h in cfg.get("hide", [])]
        move = {k.lower(): v for k, v in cfg.get("move", {}).items()}
        tops = {c: [] for c in TOP_ORDER}

        keep_only = {k.lower(): [n.lower() for n in v] for k, v in cfg.get("keep_only", {}).items()}

        def add(top, sub, item):
            if any(fnmatch.fnmatch(item["name"].lower(), h) for h in hide):
                return
            only = keep_only.get(f"{top}/{sub}".lower() if sub else top.lower())
            if only is not None and not item.get("extra") and                     not any(fnmatch.fnmatch(item["name"].lower(), n) for n in only):
                return                                   # this (sub)category shows only the listed apps
            item["group"] = sub
            tops.setdefault(top, []).append(item)

        home = os.path.expanduser("~")
        for it in [
            {"name": "This PC", "target": "shell:MyComputerFolder", "icon": "folder"},
            {"name": "Desktop", "target": os.path.join(home, "Desktop"), "icon": "folder"},
            {"name": "Downloads", "target": os.path.join(home, "Downloads"), "icon": "folder"},
            {"name": "Documents", "target": os.path.join(home, "Documents"), "icon": "folder"},
            {"name": "Pictures", "target": os.path.join(home, "Pictures"), "icon": "image"},
            {"name": "Recycle Bin", "target": "shell:RecycleBinFolder", "icon": "folder"},
        ] + [{"name": f"Drive {d}:", "target": f"{d}:\\", "icon": "folder"}
             for d in "DEFGH" if os.path.exists(f"{d}:\\")]:
            add("Files", None, it)

        seen = set()
        try:
            apps = start_apps()
        except Exception:
            apps = []
        for a in sorted(apps, key=lambda x: (x.get("Name") or "").lower()):
            name, appid = (a.get("Name") or "").strip(), (a.get("AppID") or "").strip()
            low = name.lower()
            if not name or not appid or low in seen:
                continue
            if EXCLUDE.search(name) or appid.lower().endswith(EXCLUDE_EXT) or appid.lower().startswith("http"):
                continue
            seen.add(low)
            old = categorize(name, appid)
            top, sub = place(move[low], name) if low in move else place(old, name)
            add(top, sub, {"name": name, "target": "shell:AppsFolder\\" + appid, "icon": ICON_OF.get(old, "app")})

        for e in cfg.get("extra", []):
            top, sub = (e.get("category", "Other"), e.get("group")) if e.get("group") else place(e.get("category", "Other"), e["name"])
            add(top, sub, {"name": e["name"], "target": e["target"], "icon": e.get("icon", "app"), "extra": True})

        hidden_cats = {h.lower() for h in cfg.get("hide_categories", [])}
        result = []
        for c, items in tops.items():
            if not items or c.lower() in hidden_cats:
                continue
            order = list(GROUP_ORDER.get(c, []))
            for it in items:                          # any custom subcategory goes at the end
                if it["group"] and it["group"] not in order:
                    order.append(it["group"])
            rank = {g: i for i, g in enumerate(order)}
            items.sort(key=lambda it: (rank.get(it["group"], 99), it["name"].lower()))
            groups = [g for g in order if any(it["group"] == g for it in items)]
            result.append({"name": c, "icon": TOP_ICON.get(c, "app"), "groups": groups, "items": items})
        _cache.update(t=time.time(), cats=result)
        return result


def menu_places():
    """Every place an app can be put, for the editor's dropdown: ["Files", "Games/Games", ...]."""
    out = []
    for c in TOP_ORDER:
        if c in GROUP_ORDER:
            out += [f"{c}/{g}" for g in GROUP_ORDER[c]]
        else:
            out.append(c)
    return out


ICON_DIR = os.path.join(DATA, ".icons")
_icon_lock = threading.Lock()
_icon_failed = set()


def icon_key(target):
    import hashlib
    return hashlib.md5(target.encode("utf-8")).hexdigest()[:16]


def icon_path(key):
    return os.path.join(ICON_DIR, key + ".png")


def extract_missing_icons(cats):
    """Save each app's real icon (via icons.ps1) into the .icons folder - runs in the background."""
    if not _icon_lock.acquire(blocking=False):
        return
    try:
        os.makedirs(ICON_DIR, exist_ok=True)
        todo = []
        for c in cats:
            for it in c["items"]:
                t = it["target"]
                if t.lower().startswith(("http:", "https:")):
                    continue
                k = icon_key(t)
                if k not in _icon_failed and not os.path.exists(icon_path(k)):
                    todo.append({"path": t, "out": icon_path(k)})
        if not todo:
            return
        lst = os.path.join(ICON_DIR, "_todo.json")
        with open(lst, "w", encoding="utf-8") as f:
            json.dump(todo, f, ensure_ascii=False)
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            os.path.join(RES, "icons.ps1"), "-List", lst],
                           capture_output=True, text=True, creationflags=NO_WINDOW, timeout=600)
        log("icons:", (r.stdout or r.stderr).strip()[-200:])
        for t in todo:
            if not os.path.exists(t["out"]):
                _icon_failed.add(os.path.basename(t["out"])[:-4])
        _cache["t"] = 0                      # next /apps call includes the new icons
    except Exception as e:  # noqa: BLE001
        log("icon extraction failed:", e)
    finally:
        _icon_lock.release()


def browse_for_file():
    """Normal Windows 'Open' dialog, shown above the menu."""
    LIVE.dialog_open = True
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            parent=root, title="Choose an app, shortcut or file",
            initialdir=os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                    r"Microsoft\Windows\Start Menu\Programs"),
            filetypes=[("Apps and shortcuts", "*.exe *.lnk *.url *.bat *.cmd"), ("All files", "*.*")])
        root.destroy()
        return os.path.normpath(path) if path else ""
    finally:
        LIVE.dialog_open = False
        if LIVE.hwnd and LIVE.mode == "menu":
            force_foreground(LIVE.hwnd)


def edit_config(req):
    """Changes made from the 'Edit menu' page."""
    action = req.get("action")
    cfg = load_user_config()
    name = str(req.get("name", "")).strip()
    extras = cfg.setdefault("extra", [])
    hide = cfg.setdefault("hide", [])
    if action == "browse":
        path = browse_for_file()
        stem = os.path.splitext(os.path.basename(path))[0] if path else ""
        return {"ok": True, "path": path, "name": stem}
    if action == "add":
        target = str(req.get("target", "")).strip().strip('"')
        place_ = str(req.get("place", "Other/Other"))
        if not name or not target:
            return {"ok": False, "error": "Name and path are both needed"}
        if not (target.lower().startswith(("http://", "https://", "shell:")) or os.path.exists(target)):
            return {"ok": False, "error": "That file or folder doesn't exist"}
        top, _, sub = place_.partition("/")
        extras[:] = [e for e in extras if e["name"].lower() != name.lower()]
        entry = {"category": top, "name": name, "target": target}
        if sub:
            entry["group"] = sub
        extras.append(entry)
        hide[:] = [h for h in hide if h.lower() != name.lower()]
    elif action == "remove":
        before = len(extras)
        extras[:] = [e for e in extras if e["name"].lower() != name.lower()]
        if len(extras) == before and name.lower() not in [h.lower() for h in hide]:
            hide.append(name)
    elif action == "restore":
        hide[:] = [h for h in hide if h.lower() != name.lower()]
    else:
        return {"ok": False, "error": "unknown action"}
    save_user_config(cfg)
    log("edit:", action, name)
    return {"ok": True}


def launch(target):
    try:
        os.startfile(target)
    except OSError:
        subprocess.Popen(["explorer.exe", target], creationflags=NO_WINDOW)


# ---------------------------------------------------------------- Win32

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.FindWindowW.restype = wt.HWND
user32.FindWindowExW.restype = wt.HWND
user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.SetParent.restype = wt.HWND
user32.SetParent.argtypes = [wt.HWND, wt.HWND]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.WindowFromPoint.restype = wt.HWND
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.GetAncestor.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.MapWindowPoints.argtypes = [wt.HWND, wt.HWND, ctypes.POINTER(wt.POINT), wt.UINT]
user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, wt.BYTE, wt.DWORD]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CHILD, WS_POPUP, WS_VISIBLE = 0x40000000, 0x80000000, 0x10000000
WS_FRAME_BITS = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000
WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80000, 0x80, 0x40000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW, SWP_FRAMECHANGED = 1, 2, 0x10, 0x40, 0x20
HWND_TOPMOST, HWND_NOTOPMOST = wt.HWND(-1), wt.HWND(-2)
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_CLOSE, WM_MOUSEMOVE = 0x0207, 0x0208, 0x0010, 0x0200
DRAG_PX = 40          # how far (screen pixels) to drag down with the middle button held


def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


SW_HIDE, SW_SHOW = 0, 5
SPI_GETDESKWALLPAPER, SPI_SETDESKWALLPAPER = 0x73, 0x14
SPIF_UPDATE_AND_SEND = 0x01 | 0x02
BACKUP = os.path.join(DATA, ".wallpaper-backup.json")
DESK_KEY = r"Control Panel\Desktop"


def wallpaper_file():
    """The still wallpaper to use: apps.json "wallpaper", else the night one sized for this screen."""
    cfg = load_user_config()
    p = cfg.get("wallpaper")
    if p:
        p = p if os.path.isabs(p) else os.path.join(RES, p)
        if os.path.exists(p):
            return p
    w, _ = screen_size()
    name = "sao-wallpaper-night-2560x1440.png" if w > 1920 else "sao-wallpaper-night-1920x1080.png"
    return os.path.join(RES, "wallpapers", name)


def get_wallpaper():
    buf = ctypes.create_unicode_buffer(520)
    user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 520, buf, 0)
    style = tile = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESK_KEY) as k:
            style = winreg.QueryValueEx(k, "WallpaperStyle")[0]
            tile = winreg.QueryValueEx(k, "TileWallpaper")[0]
    except OSError:
        pass
    return {"path": buf.value, "style": style, "tile": tile}


def set_wallpaper(path, style="10", tile="0"):
    """Normal Windows wallpaper change (style 10 = Fill)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESK_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if style is not None:
                winreg.SetValueEx(k, "WallpaperStyle", 0, winreg.REG_SZ, str(style))
            if tile is not None:
                winreg.SetValueEx(k, "TileWallpaper", 0, winreg.REG_SZ, str(tile))
    except OSError:
        pass
    user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(path), SPIF_UPDATE_AND_SEND)


def apply_sao_wallpaper():
    target = wallpaper_file()
    if not os.path.exists(BACKUP):                    # remember the user's wallpaper only once
        cur = get_wallpaper()
        if os.path.normcase(cur["path"]) != os.path.normcase(target):
            with open(BACKUP, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False)
    set_wallpaper(target)
    log("wallpaper set to", target)


def restore_wallpaper():
    try:
        with open(BACKUP, encoding="utf-8") as f:
            old = json.load(f)
        set_wallpaper(old["path"], old.get("style"), old.get("tile"))
        os.remove(BACKUP)
        log("wallpaper restored to", old["path"])
    except (OSError, ValueError, KeyError):
        pass


def grab_desktop():
    """Snapshot of the screen right before the menu opens (kept in memory only),
    used as the menu's background so it looks like the menu floats on your desktop."""
    try:
        import io
        from PIL import ImageGrab
        w, h = screen_size()
        img = ImageGrab.grab(bbox=(0, 0, w, h)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "PNG", compress_level=1)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        log("snapshot failed:", e)
        return None


def force_foreground(hwnd):
    fg = user32.GetForegroundWindow()
    cur = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if fg_thread and fg_thread != cur:
        user32.AttachThreadInput(cur, fg_thread, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    if fg_thread and fg_thread != cur:
        user32.AttachThreadInput(cur, fg_thread, False)


def edge_path():
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                p = winreg.QueryValue(k, None)
                if os.path.exists(p):
                    return p
        except OSError:
            pass
    return r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def find_page_window(timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        found = []

        @WNDENUMPROC
        def cb(hwnd, _):
            if class_name(hwnd) == "Chrome_WidgetWin_1" and window_title(hwnd).startswith("Link Desktop"):
                found.append(hwnd)
            return True
        user32.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.25)
    return None


# ---------------------------------------------------------------- controller

class Live:
    """Still wallpaper on the desktop; a hidden menu window that pops up on middle-click."""

    def __init__(self):
        self.mode = "hidden"
        self.hwnd = None
        self.edge = None
        self.subs = set()
        self.lock = threading.Lock()
        self.token = secrets.token_hex(16)
        self.swallow_up = False
        self.gesture = None
        self.quitting = False
        self.shown = False
        self.dialog_open = False
        self.snapshot = None
        self.snap_id = ""

    def broadcast(self, msg):
        for q in list(self.subs):
            q.put(msg)

    def start_page(self):
        w, h = screen_size()
        self.edge = subprocess.Popen([
            edge_path(), f"--app=http://127.0.0.1:{PORT}/?menu=1", f"--user-data-dir={PROFILE}",
            "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--hide-crash-restore-bubble", "--disable-session-crashed-bubble",
            "--disable-features=msEdgeSidebarV2",
            "--autoplay-policy=no-user-gesture-required",
            "--start-fullscreen", f"--window-size={w},{h}",
        ], creationflags=NO_WINDOW)
        log("edge started pid", self.edge.pid)
        self.hwnd = find_page_window()
        if not self.hwnd:
            raise RuntimeError("Could not find the menu window")
        user32.ShowWindow(self.hwnd, SW_HIDE)
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_STYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_STYLE, (style & ~WS_FRAME_BITS) | WS_POPUP)
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW)
        self.mode = "hidden"
        log("menu window ready", hex(self.hwnd))

    def open_menu(self, x, y):
        with self.lock:
            if self.mode == "menu" or not self.hwnd:
                return
            self.mode = "menu"
            self.snapshot = grab_desktop()
            self.snap_id = secrets.token_hex(8)
            wa = wt.RECT()
            user32.SystemParametersInfoW(0x30, 0, ctypes.byref(wa), 0)      # work area = screen minus taskbar
            self.broadcast({"type": "open", "x": x, "y": y, "bottom": wa.bottom or screen_size()[1],
                            "snap": self.snap_id if self.snapshot else None})
        # the page loads the snapshot, then calls /show; show anyway if it is slow
        threading.Timer(1.2, self.show_window).start()

    def play_intro(self):
        """The LINK START animation, shown full screen once (at login, or with --intro)."""
        for _ in range(50):                      # wait until the page is connected
            if self.subs:
                break
            time.sleep(0.1)
        with self.lock:
            if self.mode != "hidden" or not self.hwnd:
                return
            self.mode = "intro"
            self.snapshot = grab_desktop()       # the intro ends by fading into this
            self.snap_id = secrets.token_hex(8)
            self.broadcast({"type": "intro", "snap": self.snap_id if self.snapshot else None})
        log("intro playing")
        threading.Timer(1.5, self.show_window).start()
        threading.Timer(12, self.hide_menu).start()      # safety net: never stays on screen

    def show_window(self):
        with self.lock:
            if self.mode not in ("menu", "intro") or self.shown:
                return
            self.shown = True
            w, h = screen_size()
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, w, h, SWP_SHOWWINDOW | SWP_FRAMECHANGED)
            force_foreground(self.hwnd)

    def hide_menu(self):
        with self.lock:
            if self.mode not in ("menu", "intro"):
                return
            self.mode = "hidden"
            self.shown = False
            user32.ShowWindow(self.hwnd, SW_HIDE)

    # --- mouse hook: middle-click on an empty spot of the desktop
    @staticmethod
    def is_desktop(pt):
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return False
        return class_name(user32.GetAncestor(hwnd, 2)) in ("Progman", "WorkerW")

    def hook_thread(self):
        def proc(code, wparam, lparam):
            if code == 0:
                if wparam == WM_MBUTTONDOWN and self.mode == "hidden":
                    # hold the middle button on the desktop... (menu opens once you drag down)
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if self.is_desktop(info.pt):
                        self.gesture = (info.pt.x, info.pt.y)
                        self.swallow_up = True
                        return 1
                elif wparam == WM_MOUSEMOVE and self.gesture:
                    # ...and drag down a bit to open the menu where you started
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    gx, gy = self.gesture
                    dy, dx = info.pt.y - gy, abs(info.pt.x - gx)
                    if dy >= DRAG_PX and dx < dy:
                        self.gesture = None
                        threading.Thread(target=self.open_menu, args=(gx, gy), daemon=True).start()
                elif wparam in (0x0201, 0x0204, WM_MBUTTONDOWN) and self.mode == "menu" and not self.dialog_open:
                    # a click anywhere outside the menu closes it
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if user32.GetAncestor(user32.WindowFromPoint(info.pt), 2) != self.hwnd:
                        self.broadcast({"type": "close"})
                elif wparam == WM_MBUTTONUP and self.swallow_up:
                    self.swallow_up = False
                    self.gesture = None          # released without dragging down: do nothing
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._proc = HOOKPROC(proc)          # keep a reference so it isn't garbage-collected
        user32.SetWindowsHookExW(14, self._proc, kernel32.GetModuleHandleW(None), 0)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # --- if the menu window gets closed (e.g. Alt+F4), bring it back
    def watch_thread(self):
        while not self.quitting:
            time.sleep(2)
            if self.quitting:
                return
            if not self.hwnd or not user32.IsWindow(self.hwnd):
                log("menu window gone -> restarting it")
                try:
                    if self.edge and self.edge.poll() is None:
                        self.edge.terminate()
                    self.start_page()
                except Exception as e:  # noqa: BLE001
                    log("restart failed:", e)

    def quit(self):
        self.quitting = True
        try:
            if self.hwnd and user32.IsWindow(self.hwnd):
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            time.sleep(0.5)
            if self.edge and self.edge.poll() is None:
                self.edge.terminate()
        finally:
            restore_wallpaper()
            try:
                os.remove(STATE)
            except OSError:
                pass
            log("stopped")
            os._exit(0)


LIVE = Live()

# ---------------------------------------------------------------- web server


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(PAGE, "rb") as f:
                self.send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/apps":
            cats = build_menu()
            out = [{"name": c["name"], "icon": c["icon"], "groups": c.get("groups", []),
                    "items": [dict({"name": i["name"], "icon": i["icon"], "group": i.get("group")},
                                   **({"ico": icon_key(i["target"])} if os.path.exists(icon_path(icon_key(i["target"]))) else {}))
                              for i in c["items"]]} for c in cats]
            threading.Thread(target=extract_missing_icons, args=(cats,), daemon=True).start()
            self.send(200, json.dumps(out, ensure_ascii=False))
        elif path == "/config":
            cfg = load_user_config()
            self.send(200, json.dumps({"places": menu_places(), "hidden": cfg.get("hide", []),
                                       "extra": [{"name": e["name"], "target": e["target"],
                                                  "place": e.get("category", "Other") + ("/" + e["group"] if e.get("group") else "")}
                                                 for e in cfg.get("extra", [])]}, ensure_ascii=False))
        elif path == "/settings":
            cfg = load_user_config()
            self.send(200, json.dumps({"sound": bool(cfg.get("sound", True)), "intro": bool(cfg.get("intro", False)),
                                       "intro_voice": bool(intro_voice_file())}))
        elif path == "/intro-voice":
            f = intro_voice_file()
            if f:
                ctype = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}.get(
                    os.path.splitext(f)[1].lower(), "application/octet-stream")
                with open(f, "rb") as fh:
                    self.send(200, fh.read(), ctype)
            else:
                self.send(404, '{"error":"no intro voice"}')
        elif path == "/wallpaper.png":
            with open(wallpaper_file(), "rb") as f:
                self.send(200, f.read(), "image/png")
        elif path == "/backdrop":
            q = self.path.split("?n=")[-1] if "?n=" in self.path else ""
            if LIVE.snapshot and q and q == LIVE.snap_id:
                self.send(200, LIVE.snapshot, "image/png")
            else:
                self.send(404, '{"error":"not found"}')
        elif path.startswith("/icon/") and re.fullmatch(r"[0-9a-f]{16}", path[6:]) and os.path.exists(icon_path(path[6:])):
            with open(icon_path(path[6:]), "rb") as f:
                self.send(200, f.read(), "image/png")
        elif path == "/events":
            self.events()
        else:
            self.send(404, '{"error":"not found"}')

    def events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = queue.Queue()
        LIVE.subs.add(q)
        try:
            while True:
                try:
                    msg = "data: " + json.dumps(q.get(timeout=15)) + "\n\n"
                except queue.Empty:
                    msg = ": ping\n\n"
                self.wfile.write(msg.encode())
                self.wfile.flush()
        except Exception:
            pass
        finally:
            LIVE.subs.discard(q)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_POST(self):
        if self.path == "/open":
            if self.headers.get("X-Token") == LIVE.token:
                req = self.body()
                threading.Thread(target=LIVE.open_menu, args=(int(req.get("x", 300)), int(req.get("y", 200))), daemon=True).start()
                self.send(200, '{"ok":true}')
            else:
                self.send(403, '{"error":"forbidden"}')
            return
        if self.path == "/intro":
            if self.headers.get("X-Token") == LIVE.token:
                threading.Thread(target=LIVE.play_intro, daemon=True).start()
                self.send(200, '{"ok":true}')
            else:
                self.send(403, '{"error":"forbidden"}')
            return
        if self.path == "/quit":
            if self.headers.get("X-Token") == LIVE.token:
                self.send(200, '{"ok":true}')
                threading.Thread(target=LIVE.quit, daemon=True).start()
            else:
                self.send(403, '{"error":"forbidden"}')
            return
        if self.headers.get("Origin") not in ORIGINS or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.send(403, '{"error":"forbidden"}')
        try:
            req = self.body()
            if self.path == "/launch":
                cats = build_menu()
                entry = next((i for c in cats if c["name"] == req.get("catName")
                              for i in c["items"] if i["name"] == req.get("name")), None)
                if entry is None:
                    entry = cats[int(req["cat"])]["items"][int(req["item"])]
                launch(entry["target"])
                self.send(200, json.dumps({"ok": True, "name": entry["name"]}, ensure_ascii=False))
            elif self.path == "/config":
                self.send(200, json.dumps(edit_config(req), ensure_ascii=False))
            elif self.path == "/show":
                threading.Thread(target=LIVE.show_window, daemon=True).start()
                self.send(200, '{"ok":true}')
            elif self.path == "/mode":
                if req.get("mode") == "wall":
                    threading.Thread(target=LIVE.hide_menu, daemon=True).start()
                self.send(200, '{"ok":true}')
            else:
                self.send(404, '{"error":"not found"}')
        except Exception as e:  # noqa: BLE001
            self.send(500, json.dumps({"ok": False, "error": str(e)}))


# ---------------------------------------------------------------- entry points

def port_in_use():
    # Windows retries a refused local connection for ~2s by default, so try to bind instead (instant)
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", PORT))
            return False
        except OSError:
            return True


def stop():
    try:
        with open(STATE, encoding="utf-8") as f:
            token = json.load(f)["token"]
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/quit", data=b"{}", method="POST",
                                     headers={"X-Token": token})
        urllib.request.urlopen(req, timeout=5).read()
        for _ in range(50):                      # wait until it has really exited
            if not port_in_use():
                break
            time.sleep(0.2)
        print("Stopped.")
    except Exception as e:  # noqa: BLE001
        print("Not running (or could not stop):", e)
        restore_wallpaper()                      # still put the old wallpaper back


def play_intro_now():
    try:
        with open(STATE, encoding="utf-8") as f:
            token = json.load(f)["token"]
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/intro", data=b"{}", method="POST",
                                                      headers={"X-Token": token}), timeout=5).read()
        print("Playing the intro.")
    except Exception as e:  # noqa: BLE001
        print("The menu isn't running - start it first:", e)


def set_option(arg):
    """--set intro=true  /  --set sound=false"""
    key, _, val = arg.partition("=")
    if key not in ("intro", "sound", "set_wallpaper"):
        return print("Only intro, sound and set_wallpaper can be set this way.")
    cfg = load_user_config()
    cfg[key] = val.strip().lower() in ("1", "true", "yes", "y", "on")
    save_user_config(cfg)
    print(f"{key} = {cfg[key]}")


def main():
    if "--stop" in sys.argv:
        return stop()
    if "--intro" in sys.argv:
        return play_intro_now()
    if "--set" in sys.argv:
        i = sys.argv.index("--set")
        return set_option(sys.argv[i + 1] if i + 1 < len(sys.argv) else "")
    if "--list" in sys.argv:
        for c in build_menu(force=True):
            print(f"\n[{c['name']}] ({len(c['items'])})")
            for i in c["items"]:
                print("   ", i["name"])
        return
    if "--startup" in sys.argv:                  # launched at login: wait only until the desktop + taskbar exist
        t0 = time.time()
        while not (user32.FindWindowW("Progman", None) and user32.FindWindowW("Shell_TrayWnd", None)) \
                and time.time() - t0 < 120:
            time.sleep(0.5)
        time.sleep(1)
        log("login: desktop ready after %.1fs" % (time.time() - t0))
    if port_in_use():
        log("already running - nothing to do")
        return
    log("starting")
    dpi_aware()
    load_user_config()
    threading.Thread(target=lambda: extract_missing_icons(build_menu()), daemon=True).start()   # warm list + icons
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "token": LIVE.token}, f)
    if load_user_config().get("set_wallpaper", True):
        apply_sao_wallpaper()
    for attempt in range(3):                     # right after login Edge can be slow to appear
        try:
            LIVE.start_page()
            break
        except RuntimeError as e:
            log("start attempt", attempt + 1, "failed:", e)
            if LIVE.edge and LIVE.edge.poll() is None:
                LIVE.edge.terminate()
            if attempt == 2:
                raise
            time.sleep(10)
    threading.Thread(target=LIVE.watch_thread, daemon=True).start()
    if "--startup" in sys.argv and load_user_config().get("intro"):
        threading.Thread(target=LIVE.play_intro, daemon=True).start()
    LIVE.hook_thread()                           # runs forever (message loop)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LIVE.quit()
    except Exception:
        import traceback
        log("CRASH\n" + traceback.format_exc())
        LIVE.quit()
