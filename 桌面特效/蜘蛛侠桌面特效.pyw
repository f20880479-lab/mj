# -*- coding: utf-8 -*-
"""
蜘蛛侠桌面特效（窗口版）
- 主控制窗口（深色面板）：特效开关按钮；关闭窗口即退出程序（无论开关状态）
- 全局监听键盘：输入 mj 后按回车 → 屏幕正上方播放透明蜘蛛侠（带声音）
- 双特效随机：内置两个蜘蛛侠动画（原版倒挂 / 荡蛛丝版），每次触发随机抽取一个播放
- 持续生效：应用常驻，无论触发多少次都重播；播放中再触发会先清掉旧画面声音再从头播
- 透明实现：Win32 UpdateLayeredWindow（逐像素 alpha），参考 desk-pet 项目方案
"""
import os, sys, time, queue, random, ctypes
from ctypes import wintypes
import tkinter as tk
import winsound
import numpy as np
from PIL import Image

# ===== DPI awareness 必须在创建任何 Tk 窗口之前设置 =====
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    from pynput import keyboard
except ImportError:
    ctypes.windll.user32.MessageBoxW(0, '缺少 pynput，请先双击运行「安装依赖.bat」', '蜘蛛侠特效', 0x40)
    sys.exit(1)

# 单实例保护
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'SpidermanMjEffect')
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

if getattr(sys, 'frozen', False):
    HERE = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))   # 素材所在（临时解压）
    LOG = os.path.join(os.path.dirname(sys.executable), 'effect.log')  # 日志放 exe 旁（持久）
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    LOG = os.path.join(HERE, 'effect.log')

ICON = os.path.join(HERE, 'icon.ico')
TRIGGER = 'mj'
QUIT_WORD = 'stopmj'

# ===== 特效库：每次输入 mj 从里面随机抽取一个播放 =====
EFFECTS = [
    # 原版：倒挂 Q 版蜘蛛侠（8月21日.mp4 抠图，60fps，166 帧）
    dict(name='原版蜘蛛侠', dir=os.path.join(HERE, 'frames'),
         first=12, count=166, fps=60, cell=(434, 720),
         wav=os.path.join(HERE, 'audio.wav')),
    # 新版：荡蛛丝 Q 版蜘蛛侠（8月24日.mp4 抠图，30fps，80 帧，抖音水印已去除；
    # 帧已统一缩放到 720x720，与原版人物同高，两个特效视觉大小一致）
    dict(name='荡蛛丝蜘蛛侠', dir=os.path.join(HERE, 'frames2'),
         first=4, count=80, fps=30, cell=(720, 720),
         wav=os.path.join(HERE, 'audio2.wav')),
]

# 主窗口配色（深色蜘蛛侠主题）
BG = '#14171f'
PANEL = '#1d2330'
FG = '#f2f4f8'
MUTED = '#8b93a5'
ACCENT = '#fe2c55'      # 蜘蛛侠红
GREEN = '#2bd97c'
GRAY = '#3a4150'

# ---------------- Win32 ----------------
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG), ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER)]


