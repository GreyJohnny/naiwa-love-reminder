# 牛来的爱意提醒物语 · Windows 版 🐮💛

macOS 原版（SwiftUI + AppKit）的 Windows 移植版，用 **Python 3 + PySide6 (Qt 6)** 重写，
行为、界面、数据格式都对着原版一比一还原 —— 原版有什么，这里就有什么。

本仓库是 **牛来皮肤版**：在 `naiwa-windows`（奶蛙版）的基础上换了一套素材 ——
弹窗图、弹窗音效、标题、标题小图全部换成牛来，另外加了一个「点一下添加按钮就"牛来"一声」的
小彩蛋；其余逻辑与奶蛙版完全一致，改了哪些见下面的「牛来皮肤改了什么」。

> macOS 原版就在本仓库根目录：[`app/NaiwaApp.swift`](../app/NaiwaApp.swift)

## 一句话功能

在你设定的时间范围内，每隔一段时间就有一车牛来从屏幕中央弹出来盯着你，
到点自动停、第二天自动又开始；关掉主窗口时会问你是直接关掉还是缩进托盘继续盯着你。

## 快速开始

### 直接跑（开发模式）

双击 `run.bat` 就行。它会用 `pythonw.exe` 启动，不弹黑框。

命令行等价写法：

```powershell
pythonw app\niulai_app.py
```

### 打包成免安装 exe

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

