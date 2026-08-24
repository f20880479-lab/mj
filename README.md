# 蜘蛛侠桌面特效（Spiderman Desktop Effect）

一个 Windows 桌面小应用：全局监听键盘，输入 `mj` 后按回车，屏幕正上方弹出**透明蜘蛛侠动画**（带声音），约 2.8 秒自动消失。应用常驻，可反复触发；带控制窗口（特效开关），关闭窗口即退出。

## 快速开始

- **免安装（推荐）**：下载 `蜘蛛侠特效/` 文件夹（含 exe），双击 `蜘蛛侠特效.exe` 即用，无需安装 Python
- **源码运行**：需要 Python 3，`pip install pynput pillow` 后运行 `桌面特效/蜘蛛侠桌面特效.pyw`

## 功能

- 输入 `mj` 后按**回车** → 蜘蛛侠从屏幕**正上方**播放（透明背景、置顶悬浮、点击穿透、带声音约 2.8 秒），播放完自动消失
- **持续生效**：无论触发多少次都会重播；播放中再触发会先清掉旧画面和声音，从头重播
- **控制窗口**：深色面板 + "特效开关"按钮；关闭窗口（X）即退出程序
- 输入 `stopmj` 后按回车 → 退出

## 技术实现

- **透明**：Win32 `UpdateLayeredWindow` 逐像素 alpha（参考 [desk-pet](https://github.com/Egger0/desk-pet) 方案），不依赖 tkinter 色键（`-transparentcolor` 在 >100% DPI 缩放下会整窗透明失效）
- **动画**：166 帧透明 PNG（60fps = 2.77 秒），PIL 逐帧渲染 + 按时间轴推进，与音频（2.75 秒）严格同步
- **素材**：从 `8月21日.mp4`（60fps 原视频）抠图得到透明蜘蛛侠帧序列（`scripts/segment_solid.py`）

## 自定义

| 想改什么 | 怎么做 |
| --- | --- |
| 触发词 | 修改 `桌面特效/蜘蛛侠桌面特效.pyw` 中的 `TRIGGER`（默认 `mj`） |
| 更换人物视频 | 替换 `8月21日.mp4` → 跑 `scripts/segment_solid.py` → 把输出帧复制到 `桌面特效/frames/` |
| 重新打包 exe | 在 `桌面特效/` 下执行：`pyinstaller --noconfirm --windowed --name 蜘蛛侠特效 --icon icon.ico --add-data "frames;frames" --add-data "audio.wav;." --add-data "icon.ico;." 蜘蛛侠桌面特效.pyw` |

## 文件说明

- `蜘蛛侠特效/` — 免安装 exe 版（整个文件夹一起分发，含运行时依赖与素材，约 90MB）
- `桌面特效/` — 源码版（.pyw 主程序 + frames 素材 + audio + icon + 启动/安装脚本）
- `8月21日.mp4` — 原始视频（素材来源）
- `scripts/` — 抠图与素材生成脚本
