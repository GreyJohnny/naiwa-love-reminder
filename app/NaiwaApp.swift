import SwiftUI
import AppKit
import AVFoundation

// MARK: - 数据模型

struct Reminder: Identifiable, Codable, Equatable {
    var id: UUID
    var label: String
    var intervalSec: Int
    var start: String   // "HH:mm"
    var end: String     // "HH:mm"
    var paused: Bool
    var nextFire: Date? = nil   // 仅运行时使用，不持久化

    enum CodingKeys: String, CodingKey { case id, label, intervalSec, start, end, paused }

    init(id: UUID = UUID(), label: String, intervalSec: Int, start: String, end: String, paused: Bool = false) {
        self.id = id
        self.label = label
        self.intervalSec = intervalSec
        self.start = start
        self.end = end
        self.paused = paused
    }
}

// MARK: - 资源缓存

enum Assets {
    static let images: [NSImage] = (1...7).compactMap { i in
        Bundle.main.url(forResource: "laugh\(i)", withExtension: "png").flatMap { NSImage(contentsOf: $0) }
    }
    static let sounds: [URL] = ["naiwa_laugh"].compactMap {
        Bundle.main.url(forResource: $0, withExtension: "mp3")
    }
    static var menuIcon: NSImage? {
        guard let url = Bundle.main.url(forResource: "laugh2", withExtension: "png"),
              let img = NSImage(contentsOf: url) else { return nil }
        img.size = NSSize(width: 18, height: 18)
        return img
    }
}

// MARK: - 弹窗管理

final class PopupManager: NSObject, AVAudioPlayerDelegate, NSWindowDelegate {
    static let shared = PopupManager()

    private var windows: [NSWindow] = []
    private var players: [AVAudioPlayer] = []

    func fire(label: String) {
        DispatchQueue.main.async {
            self.playSound()
            self.showPopup(label: label)
        }
    }

    private func playSound() {
        guard let url = Assets.sounds.randomElement(),
              let p = try? AVAudioPlayer(contentsOf: url) else { return }
        p.delegate = self
        p.play()
        players.append(p)
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        players.removeAll { $0 === player }
    }

    private final class WindowRef { weak var window: NSWindow? }

    private func showPopup(label: String) {
        let ref = WindowRef()
        let view = PopupView(label: label, onClose: { ref.window?.close() })
        let hosting = NSHostingView(rootView: view)

        let size = NSSize(width: 380, height: 500)
        let window = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                              styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.contentView = hosting
        window.delegate = self
        window.isReleasedWhenClosed = false   // 关键：close 时不释放，由 windows 数组统一管理生命周期

        if let screen = NSScreen.main {
            let sf = screen.visibleFrame
            let offset = CGFloat(windows.count % 5) * 34
            window.setFrameOrigin(NSPoint(
                x: sf.midX - size.width / 2 + offset,
                y: sf.midY - size.height / 2 - offset))
        }
        ref.window = window
        window.orderFrontRegardless()
        windows.append(window)

        // 20 秒自动关闭
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak window] in
            window?.close()
        }
    }

    func windowWillClose(_ notification: Notification) {
        guard let w = notification.object as? NSWindow else { return }
        // 必须等 close() 彻底执行完再释放窗口，否则窗口会在 close 中途被销毁导致崩溃
        DispatchQueue.main.async { [weak self] in
            self?.windows.removeAll { $0 === w }
        }
    }
}

// MARK: - 提醒引擎

final class ReminderStore: ObservableObject {
    static let shared = ReminderStore()

    @Published var reminders: [Reminder] = []
    private var timer: Timer?
    private var activity: NSObjectProtocol?

    enum Status { case on, wait, off, pause }

    private init() {
        load()
        let t = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in self?.tick() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
        // 防止 App Nap 把计时器挂起
        activity = ProcessInfo.processInfo.beginActivity(
            options: [.userInitiatedAllowingIdleSystemSleep], reason: "奶蛙提醒引擎")
    }

    // MARK: 增删改
    func add(label: String, intervalSec: Int, start: String, end: String) {
        reminders.append(Reminder(label: label, intervalSec: intervalSec, start: start, end: end))
        save()
    }
    func delete(_ r: Reminder) {
        reminders.removeAll { $0.id == r.id }
        save()
    }
    func togglePause(_ r: Reminder) {
        guard let i = reminders.firstIndex(where: { $0.id == r.id }) else { return }
        reminders[i].paused.toggle()
        reminders[i].nextFire = nil
        save()
    }

