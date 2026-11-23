"""The Job Hunter window: the React page in ui/dist, shown by pywebview in Microsoft Edge WebView2.

Run from source:   python -I webapp.py        (build the page once first:  cd ui && npm ci && npm run build)
Installed:         JobHunter.exe              (jobhunter.py starts this)

WebView2 is part of Windows 11 and of every up-to-date Windows 10. The installer adds it when it is missing,
and this file says so in a plain message box instead of failing silently.
"""
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backend  # noqa: E402
import bot  # noqa: E402

WEBVIEW2_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/#download-section"
WEBVIEW2_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"  # the Evergreen WebView2 runtime


def page():
    """index.html of the built React page: inside the installed app, or ui/dist next to the scripts."""
    base = sys._MEIPASS if bot.FROZEN else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "ui", "dist", "index.html")


def message(text, title="Job Hunter", yes_no=False):
    """A native Windows message box (works before any window exists). Returns True for Yes/OK."""
    try:
        import ctypes
        flags = (0x4 if yes_no else 0x0) | 0x40  # Yes/No or OK, information icon
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags) in (1, 6)
    except (AttributeError, OSError):
        print(text, file=sys.stderr)
        return False


def webview2_installed():
    try:
        import winreg
    except ImportError:
        return True  # not Windows: pywebview picks its own engine
    for root, path in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}"),
                       (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}"),
                       (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}")):
        try:
            with winreg.OpenKey(root, path) as k:
                version = winreg.QueryValueEx(k, "pv")[0]
            if version and version != "0.0.0.0":
                return True
        except OSError:
            continue
    return False


def icon_file():
    """The app icon: next to JobHunter.exe when installed, in installer/ when run from source."""
    base = sys._MEIPASS if bot.FROZEN else os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer")
    return os.path.join(base, "icon.ico")


def windows_light_theme():
    """True when Windows apps use the light theme (so the window does not flash dark while it loads)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except (ImportError, OSError):
        return False


def own_taskbar_identity():
    """Group the window under Job Hunter on the taskbar, not under python.exe or a console."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CodeProjectsOfficial.JobHunter")
    except (AttributeError, OSError):
        pass


def set_window_icon(window):
    """Put the Job Hunter icon on the title bar and the taskbar button (from source it would be Python's)."""
    try:
        import ctypes
        path = icon_file()
        if not os.path.exists(path):
            return
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        hwnd = ctypes.c_void_p(window.native.Handle.ToInt64())
        for which, size in ((0, 16), (1, 256)):  # ICON_SMALL (title bar), ICON_BIG (taskbar, Alt+Tab)
            icon = user32.LoadImageW(None, path, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if icon:
                user32.SendMessageW(hwnd, 0x80, ctypes.c_void_p(which), ctypes.c_void_p(icon))  # WM_SETICON
    except Exception:  # never stop the window over its icon
        pass


def main():
    index = page()
    if not os.path.exists(index):
        message("The Job Hunter window files are missing.\n\nFrom source, build them once:\n"
                "    cd ui\n    npm ci\n    npm run build\n\nThe installed app always includes them: "
                f"reinstall it from {backend.DOWNLOAD_PAGE}")
        return
    if not webview2_installed():
        if message("Job Hunter needs Microsoft Edge WebView2, a free part of Windows that is missing on this PC."
                   "\n\nOpen Microsoft's download page now? Install the \"Evergreen Bootstrapper\", then start Job "
                   "Hunter again.", yes_no=True):
            webbrowser.open(WEBVIEW2_DOWNLOAD)
        return
    try:
        import webview
    except ImportError:
        message("Job Hunter needs the pywebview package to show its window.\n\nInstall it once:\n"
                "    python -m pip install -r requirements.txt")
        return

    own_taskbar_identity()
    api = backend.Api()
    theme = api.prefs()["theme"]
    light = theme == "light" or (theme == "auto" and windows_light_theme())
    window = webview.create_window(
        f"Job Hunter {bot.VERSION}", index, js_api=api, width=1400, height=880, min_size=(1040, 660), maximized=True,
        background_color="#f3f3f5" if light else "#1b1b1e", text_select=True)
    window.events.shown += lambda: set_window_icon(window)
    api._attach(window)
    # The local page is served from 127.0.0.1, so the clipboard and other modern browser features work.
    webview.start(gui="edgechromium", http_server=True, debug=os.environ.get("JOBHUNTER_DEBUG") == "1",
                  private_mode=True)


if __name__ == "__main__":
    main()
