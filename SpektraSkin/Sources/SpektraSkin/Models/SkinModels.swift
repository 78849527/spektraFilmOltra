import Foundation

// MARK: - 共享值类型

enum ColorLabel: String, CaseIterable, Identifiable, Hashable {
    case red, yellow, green, blue

    var id: String { rawValue }

    var title: String {
        switch self {
        case .red: return "红"
        case .yellow: return "黄"
        case .green: return "绿"
        case .blue: return "蓝"
        }
    }
}

struct PhotoItem: Identifiable, Hashable {
    let id: String
    let filename: String
    let asset: String
    let film: String
    let paper: String?
    let dimensions: String
    let isRaw: Bool
    let favorite: Bool
    let color: ColorLabel?
    let isGraded: Bool

    var metaLine: String {
        [film, dimensions].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var editorMetaLine: String {
        [dimensions, film, paper ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var aspectRatio: CGFloat {
        let parts = dimensions.split(separator: "×").compactMap { Double($0) }
        guard parts.count == 2, parts[1] > 0 else { return 4.0 / 3.0 }
        return CGFloat(parts[0] / parts[1])
    }
}

struct FolderItem: Identifiable, Hashable {
    let id: String
    let name: String
    let count: Int
    let isCurrent: Bool
}

struct LibrarySnapshot {
    let folderCount: Int
    let photoCount: Int
    let sectionTitle: String
    let sectionCount: String
    let folders: [FolderItem]
    let photos: [PhotoItem]
    let statusMessage: String
}

// MARK: - 预设

enum FilmKind: Hashable {
    case negative
    case reversal
    case cinema
    case paper
}

struct PresetItem: Identifiable, Hashable {
    let id: String
    let name: String
    let meta: String
    let brand: String
    let kind: FilmKind
    let hue: Double
}

struct PresetCatalog {
    let films: [PresetItem]
    let papers: [PresetItem]
}

// MARK: - 快速控制

struct QuickAxis: Identifiable, Hashable {
    let id: String
    let label: String
    let range: ClosedRange<Double>
    let step: Double
    let decimals: Int
    let suffix: String
    let baseValue: Double
    let value: Double
    let unavailableReason: String?

    var isDirty: Bool { abs(value - baseValue) > 1e-9 }

    func text(for value: Double) -> String {
        let normalized = abs(value) < pow(10, Double(-decimals)) * 0.5 ? 0 : value
        var text = String(format: "%.\(decimals)f", normalized)
        if decimals > 0, text.contains(".") {
            while text.hasSuffix("0") { text.removeLast() }
            if text.hasSuffix(".") { text.removeLast() }
        }
        if range.lowerBound < 0, normalized > 0 { text = "+" + text }
        return text + suffix
    }
}

struct QuickPad: Hashable {
    let title: String
    let x: Double
    let y: Double
}

struct QuickGroup: Identifiable, Hashable {
    let id: String
    let title: String
    let axes: [QuickAxis]
    let pad: QuickPad?
}

// MARK: - 专业参数

enum ParamControl: Hashable {
    case slider(value: Double, valueText: String, dirty: Bool)
    case toggle(isOn: Bool)
    case choice(text: String)
}

struct ParamRow: Identifiable, Hashable {
    let id: String
    let label: String
    let control: ParamControl
    let isEnabled: Bool
}

struct ParamGroup: Identifiable, Hashable {
    let id: String
    let title: String
    let rows: [ParamRow]
}

struct ParamPage: Identifiable, Hashable {
    let id: String
    let title: String
    let groups: [ParamGroup]
}

// MARK: - 显影

struct HistogramData: Hashable {
    let red: [Double]
    let green: [Double]
    let blue: [Double]
}

struct EditorSnapshot {
    let photo: PhotoItem
    let filmName: String
    let paperName: String
    let filmstrip: [PhotoItem]
    let quickGroups: [QuickGroup]
    let proPages: [ParamPage]
    let histogram: HistogramData
    let dirtyCount: Int
    let currentFilmID: String
    let currentPaperID: String
    let stripCount: Int
}

struct GradeSnapshot {
    let photo: PhotoItem
    let handoffMeta: String
}

// MARK: - 后端边界
//
// 皮肤只依赖这一份只读快照协议。当前实现是静态预览数据；
// 未来 Swift 引擎实现同一协议后，视图代码不需要改。
protocol SpektraSkinDataSource {
    var library: LibrarySnapshot { get }
    var presets: PresetCatalog { get }
    func editor(for photoID: PhotoItem.ID) -> EditorSnapshot
    func grade(for photoID: PhotoItem.ID) -> GradeSnapshot
}

// 用户意图只通过这一层闭包离开皮肤。预览版全部为空实现；
// Swift 引擎接管后把这里接到渲染、导出和状态存储。
struct SkinActions {
    var openPhoto: (String) -> Void = { _ in }
    var backToLibrary: () -> Void = {}
    var openGrade: () -> Void = {}
    var backToEditor: () -> Void = {}
    var selectFilm: (String) -> Void = { _ in }
    var selectPaper: (String) -> Void = { _ in }
    var selectStripPhoto: (String) -> Void = { _ in }
    var resetParameters: () -> Void = {}
    var exportCurrent: () -> Void = {}
    var exportOptions: () -> Void = {}

    static let preview = SkinActions()
}