    // MARK: 时间逻辑
    private func minutesNow(_ d: Date) -> Double {
        let c = Calendar.current.dateComponents([.hour, .minute, .second], from: d)
        return Double((c.hour ?? 0) * 60 + (c.minute ?? 0)) + Double(c.second ?? 0) / 60.0
    }
    private func parseHM(_ s: String) -> Int {
        let p = s.split(separator: ":")
        return (Int(p.first ?? "0") ?? 0) * 60 + (Int(p.last ?? "0") ?? 0)
    }
    func inRange(_ r: Reminder, _ now: Date) -> Bool {
        let m = minutesNow(now)
        let s = Double(parseHM(r.start)), e = Double(parseHM(r.end))
        if s == e { return true }
        if s < e { return m >= s && m < e }
        return m >= s || m < e   // 跨午夜
    }
    func status(_ r: Reminder, _ now: Date) -> Status {
        if r.paused { return .pause }
        if !inRange(r, now) {
            let m = minutesNow(now)
            let s = Double(parseHM(r.start)), e = Double(parseHM(r.end))
            let ended = s < e ? (m >= e) : (m >= e && m < s)
            return ended ? .off : .wait
        }
        return .on
    }

    func tick() {
        let now = Date()
        for i in reminders.indices {
            if reminders[i].paused { continue }
            if !inRange(reminders[i], now) { reminders[i].nextFire = nil; continue }  // 时间过了就停
            if reminders[i].nextFire == nil {
                reminders[i].nextFire = now.addingTimeInterval(TimeInterval(reminders[i].intervalSec))
            }
            if now >= reminders[i].nextFire! {
                let r = reminders[i]
                reminders[i].nextFire = now.addingTimeInterval(TimeInterval(r.intervalSec))
                PopupManager.shared.fire(label: r.label)
            }
        }
    }

    // MARK: 持久化
    private var fileURL: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("NaiwaReminder", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("reminders.json")
    }
    func save() {
        if let data = try? JSONEncoder().encode(reminders) {
            try? data.write(to: fileURL)
        }
    }
    func load() {
        guard let data = try? Data(contentsOf: fileURL),
              let arr = try? JSONDecoder().decode([Reminder].self, from: data) else { return }
        reminders = arr
    }
}

// MARK: - 弹窗视图

struct PopupView: View {
    let label: String
    let onClose: () -> Void

    @State private var frame = Int.random(in: 0..<7)
    @State private var appear = false
    @State private var wobble = false
    private let cycler = Timer.publish(every: 0.3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 10) {
            if !Assets.images.isEmpty {
                Image(nsImage: Assets.images[frame % Assets.images.count])
                    .resizable()
                    .scaledToFit()
                    .frame(width: 190, height: 190)
                    .rotationEffect(.degrees(wobble ? 6 : -6))
                    .animation(.easeInOut(duration: 0.3).repeatForever(autoreverses: true), value: wobble)
                    .onTapGesture(perform: onClose)
            }
            Text("奶 蛙 提 醒 你")
                .font(.system(size: 12))
                .foregroundColor(.gray)
                .kerning(3)
            Text(label)
                .font(.system(size: 26, weight: .bold))
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onClose) {
                Text("知道啦 😄")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color(red: 0.42, green: 0.31, blue: 0))
                    .padding(.horizontal, 30)
                    .padding(.vertical, 10)
                    .background(Capsule().fill(Color(red: 1, green: 0.788, blue: 0.235)))
            }
            .buttonStyle(.plain)
            .padding(.top, 6)
        }
        .padding(28)
        .frame(width: 320)
        .background(
            RoundedRectangle(cornerRadius: 22)
                .fill(Color.white)
                .shadow(color: .black.opacity(0.18), radius: 24, x: 0, y: 12)
        )
        .padding(30)   // 透明边距给阴影留空间
        .scaleEffect(appear ? 1 : 0.6)
        .opacity(appear ? 1 : 0)
        .onAppear {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.6)) { appear = true }
            wobble = true
        }
        .onReceive(cycler) { _ in frame = (frame + 1) % max(1, Assets.images.count) }
    }
}

// MARK: - 主界面

