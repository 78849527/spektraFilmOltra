import Foundation

enum MColorLabel: String, CaseIterable, Identifiable, Hashable {
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

struct MPhoto: Identifiable, Hashable {
    let id: String
    let filename: String
    let film: String
    let paper: String
    let dimensions: String
    let isRaw: Bool
    let favorite: Bool
    let color: MColorLabel?
    let isGraded: Bool
    let exposure: String
    let thumbnailURL: URL?

    var metaLine: String {
        [film, dimensions].joined(separator: " · ")
    }

    var aspectRatio: CGFloat {
        let parts = dimensions.split(separator: "×").compactMap { Double($0) }
        guard parts.count == 2, parts[1] > 0 else { return 4.0 / 3.0 }
        return CGFloat(parts[0] / parts[1])
    }
}

struct MFilm: Identifiable, Hashable {
    let id: String
    let name: String
    let brand: String
    let kind: String
    let hue: Double
    let saturation: Double
    let brightness: Double
}

struct MPaper: Identifiable, Hashable {
    let id: String
    let name: String
    let brand: String
    let warmth: Double
    let note: String
}

struct MQuickAxis: Identifiable, Hashable {
    let id: String
    let label: String
    let group: String
    let range: ClosedRange<Double>
    let step: Double
    let decimals: Int
    let suffix: String
    let base: Double
    var value: Double

    var isDirty: Bool { abs(value - base) > 1e-9 }

    func text(for value: Double) -> String {
        let zeroCutoff = pow(10, Double(-decimals)) * 0.5
        let normalized = abs(value) < zeroCutoff ? 0 : value
        var text = String(format: "%.\(decimals)f", normalized)
        if decimals > 0, text.contains(".") {
            while text.hasSuffix("0") { text.removeLast() }
            if text.hasSuffix(".") { text.removeLast() }
        }
        if range.lowerBound < 0, normalized > 0 { text = "+" + text }
        return text + suffix
    }
}

struct MQuickGroup: Identifiable, Hashable {
    let id: String
    let title: String
    var axes: [MQuickAxis]
}

enum MProControl: Hashable {
    case slider(value: Double, base: Double, range: ClosedRange<Double>, step: Double, decimals: Int, suffix: String)
    case toggle(isOn: Bool)
    case choice(text: String)
}

struct MProRow: Identifiable, Hashable {
    let id: String
    let label: String
    let control: MProControl
}

struct MProGroup: Identifiable, Hashable {
    let id: String
    let title: String
    let rows: [MProRow]
}

struct MProPage: Identifiable, Hashable {
    let id: String
    let title: String
    let groups: [MProGroup]
}

struct MLUT: Identifiable, Hashable {
    let id: String
    let name: String
    let meta: String
    let tints: [UInt32]
}

enum MGradeTab: String, CaseIterable, Identifiable {
    case presets, adjust, curve
    var id: String { rawValue }
    var title: String {
        switch self {
        case .presets: return "预设"
        case .adjust: return "调整"
        case .curve: return "曲线"
        }
    }
}

struct MGradeRecipe: Equatable {
    var exposure: Double = 0
    var contrast: Double = 0
    var highlights: Double = 0
    var shadows: Double = 0
    var temperature: Double = 0
    var tint: Double = 0
    var lutName: String = "无 LUT"
    var lutStrength: Double = 0
    var curveHighlights: Double = 0
    var curveLights: Double = 0
    var curveDarks: Double = 0
    var curveShadows: Double = 0

    /// 视图模型 → 调色引擎配方。只写既有字段，不新增算法。
    func gradeRecipe(lutPath: String) -> GradeRecipe {
        var recipe = GradeRecipe()
        recipe.light.exposure = exposure
        recipe.light.contrast = contrast
        recipe.light.highlights = highlights
        recipe.light.shadows = shadows
        recipe.light.curveHighlights = curveHighlights
        recipe.light.curveLights = curveLights
        recipe.light.curveDarks = curveDarks
        recipe.light.curveShadows = curveShadows
        recipe.color.temperature = temperature
        recipe.color.tint = tint
        recipe.lut.path = lutPath
        recipe.lut.strength = lutStrength
        return recipe
    }

    /// 引擎配方 → 视图模型。
    init(grade: GradeRecipe, lutName: String) {
        exposure = grade.light.exposure
        contrast = grade.light.contrast
        highlights = grade.light.highlights
        shadows = grade.light.shadows
        curveHighlights = grade.light.curveHighlights
        curveLights = grade.light.curveLights
        curveDarks = grade.light.curveDarks
        curveShadows = grade.light.curveShadows
        temperature = grade.color.temperature
        tint = grade.color.tint
        self.lutName = lutName
        lutStrength = grade.lut.strength
    }

    init() {}
}

enum MScreen: Hashable {
    case home
    case develop
    case grade
}

enum MGradeEntry: Hashable {
    case handoff
    case direct
}