产物在 `dist\NiulaiReminder\`，整个文件夹拷到哪都能跑。
想让牛来开机就上班：`Win+R` → `shell:startup` → 把 exe 的快捷方式丢进去。

## 操作说明

### 新建一个提醒

1. 「提醒我干嘛」写标签，比如 `喝水`、`站起来活动`、`远眺 20 秒`
2. 设置间隔：数字 + 单位（秒 / 分钟 / 小时），比如 `30 分钟`
3. 设置生效时间范围，比如 `09:00 ~ 22:00`
4. 点「＋ 添加提醒」

### 列表里每行能干什么

| 按钮 | 作用 |
| --- | --- |
| 编辑 | 改标签 / 间隔 / 时间范围（原版没有，这是截图版补上的功能） |
| 测试 | 立刻预览一次弹窗 + 笑声 |
| 暂停 / 继续 | 暂停后不再提醒，继续时重新起算一个完整间隔 |
| 删除 | 删除前会问一句，避免手滑 |

左边的圆点是状态灯：

- 🟢 绿色 = 进行中
- 🟠 橙色 = 未到开始时间
- ⚪ 灰色 = 今天已结束（整行会变淡）
- 🔵 蓝色 = 已暂停

### 声音

「音效音量」滑杆随时调，「试听」按钮立刻放一遍，音量会记到设置里。

### 托盘

点右上角 X 会先问一句：**直接关闭**（整个 App 退出）还是 **程序最小化**（缩到右下角托盘继续盯着你）；
勾上「下次不再提醒」就记住这次的选择，以后关窗口不再弹框。点托盘里的小牛来图标可以随时把主窗口叫回来；
右键托盘图标有「打开主窗口 / 退出牛来提醒」，从托盘菜单退出不会再问。

> 想恢复"每次都问"：把 `settings.json` 里的 `"closeAction"` 删掉（或整个文件删掉，音量会一起重置）。

> Windows 11 默认会把新图标塞进托盘的「隐藏的图标」里（就是托盘左边那个 `^` 箭头）。
> 想让它常驻，点开 `^` 把牛来拖到底部任务栏上即可。

### 小提示

- 结束时间设为 `23:59` 基本等于"今天一直提醒"；开始 = 结束视为全天生效
- 支持跨午夜，比如 `22:00 ~ 02:00`
- 提醒弹窗可以叠加，多个提醒同时到点会按 34px 错位排开
- 弹窗 20 秒没人管会自己消失，点图或点「知道啦 😄」也能立刻关掉

## 数据放在哪

```
%APPDATA%\NiulaiReminder\reminders.json    # 提醒列表
%APPDATA%\NiulaiReminder\settings.json     # 音量 + 关窗口的选择（closeAction）
```

`reminders.json` 的字段名（`id` / `label` / `intervalSec` / `start` / `end` / `paused`）
和 macOS 原版完全一致 —— 两边（包括奶蛙版）的提醒列表可以直接互相拷贝。
卸载时删掉 `%APPDATA%\NiulaiReminder` 就干净了。

## 迁移对照表（macOS → Windows）

| macOS 原版 | Windows 版 | 说明 |
| --- | --- | --- |
| `MenuBarExtra` 菜单栏图标 | `QSystemTrayIcon` 系统托盘 | Windows 没有菜单栏，改用托盘 |
| `NSWindow.level = .floating` | `Qt.WindowStaysOnTopHint` | 弹窗浮在所有窗口之上 |
| `styleMask = [.borderless]` | `Qt.FramelessWindowHint` | 无边框窗口 |
| 透明窗口 + 白色圆角卡片 | `WA_TranslucentBackground` + QSS 圆角 + `QGraphicsDropShadowEffect` | 阴影是 Qt 手绘的 |
| `canJoinAllSpaces` | 跟随鼠标所在显示器 | Windows 没有"空间"概念，按光标位置选屏幕 |
| `NSScreen.visibleFrame` | `QScreen.availableGeometry()` | 屏幕可用区域 |
| `beginActivity()` 防 App Nap | 不需要 | Windows 没有 App Nap 机制，定时器不会被掐 |
| `applicationShouldTerminateAfterLastWindowClosed = false` | `app.setQuitOnLastWindowClosed(False)` + `closeEvent` 里 `hide()` | 关窗不退出 |
| `AVAudioPlayer` 播 mp3 | `QMediaPlayer` + `QAudioOutput` | 支持 mp3 和音量调节 |
| `Bundle.main.url(forResource:)` | `sys._MEIPASS`（打包后）/ 项目 `assets/`（源码运行） | 见 `resource_root()` |
| `~/Library/Application Support` | `%APPDATA%\NiulaiReminder\` | 数据目录 |
| `DatePicker(.hourAndMinute)` | `QTimeEdit` | 时间选择 |
| `.app` + `Info.plist` + `.icns` | PyInstaller `--windowed --icon assets\niulai.ico` | 打包方式 |
| 登录项自启 | `shell:startup` 放快捷方式 | 见上文 |
| SwiftUI 弹簧动画 / `repeatForever` 摇摆 | `QVariantAnimation`(OutBack) + 正弦波 QTimer | 见 `PopupWindow._redraw_image` |

## 与原版的差异（都是有意的）

1. **补上了截图版的两个功能**：音效音量滑杆 + 试听、每条提醒的「编辑」按钮。
   原版源码（1.0.0）里没有这两样，但用户给的界面截图里有。
2. **跨午夜提醒的状态文案修正**：原版对 `22:00 ~ 02:00` 这种跨午夜的提醒，
   在 21:00 也会显示"今天已结束"；Windows 版按中午 12 点分界，晚上显示"未到开始时间"、
   凌晨显示"今天已结束"。**只影响文案，触发逻辑一模一样。**
3. **删除会先确认**：原版点了就删，这里弹一句"确定删掉「xxx」吗？"
4. **同一时刻多声笑声不叠加**：原版每次提醒新建一个播放器、可以叠着响；
   这里共用一个播放器，正在响时再触发就从头播，避免几个提醒同时到点时炸耳朵。
5. **弹窗不抢焦点**：加了 `Qt.WindowDoesNotAcceptFocus`，弹窗时不会把你正在打字的光标抢走。
   原版（macOS）本来就是非激活面板，这里是为了对齐这个行为。
6. **关窗口先问一句**（牛来版新增）：点右上角 X 不再直接缩托盘，而是弹「直接关闭 / 程序最小化」，
   可以勾"下次不再提醒"把选择写进 `settings.json` 的 `closeAction`；从托盘菜单退出则不问。

## 牛来皮肤改了什么（相对奶蛙版）

| 位置 | 奶蛙版 | 牛来版 |
| --- | --- | --- |
| 弹窗主图 | `laugh1.png ~ laugh7.png` 静态图轮播 | `niulaigif.gif` 动图（36 帧循环）+ 摇摆动画 |
| 弹窗音效 | `naiwa_laugh.mp3` | `mama.mp3` |
| 标题 / 窗口名 / 托盘提示 | 奶蛙的爱意提醒物语 | 牛来的爱意提醒物语 |
| 标题左边的小图 | `laugh2.png`（30x30） | `niulai.jpg`（30x30） |
| 弹窗提示文字 | 奶 蛙 提 醒 你 | 牛 来 提 醒 你 |
| 点「＋ 添加提醒」/「知道啦」 | 不发声 | 各响一声 `niulai.mp3`（**新加的功能**） |
| 点右上角 X | 直接缩到托盘 | 弹「直接关闭 / 程序最小化」，可勾选记住（**新加的功能**） |
| 托盘 / 应用图标 | `naiwa_tray.png` / `naiwa.ico` | `niulai_tray.png` / `niulai.ico`（从 niulai.jpg 裁的牛头） |
| 数据目录 | `%APPDATA%\NaiwaReminder` | `%APPDATA%\NiulaiReminder` |

两个音效各用一个播放器，互不打断；音量滑杆对两个音效都生效。

## 目录结构

```
niulai-windows/
├── app/
│   └── niulai_app.py           # 全部源码（约 1400 行，含注释），结构跟原版一一对应
├── assets/
│   ├── niulaigif.gif           # 弹窗主图：牛来动图（36 帧循环，和摇摆动画叠着播）
│   ├── niulai.jpg              # 标题左边的小图（图标素材也是它）
│   ├── mama.mp3                # 弹窗音效
│   ├── niulai.mp3              # 点「＋ 添加提醒」/「知道啦」的音效
│   ├── niulai_tray.png         # 抠好背景的托盘图标（由工具生成）
│   └── niulai.ico              # Windows 应用图标（由工具生成）
├── tools/
│   ├── make_icons.py           # 从 niulai.jpg 裁牛头生成托盘图标和 ico
│   └── capture_window.py       # 开发用：给窗口截图（被挡住也能拍）
├── run.bat                     # 双击即跑
├── build.ps1                   # 打包成 exe
└── README.md
```

源码里的模块划分跟 Swift 原版一一对应，想对着读的话看文件头的对照表：

```
struct Reminder        -> class Reminder        数据模型
enum Assets            -> class Assets          资源缓存
final class PopupManager -> class PopupManager  弹窗管理
struct PopupView       -> class PopupWindow     弹窗视图
final class ReminderStore -> class ReminderStore 提醒引擎
struct ContentView     -> class MainWindow      主界面
@main struct NaiwaApp  -> main() + build_tray() 入口 + 托盘
```

## 已知限制

- **独占全屏的游戏**（比如某些老游戏的全屏模式）下弹窗可能显示不出来 ——
  macOS 原版用 `fullScreenAuxiliary` 解决了这个问题，Windows 这边没有完全等价的开关。
  无边框全屏（现在的游戏基本都用这种）不受影响。
- **系统睡眠期间不会提醒**，唤醒后会立刻补一次，然后按新间隔继续。
- 标题栏颜色跟随你的 Windows 强调色设置（大部分窗口都这样，不是这个 App 特有的）。
- 同一时间只能开一个实例，开两个会各弹各的（原版也是这样，暂未加单实例锁）。

## 环境要求

- Windows 10 / 11
- Python 3.10+（本机是 3.12）
- `pip install PySide6`（打包 exe 另需 `pyinstaller`）

## 免责声明

### 1. 健康与医疗相关（重要）

- 本软件**仅为时间管理/提醒工具**，不构成任何医疗建议、诊断或治疗方案。
- 软件提醒的护眼、起身活动等习惯仅为一般性健康生活方式提示，**不能替代眼科医生或其他专业医疗人员的意见**。如果您已经出现视力下降、眼睛干涩、疼痛或其他不适症状，请及时就医，不要依赖本软件。
- 即使正常使用本软件，也**不保证**能预防或缓解任何眼部疾病或身体不适。长时间使用电子设备的风险因人而异，请根据自身情况合理安排作息。
- 因使用（或未能正常使用）本软件而导致的任何健康问题、延误就医等后果，作者不承担任何责任。

### 2. 软件功能与稳定性

- 本软件按 **"现状"（AS IS）** 提供，不附带任何明示或默示的保证，包括但不限于适销性、特定用途适用性、不间断运行、无错误的保证。
- 提醒功能依赖 App 在后台持续运行。系统休眠、强制退出 App、系统更新、资源限制等情况都可能导致提醒延迟或失效。**请勿将本软件用于服药、医疗监护、安全警报等任何"错过提醒可能造成损害"的关键场景。**
- 因软件缺陷、提醒未触发或延迟触发而造成的任何直接或间接损失，作者概不负责。

### 3. 素材版权

- 仓库中的"牛来"表情包图片为网络流传的二次创作（梗图），其原始形象的著作权归原权利人所有；本仓库仅作个人学习、非商业用途的引用，**不代表作者对这些形象主张任何权利**。如有侵权，请联系删除，作者将第一时间移除。
- 音效文件由使用者自行提供/替换，请确保您使用的音效来源合法。因替换素材产生的版权纠纷与作者无关。
- 本项目代码采用 MIT 协议开源，但**协议范围仅限代码本身**，不延伸至上述第三方图片、音色素材。

---

原版作者的那句话照抄一遍：

> 愿每 30 分钟一车的牛来，都能把你从屏幕前拽回来一分钟。🐮