class POINT(ctypes.Structure):
    _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [('cx', wintypes.LONG), ('cy', wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', wintypes.BYTE), ('BlendFlags', wintypes.BYTE),
                ('SourceConstantAlpha', wintypes.BYTE), ('AlphaFormat', wintypes.BYTE)]


def make_premultiplied_bgra(img):
    arr = np.asarray(img, dtype=np.uint16)
    a = arr[..., 3:4]
    premul = (arr[..., 0:3] * a) >> 8
    out = np.empty(arr.shape[:2] + (4,), dtype=np.uint8)
    out[..., 0] = premul[..., 2]
    out[..., 1] = premul[..., 1]
    out[..., 2] = premul[..., 0]
    out[..., 3] = arr[..., 3]
    return out


class LayeredWindow:
    """UpdateLayeredWindow 逐像素 alpha 透明窗口（点击穿透 + 置顶）"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST)
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        self._screen_dc = user32.GetDC(0)
        self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        self._bitmap = None
        self._old_bitmap = None
        self._cap_w = 0
        self._cap_h = 0
        self._bits = None

    def update(self, img, x, y):
        w, h = img.size
        if self._bitmap is None or w > self._cap_w or h > self._cap_h:
            if self._old_bitmap:
                gdi32.SelectObject(self._mem_dc, self._old_bitmap)
            if self._bitmap:
                gdi32.DeleteObject(self._bitmap)
            self._cap_w = max(w, self._cap_w)
            self._cap_h = max(h, self._cap_h)
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = self._cap_w
            bmi.bmiHeader.biHeight = -self._cap_h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            bmi.bmiHeader.biSizeImage = self._cap_w * self._cap_h * 4
            bits = ctypes.c_void_p()
            self._bitmap = gdi32.CreateDIBSection(self._mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            if not self._bitmap:
                raise OSError('CreateDIBSection failed')
            self._old_bitmap = gdi32.SelectObject(self._mem_dc, self._bitmap)
            self._bits = bits
        data = make_premultiplied_bgra(img)
        ctypes.memset(self._bits, 0, self._cap_w * self._cap_h * 4)
        row_bytes = w * 4
        src = data.tobytes()
        stride = self._cap_w * 4
        for row in range(h):
            dst = ctypes.c_void_p(self._bits.value + row * stride)
            ctypes.memmove(dst, src[row * row_bytes:(row + 1) * row_bytes], row_bytes)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        pt_src = POINT(0, 0)
        pt_dst = POINT(x, y)
        size = SIZE(w, h)
        ok = user32.UpdateLayeredWindow(self.hwnd, self._screen_dc, ctypes.byref(pt_dst),
                                        ctypes.byref(size), self._mem_dc, ctypes.byref(pt_src),
                                        0, ctypes.byref(blend), ULW_ALPHA)
        if not ok:
            raise OSError('UpdateLayeredWindow failed: %d' % ctypes.get_last_error())

    def close(self):
        if self._old_bitmap:
            gdi32.SelectObject(self._mem_dc, self._old_bitmap)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        if self._mem_dc:
            gdi32.DeleteDC(self._mem_dc)
        if self._screen_dc:
            user32.ReleaseDC(0, self._screen_dc)


# ---------------- 全局状态 ----------------
q = queue.Queue()
typed = ''
anim_id = 0
enabled_flag = True   # 特效开关（普通布尔，pynput 线程安全读取）


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + '  ' + msg + '\n')
    except Exception:
        pass


def on_press(key):
    global typed, anim_id
    try:
        ch = key.char
    except AttributeError:
        # 回车键：确认输入
        if key == keyboard.Key.enter:
            if typed.endswith(QUIT_WORD):
                log('exit by stopmj')
                q.put('quit')
                typed = ''
                return
            if typed.endswith(TRIGGER) and enabled_flag:
                anim_id += 1
                q.put('go')
            typed = ''
        return
    if not ch or not ch.isprintable():
        return
    typed = (typed + ch.lower())[-8:]


# ================ 窗口 ================
root = tk.Tk()
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()

# 缩放：小屏幕缩小特效帧；蜘蛛侠出现在屏幕正上方（按每个特效自己的尺寸计算）
def effect_geometry(eff):
    cw, ch = eff['cell']
    sc = 2 if sh - 80 < ch else 1
    fw, fh = cw // sc, ch // sc
    return fw, fh, (sw - fw) // 2, 20

FW, FH, WIN_X, WIN_Y = effect_geometry(EFFECTS[0])

# ---- 特效窗口（UpdateLayeredWindow，透明）----
win = tk.Toplevel(root)
win.overrideredirect(True)
win.attributes('-topmost', True)
win.geometry('%dx%d+%d+%d' % (FW, FH, WIN_X, WIN_Y))
win.update_idletasks()
win.update()
hwnd = int(win.wm_frame(), 16) if isinstance(win.wm_frame(), str) else win.wm_frame()
layered = LayeredWindow(hwnd)
layered.update(Image.new('RGBA', (FW, FH), (0, 0, 0, 0)), WIN_X, WIN_Y)


def force_topmost():
    try:
        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                                          SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        pass


def show_effect(eff):
    """播放一个特效（eff 来自 EFFECTS，每次触发随机抽取）"""
    global anim_id
    my_id = anim_id
    fw, fh, wx, wy = effect_geometry(eff)
    blank = Image.new('RGBA', (fw, fh), (0, 0, 0, 0))
    log('effect trigger: %s' % eff['name'])
    layered.update(blank, wx, wy)
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    force_topmost()
    try:
        winsound.PlaySound(eff['wav'], winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass
    start = time.time()
    last_frame = -1

    def step():
        nonlocal last_frame
        if my_id != anim_id:
            return
        i = int((time.time() - start) * eff['fps'])
        if i >= eff['count']:
            layered.update(blank, wx, wy)
            return
        if i != last_frame:
            last_frame = i
            try:
                path = os.path.join(eff['dir'], 'f%04d.png' % (eff['first'] + i))
                img = Image.open(path).convert('RGBA')
                if (fw, fh) != eff['cell']:
                    img = img.resize((fw, fh), Image.Resampling.BILINEAR)
                layered.update(img, wx, wy)
            except Exception as e:
                log('frame %d: %s' % (i, e))
                layered.update(blank, wx, wy)
                return
        root.after(8, step)

    step()


def poll():
    try:
        while True:
            m = q.get_nowait()
            if m == 'go':
                show_effect(random.choice(EFFECTS))
            elif m == 'quit':
                on_close()
                return
    except queue.Empty:
        pass
    root.after(50, poll)


# ---- 主控制窗口（深色美化）----
def on_close():
    """关闭窗口（X）即退出程序，无论开关状态"""
    log('exit by window close')
    try:
        listener.stop()
    except Exception:
        pass
    try:
        layered.close()
    except Exception:
        pass
    root.quit()
    root.destroy()


CW, CH = 380, 280
root.title('蜘蛛侠特效')
root.configure(bg=BG)
root.resizable(False, False)
root.geometry('%dx%d+%d+%d' % (CW, CH, (sw - CW) // 2, (sh - CH) // 2))
root.protocol('WM_DELETE_WINDOW', on_close)
try:
    root.iconbitmap(ICON)
except Exception:
    pass

# 标题
tk.Label(root, text='🕷️ 蜘蛛侠特效', bg=BG, fg=FG,
         font=('Microsoft YaHei', 18, 'bold')).pack(pady=(26, 2))
tk.Label(root, text='输入 mj 后按回车，蜘蛛侠从天而降',
         bg=BG, fg=MUTED, font=('Microsoft YaHei', 10)).pack()


def update_btn():
    if enabled_flag:
        btn.config(text='特效：已开启', bg=GREEN, activebackground='#25b96e', fg='#08211a')
    else:
        btn.config(text='特效：已关闭', bg=GRAY, activebackground='#2c3342', fg='#c9d1e0')


def toggle():
    global enabled_flag
    enabled_flag = not enabled_flag
    update_btn()
    status.config(text='特效已开启，输入 mj 回车触发' if enabled_flag else '特效已关闭，窗口关闭即退出')


btn = tk.Button(root, text='', font=('Microsoft YaHei', 14, 'bold'),
                command=toggle, bd=0, relief='flat', cursor='hand2',
                padx=34, pady=10, activeforeground='#ffffff')
btn.pack(pady=(20, 8))
status = tk.Label(root, text='', bg=BG, fg=MUTED, font=('Microsoft YaHei', 10))
status.pack()
tk.Label(root, text='关闭本窗口即退出程序', bg=BG, fg='#5a6270',
         font=('Microsoft YaHei', 9)).pack(pady=(4, 0))
update_btn()
status.config(text='特效已开启，输入 mj 回车触发' if enabled_flag else '特效已关闭，窗口关闭即退出')


# ---------------- 启动 ----------------
listener = keyboard.Listener(on_press=on_press)
listener.daemon = True
listener.start()
log('app started')
if '--test' in sys.argv:
    # --test 随机触发一次；--test 0 / --test 1 强制指定特效（便于逐一验证）
    idx = None
    try:
        p = sys.argv.index('--test')
        if p + 1 < len(sys.argv) and sys.argv[p + 1] in ('0', '1'):
            idx = int(sys.argv[p + 1])
    except ValueError:
        pass
    eff = EFFECTS[idx] if idx is not None else random.choice(EFFECTS)
    root.after(2500, lambda: show_effect(eff))
root.after(50, poll)
root.mainloop()
log('app exited')
