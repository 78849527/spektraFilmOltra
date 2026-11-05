import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

// MARK: - 表面
//
// 暗房石墨 + 相纸白 + 黄铜。只在选中、改过的参数和主操作上出现颜色；
// 其余全部交给亮度台阶与发丝线。

enum MColor {
    static let app = Color(hex: 0x0E0D0B)
    static let canvas = Color(hex: 0x080706)
    static let surface1 = Color(hex: 0x17150F)
    static let surface2 = Color(hex: 0x1F1C15)
    static let surface3 = Color(hex: 0x28241B)
    static let surface4 = Color(hex: 0x353024)

    static let hairline = Color.white.opacity(0.07)
    static let hairlineStrong = Color.white.opacity(0.13)
    static let hairlineFaint = Color.white.opacity(0.035)

    static let text1 = Color(hex: 0xF4F0E7)
    static let text2 = Color(hex: 0xBDB6A8)
    static let text3 = Color(hex: 0x968F81)
    static let text4 = Color(hex: 0x7C7568)

    static let brass = Color(hex: 0xC7A577)
    static let brassHigh = Color(hex: 0xE2C99F)
    static let brassDeep = Color(hex: 0x9C7C52)
    static let brassInk = Color(hex: 0x17130C)
    static let brassWash = Color(hex: 0xC7A577).opacity(0.11)

    static let danger = Color(hex: 0xC0705E)
    static let filmRed = Color(hex: 0xC0705E)
    static let filmYellow = Color(hex: 0xC9A872)
    static let filmGreen = Color(hex: 0x7E9B77)
    static let filmBlue = Color(hex: 0x6D8BA7)

    static let scrim = Color.black.opacity(0.62)
    static let wash = Color.white.opacity(0.05)
    static let washStrong = Color.white.opacity(0.085)

    static func labelTone(_ label: MColorLabel) -> Color {
        switch label {
        case .red: return filmRed
        case .yellow: return filmYellow
        case .green: return filmGreen
        case .blue: return filmBlue
        }
    }
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}

// MARK: - 几何

enum MRadius {
    static let micro: CGFloat = 4
    static let control: CGFloat = 10
    static let card: CGFloat = 14
    static let sheet: CGFloat = 28
    static let pill: CGFloat = 15
}

enum MMetric {
    static let safeTop: CGFloat = 54
    static let safeBottom: CGFloat = 34
    static let pageMargin: CGFloat = 20
    static let navHeight: CGFloat = 44
    static let tabsHeight: CGFloat = 42
    static let touch: CGFloat = 44
    static let drawerMin: CGFloat = 234
    static let drawerMid: CGFloat = 468
    static let drawerMax: CGFloat = 560
}

// MARK: - 字体

extension Font {
    /// 全局使用苹方：中文与数字都走同一套字族，不再混 SF Pro。
    static func mSans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .custom(pingFangName(weight), size: size)
    }

    static func mSerif(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
        .custom(pingFangName(weight), size: size)
    }

    private static func pingFangName(_ weight: Font.Weight) -> String {
        switch weight {
        case .ultraLight: return "PingFangSC-Ultralight"
        case .thin: return "PingFangSC-Thin"
        case .light: return "PingFangSC-Light"
        case .medium: return "PingFangSC-Medium"
        case .semibold, .bold, .heavy, .black: return "PingFangSC-Semibold"
        default: return "PingFangSC-Regular"
        }
    }

    static let pageTitle = Font.mSerif(30, .semibold)
    static let navTitle = Font.mSans(13, .semibold)
    static let rowLabel = Font.mSans(12.5)
    static let bodyText = Font.mSans(12)
    static let caption = Font.mSans(10.5)
    static let micro = Font.mSans(9, .medium)
    static let readout = Font.mSans(10.5, .medium).monospacedDigit()
    static let groupLabel = Font.mSans(9.5, .semibold)
    static let button = Font.mSans(12, .medium)
}

extension View {
    /// 小字距的全大写标签，欧创的“样张说明”语气。
    func mLabel(_ size: CGFloat = 9.5, color: Color = MColor.text3) -> some View {
        self.font(.mSans(size, .semibold))
            .tracking(1.35)
            .foregroundStyle(color)
    }

    func mMeta(_ size: CGFloat = 10, color: Color = MColor.text3) -> some View {
        self.font(.mSans(size, .medium).monospacedDigit())
            .foregroundStyle(color)
    }

    func mHairlineOverlay(_ radius: CGFloat, color: Color = MColor.hairline) -> some View {
        overlay(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(color, lineWidth: 1)
        )
    }
}

// MARK: - 动效

enum MMotion {
    static let push = Animation.spring(response: 0.38, dampingFraction: 0.9)
    static let drawer = Animation.spring(response: 0.34, dampingFraction: 0.86)
    /// 弹窗上弹：阻尼更低，收尾带一点回弹。
    static let pill = Animation.spring(response: 0.42, dampingFraction: 0.66)
    static let state = Animation.easeOut(duration: 0.2)
    static let quick = Animation.easeOut(duration: 0.14)
    static let press = Animation.easeOut(duration: 0.16)
}

// MARK: - 预览调试参数

enum DebugLaunch {
    private static let args = ProcessInfo.processInfo.arguments

    static var showSheet: Bool { args.contains("--sheet") }
    static var exportOpen: Bool { args.contains("--export") }

    static var modePro: Bool {
        guard let index = args.firstIndex(of: "--mode"), args.indices.contains(index + 1) else { return false }
        return args[index + 1] == "pro"
    }

    static var gradeTab: Int {
        guard let index = args.firstIndex(of: "--tab"), args.indices.contains(index + 1) else { return 1 }
        switch args[index + 1] {
        case "presets": return 0
        case "curve": return 2
        default: return 1
        }
    }

    static var developPage: Int {
        guard let index = args.firstIndex(of: "--page"), args.indices.contains(index + 1) else { return 0 }
        switch args[index + 1] {
        case "tone": return 1
        case "color": return 2
        case "detail": return 3
        default: return 0
        }
    }

    /// 预览用：直接以指定抽屉档位启动，方便检查不同高度下的排版。
    static var developDrawer: CGFloat {
        guard let index = args.firstIndex(of: "--drawer"), args.indices.contains(index + 1) else {
            return MMetric.drawerMin
        }
        switch args[index + 1] {
        case "mid": return MMetric.drawerMid
        case "max": return MMetric.drawerMax
        default: return MMetric.drawerMin
        }
    }
}

// MARK: - 面板高度测量
//
// 抽屉要按当前 tab 的内容高度自适应：内容在最小档放得下就锁死一档，否则二档刚好收纳全部内容。

struct MPanelHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

struct MPanelHeightReporter: View {
    var body: some View {
        GeometryReader { geo in
            Color.clear.preference(key: MPanelHeightKey.self, value: geo.size.height)
        }
    }
}

// MARK: - 触感
enum MHaptic {
    static func tick() {
        #if os(iOS)
        UISelectionFeedbackGenerator().selectionChanged()
        #endif
    }

    static func light() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    static func medium() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
    }
}

// MARK: - 图片

enum MPhotoImage {
    static func load(_ photo: MPhoto) -> Image? {
        guard let url = photo.thumbnailURL, let image = MImage.thumbnail(url: url) else { return nil }
        return MImage.swiftUI(image)
    }
}