struct ContentView: View {
    @StateObject private var store = ReminderStore.shared
    @State private var label = ""
    @State private var intervalText = "30"
    @State private var unit = 60
    @State private var startDate = Date()
    @State private var endDate = Date().addingTimeInterval(7200)
    @State private var now = Date()
    @State private var alertMsg: String?
    private let clock = Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()

    private static let hmFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm"; return f
    }()
    private static let timeFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; return f
    }()
    private static let dateFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy 年 M 月 d 日 · EEEE"; f.locale = Locale(identifier: "zh_CN"); return f
    }()

    private let yellow = Color(red: 1, green: 0.788, blue: 0.235)
    private let ink = Color(red: 0.17, green: 0.17, blue: 0.17)
    private let line = Color(red: 0.925, green: 0.925, blue: 0.925)

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollView {
                VStack(spacing: 20) {
                    formCard
                    listSection
                }
                .padding(20)
            }
        }
        .frame(minWidth: 760, minHeight: 640)
        .background(Color.white)
        .onReceive(clock) { now = $0 }
        .background(WindowAccessor())
        .alert("提示", isPresented: Binding(
            get: { alertMsg != nil },
            set: { if !$0 { alertMsg = nil } })
        ) {
            Button("好的", role: .cancel) {}
        } message: {
            Text(alertMsg ?? "")
        }
    }

    // MARK: 顶部时钟
    private var header: some View {
        VStack(spacing: 6) {
            HStack(spacing: 8) {
                if Assets.images.count > 1 {
                    Image(nsImage: Assets.images[1])
                        .resizable().scaledToFit().frame(width: 30, height: 30)
                }
                Text("奶蛙的爱意提醒物语")
                    .font(.system(size: 13)).foregroundColor(.gray).kerning(2)
            }
            Text(Self.timeFmt.string(from: now))
                .font(.system(size: 54, weight: .bold))
                .monospacedDigit()
                .foregroundColor(ink)
            Text(Self.dateFmt.string(from: now))
                .font(.system(size: 14)).foregroundColor(.gray)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 18)
        .background(LinearGradient(
            colors: [Color(red: 1, green: 0.992, blue: 0.96), .white],
            startPoint: .top, endPoint: .bottom))
    }

    // MARK: 新建提醒表单
    private var formCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("⏰ 新建提醒").font(.system(size: 16, weight: .semibold)).foregroundColor(ink)
            HStack(alignment: .bottom, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("提醒我干嘛（标签）").font(.system(size: 12)).foregroundColor(.gray)
                    TextField("例如：喝水、站起来活动、吃药…", text: $label)
                        .textFieldStyle(.roundedBorder)
                        .frame(minWidth: 220)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("每隔多久提醒一次").font(.system(size: 12)).foregroundColor(.gray)
                    HStack(spacing: 6) {
                        TextField("30", text: $intervalText)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 64)
                        Picker("", selection: $unit) {
                            Text("秒").tag(1)
                            Text("分钟").tag(60)
                            Text("小时").tag(3600)
                        }
                        .labelsHidden()
                        .frame(width: 76)
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("生效时间范围（过了就停）").font(.system(size: 12)).foregroundColor(.gray)
                    HStack(spacing: 6) {
                        DatePicker("", selection: $startDate, displayedComponents: .hourAndMinute)
                            .labelsHidden()
                        Text("~").foregroundColor(.gray)
                        DatePicker("", selection: $endDate, displayedComponents: .hourAndMinute)
                            .labelsHidden()
                    }
                }
            }
            Button(action: addReminder) {
                Text("＋ 添加提醒")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Color(red: 0.42, green: 0.31, blue: 0))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(RoundedRectangle(cornerRadius: 12).fill(yellow))
            }
            .buttonStyle(.plain)
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.white)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(line, lineWidth: 1))
                .shadow(color: .black.opacity(0.04), radius: 8, x: 0, y: 3)
        )
    }

    private func addReminder() {
        let trimmed = label.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { alertMsg = "先写一下这个提醒是干嘛的～"; return }
        guard let num = Int(intervalText), num > 0 else { alertMsg = "间隔要大于 0 哦"; return }
        store.add(label: trimmed,
                  intervalSec: num * unit,
                  start: Self.hmFmt.string(from: startDate),
                  end: Self.hmFmt.string(from: endDate))
        label = ""
    }

    // MARK: 提醒列表
    private var listSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("📋 我的提醒（可同时开多个）").font(.system(size: 16, weight: .semibold)).foregroundColor(ink)
            if store.reminders.isEmpty {
                Text("还没有提醒，在上面添加一个吧 👆")
                    .font(.system(size: 13)).foregroundColor(.gray)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 30)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(style: StrokeStyle(lineWidth: 1, dash: [6]))
                            .foregroundColor(line)
                    )
            } else {
                ForEach(store.reminders) { r in row(for: r) }
            }
        }
    }

    private func statusInfo(_ s: ReminderStore.Status) -> (String, Color) {
        switch s {
        case .on:    return ("进行中", Color(red: 0.2, green: 0.78, blue: 0.35))
        case .wait:  return ("未到开始时间", Color(red: 1, green: 0.58, blue: 0))
        case .off:   return ("今天已结束", Color(red: 0.78, green: 0.78, blue: 0.8))
        case .pause: return ("已暂停", Color(red: 0.04, green: 0.52, blue: 1))
        }
    }

    private func fmtInterval(_ sec: Int) -> String {
        if sec % 3600 == 0 { return "\(sec / 3600) 小时" }
        if sec % 60 == 0 { return "\(sec / 60) 分钟" }
        return "\(sec) 秒"
    }

    private func countdown(_ r: Reminder) -> String {
        guard store.status(r, now) == .on, let nf = r.nextFire else { return "—" }
        let diff = max(0, Int(nf.timeIntervalSince(now)))
        let m = diff / 60, s = diff % 60
        return m > 0 ? "\(m)分\(s)秒" : "\(s)秒"
    }

    private func row(for r: Reminder) -> some View {
        let st = store.status(r, now)
        let (stText, stColor) = statusInfo(st)
        return HStack(spacing: 12) {
            Circle()
                .fill(stColor)
                .frame(width: 10, height: 10)
                .shadow(color: stColor.opacity(0.4), radius: 3)
            VStack(alignment: .leading, spacing: 3) {
                Text(r.label)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(ink)
                    .lineLimit(1)
                Text("每 \(fmtInterval(r.intervalSec)) 一次 · \(r.start) ~ \(r.end) · \(stText)")
                    .font(.system(size: 12)).foregroundColor(.gray)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("下次提醒").font(.system(size: 11)).foregroundColor(.gray)
                Text(countdown(r))
                    .font(.system(size: 14, weight: .semibold))
                    .monospacedDigit()
                    .foregroundColor(ink)
            }
            .frame(minWidth: 80)
            HStack(spacing: 6) {
                smallBtn("测试") { PopupManager.shared.fire(label: r.label) }
                smallBtn(r.paused ? "继续" : "暂停") { store.togglePause(r) }
                smallBtn("删除", danger: true) { store.delete(r) }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.white)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(line, lineWidth: 1))
                .shadow(color: .black.opacity(0.03), radius: 5, x: 0, y: 2)
        )
        .opacity(st == .off ? 0.55 : 1)
    }

    private func smallBtn(_ title: String, danger: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12))
                .foregroundColor(danger ? Color(red: 1, green: 0.23, blue: 0.19) : ink)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.white)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(line, lineWidth: 1))
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - 窗口辅助

struct WindowAccessor: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            view.window?.isReleasedWhenClosed = false   // 关闭只是隐藏，App 继续运行
        }
        return view
    }
    func updateNSView(_ nsView: NSView, context: Context) {}
}

// MARK: - AppDelegate

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        _ = ReminderStore.shared   // 启动提醒引擎
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false   // 关窗不退出，后台继续提醒
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            for w in sender.windows where !(w is NSPanel) && w.canBecomeKey {
                w.makeKeyAndOrderFront(nil)
            }
            sender.activate()
        }
        return true
    }
}

// MARK: - App 入口

@main
struct NaiwaApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        WindowGroup(id: "main") {
            ContentView()
        }
        .defaultSize(width: 800, height: 680)

        MenuBarExtra {
            Button("打开主窗口") {
                openWindow(id: "main")
                NSApplication.shared.activate()
            }
            Divider()
            Button("退出奶蛙提醒") { NSApplication.shared.terminate(nil) }
        } label: {
            if let img = Assets.menuIcon {
                Image(nsImage: img)
            } else {
                Image(systemName: "alarm")
            }
        }
    }
}
