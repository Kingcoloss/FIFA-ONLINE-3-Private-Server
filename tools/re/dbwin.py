"""Passive OutputDebugString listener (the DBWIN_BUFFER protocol DebugView uses; no debugger attached).
Usage: python dbwin.py <log>"""
import ctypes, ctypes.wintypes as w, sys, time

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateEventW.restype = w.HANDLE
k.CreateFileMappingW.restype = w.HANDLE
k.CreateFileMappingW.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR]
k.MapViewOfFile.restype = ctypes.c_void_p
k.MapViewOfFile.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t]
log = sys.argv[1]

ready = k.CreateEventW(None, False, False, "DBWIN_BUFFER_READY")
if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS: the two listeners would split the lines
    sys.exit("another debug-output listener (DebugView?) is running")
data = k.CreateEventW(None, False, False, "DBWIN_DATA_READY")
mapping = k.CreateFileMappingW(w.HANDLE(-1), None, 4, 0, 4096, "DBWIN_BUFFER")  # PAGE_READWRITE
view = k.MapViewOfFile(mapping, 4, 0, 0, 4096)  # FILE_MAP_READ
if not (ready and data and mapping and view):
    sys.exit(f"setup failed: {ctypes.get_last_error()}")
with open(log, "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%H:%M:%S')} listening\n")
while True:
    k.SetEvent(ready)
    if k.WaitForSingleObject(data, 1000) != 0:
        continue
    pid = ctypes.c_uint32.from_address(view).value
    text = ctypes.string_at(view + 4).decode("latin1", "replace").rstrip()
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} [{pid}] {text}\n")
