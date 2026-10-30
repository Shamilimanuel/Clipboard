"""Talking to Windows: reading and writing the clipboard, the global hotkey, and pasting.

Everything here uses ctypes (Python's built-in way to call Windows functions).
"""
import ctypes
import io
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_BITMAP, CF_DIB, CF_UNICODETEXT, CF_HDROP, CF_DIBV5 = 2, 8, 13, 15, 17
GMEM_MOVEABLE = 0x0002
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

# Tell ctypes the exact types, otherwise 64-bit handles get cut in half.
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
kernel32.GlobalSize.restype = ctypes.c_size_t
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT

MAX_PIXELS = 40_000_000   # bigger pictures are not kept (a 8K screenshot is 33 million)

EXCLUDE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing",)  # set by password managers
HISTORY_FORMAT = "CanIncludeInClipboardHistory"                       # DWORD 0 = do not record


def _open_clipboard(tries=15):
    """Another program may hold the clipboard for a moment, so retry a few times."""
    for _ in range(tries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def sequence_number():
    """A number that changes every time anything is copied."""
    return user32.GetClipboardSequenceNumber()


def _owner_exe():
    """Name of the program that put something on the clipboard, e.g. 'chrome.exe'."""
    hwnd = user32.GetClipboardOwner()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def read_snapshot():
    """What is on the clipboard right now. Returns None if it could not be opened."""
    owner = _owner_exe()
    if not _open_clipboard():
        return None
    try:
        excluded = any(user32.IsClipboardFormatAvailable(user32.RegisterClipboardFormatW(name))
                       for name in EXCLUDE_FORMATS)
        history_format = user32.RegisterClipboardFormatW(HISTORY_FORMAT)
        if user32.IsClipboardFormatAvailable(history_format):
            handle = user32.GetClipboardData(history_format)
            pointer = kernel32.GlobalLock(handle) if handle else None
            if pointer:
                if ctypes.c_uint32.from_address(pointer).value == 0:
                    excluded = True
                kernel32.GlobalUnlock(handle)

        text = None
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            pointer = kernel32.GlobalLock(handle) if handle else None
            if pointer:
                text = ctypes.wstring_at(pointer)
                kernel32.GlobalUnlock(handle)

        # Pictures and copied files are read here too, while the clipboard is open, and never with Pillow's
        # ImageGrab.grabclipboard(): when a program offers a picture it then cannot hand over, that one asks
        # again forever, keeping the clipboard locked and the window frozen (it happened on 20 Oct 2026).
        image = files = None
        if text is None and not excluded:
            image = _read_dib()
            if image is None:
                files = _read_files()
        return {"text": text, "image": image, "files": files, "excluded": excluded, "owner": owner}
    finally:
        user32.CloseClipboard()


def _read_dib():
    """The picture on the (open) clipboard as DIB bytes (a bitmap without its file header), or None.
    None too when a program says it has a picture but cannot give it, or when it is too big to keep."""
    for fmt in (CF_DIB, CF_DIBV5):   # Windows makes a DIB out of a plain CF_BITMAP by itself
        if not user32.IsClipboardFormatAvailable(fmt):
            continue
        handle = user32.GetClipboardData(fmt)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            continue
        try:
            size = kernel32.GlobalSize(handle)
            if size < 40:
                continue
            width = ctypes.c_int32.from_address(pointer + 4).value
            height = abs(ctypes.c_int32.from_address(pointer + 8).value)
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                return None
            return ctypes.string_at(pointer, size)
        finally:
            kernel32.GlobalUnlock(handle)
    return None


def _read_files():
    """Paths of copied files on the (open) clipboard, or None."""
    if not user32.IsClipboardFormatAvailable(CF_HDROP):
        return None
    handle = user32.GetClipboardData(CF_HDROP)
    if not handle:
        return None
    count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
    paths = []
    for index in range(count):
        length = shell32.DragQueryFileW(handle, index, None, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        shell32.DragQueryFileW(handle, index, buffer, length + 1)
        paths.append(buffer.value)
    return paths or None


def set_text(text):
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, size)
    kernel32.GlobalUnlock(handle)
    if not _open_clipboard():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, handle)  # Windows now owns the memory
        return True
    finally:
        user32.CloseClipboard()


def set_image(path):
    """Puts a PNG file on the clipboard as a bitmap (CF_DIB)."""
    from PIL import Image
    with Image.open(path) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
    dib = output.getvalue()[14:]  # a DIB is a BMP file without its 14-byte file header
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, dib, len(dib))
    kernel32.GlobalUnlock(handle)
    if not _open_clipboard():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_DIB, handle)
        return True
    finally:
        user32.CloseClipboard()


# ---------- window focus, pasting, hotkey ----------

def foreground_window():
    return user32.GetForegroundWindow()


def focus_window(hwnd):
    if hwnd:
        user32.SetForegroundWindow(hwnd)


user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND


def toplevel_hwnd(tk_window_id):
    """Tkinter's winfo_id() is an inner window; its parent is the real top-level window."""
    return user32.GetParent(tk_window_id)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL


def caret_position():
    """Screen position (x, y of the bottom of the blinking text cursor) in the window you are typing
    in, or None. Many modern apps (browsers, Electron) do not report a caret; then this returns None."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(hwnd, None), ctypes.byref(info)):
        return None
    if not info.hwndCaret:
        return None
    point = wintypes.POINT(info.rcCaret.left, info.rcCaret.bottom)
    if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
        return None
    return point.x, point.y


dwmapi = ctypes.WinDLL("dwmapi")


class MARGINS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]


def soften_window(hwnd):
    """Windows 11: rounded corners and a soft shadow for a borderless window. Quietly does nothing elsewhere."""
    try:
        corners = ctypes.c_int(2)  # DWMWCP_ROUND
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corners), 4)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))
    except Exception:
        pass


def send_ctrl_v():
    """Presses Ctrl+V in whichever window has focus."""
    control, alt, v, key_up = 0x11, 0x12, 0x56, 0x0002
    user32.keybd_event(alt, 0, key_up, 0)  # in case Alt from our hotkey is still held
    user32.keybd_event(control, 0, 0, 0)
    user32.keybd_event(v, 0, 0, 0)
    user32.keybd_event(v, 0, key_up, 0)
    user32.keybd_event(control, 0, key_up, 0)


user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
WM_QUIT = 0x0012


class Hotkey:
    """One global hotkey that can be changed while the app runs."""

    def __init__(self, on_press):
        self.on_press = on_press
        self.thread = None
        self.thread_id = None

    def start(self, modifiers, key):
        """Registers the hotkey. Returns None on success, or a message saying why not."""
        import threading
        self.stop()
        ready = threading.Event()
        outcome = {}

        def run():
            outcome["thread_id"] = kernel32.GetCurrentThreadId()
            message = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # creates this thread's message queue
            outcome["ok"] = bool(user32.RegisterHotKey(None, 1, modifiers | MOD_NOREPEAT, key))
            ready.set()
            if not outcome["ok"]:
                return
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    self.on_press()
            user32.UnregisterHotKey(None, 1)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(2)
        if not outcome.get("ok"):
            self.thread = None
            return "Another program already uses that shortcut."
        self.thread_id = outcome["thread_id"]
        return None

    def stop(self):
        if self.thread and self.thread.is_alive() and self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            self.thread.join(1)
        self.thread = None
        self.thread_id = None
