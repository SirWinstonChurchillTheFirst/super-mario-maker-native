"""wincap_loop.py <exe name> <out dir> <interval s> <count> : pictures of the visible window of a running program
(found by its executable's name), taken from the window itself, so it works while the window is behind others.
Saves win_0000.png, win_0001.png, ... Used when the runtime's own picture capture gives nothing."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

from PIL import Image

exe, out, interval, count = sys.argv[1].lower(), sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
user32.SetProcessDPIAware()
os.makedirs(out, exist_ok=True)


def process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ''
    buf = ctypes.create_unicode_buffer(600)
    size = wintypes.DWORD(600)
    ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    kernel32.CloseHandle(h)
    return os.path.basename(buf.value).lower() if ok else ''


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def each(window, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if user32.IsWindowVisible(window) and process_name(pid.value) == exe:
            rect = wintypes.RECT()
            user32.GetClientRect(window, ctypes.byref(rect))
            if rect.right >= 320 and rect.bottom >= 180:
                found.append(window)
        return True

    user32.EnumWindows(each, 0)
    return found[0] if found else None


class Header(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("width", ctypes.c_long), ("height", ctypes.c_long), ("planes", wintypes.WORD),
                ("bits", wintypes.WORD), ("compression", wintypes.DWORD), ("image", wintypes.DWORD), ("x", ctypes.c_long),
                ("y", ctypes.c_long), ("used", wintypes.DWORD), ("important", wintypes.DWORD)]


def grab(window, path):
    rect = wintypes.RECT()
    user32.GetClientRect(window, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        return False
    screen = user32.GetDC(window)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, w, h)
    gdi32.SelectObject(memory, bitmap)
    user32.PrintWindow(window, memory, 3)  # client area only, rendered content included
    data = ctypes.create_string_buffer(w * h * 4)
    header = Header(ctypes.sizeof(Header), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    gdi32.GetDIBits(memory, bitmap, 0, h, data, ctypes.byref(header), 0)
    Image.frombuffer("RGBA", (w, h), data, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(window, screen)
    return True


taken = 0
start = time.time()
while taken < count and time.time() - start < interval * count + 30:
    window = find_window()
    if window is None:
        if taken:
            break  # the program ended
        time.sleep(0.5)
        continue
    if grab(window, os.path.join(out, 'win_%04d.png' % taken)):
        taken += 1
    time.sleep(interval)
print('wincap_loop:', taken, 'pictures')
