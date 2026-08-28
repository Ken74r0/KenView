import ctypes
import platform

# Constants for SetWindowDisplayAffinity
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011

def set_exclude_from_capture(hwnd, exclude=True):
    """
    Sets the window to be excluded from screen capture (Windows 10+ only).
    """
    if platform.system() != "Windows":
        return False
    
    try:
        # Get the User32 DLL
        user32 = ctypes.windll.user32
        
        # Determine the affinity value
        # WDA_EXCLUDEFROMCAPTURE is the most aggressive (available in Win10 2004+)
        # It makes the window appear as black or invisible in captures.
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        
        # BOOL SetWindowDisplayAffinity(HWND hWnd, DWORD dwAffinity);
        result = user32.SetWindowDisplayAffinity(hwnd, affinity)
        return bool(result)
    except Exception:
        return False
