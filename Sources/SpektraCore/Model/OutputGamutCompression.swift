import Foundation

/// 输出色域压缩：把超出输出 RGB 立方体的色度沿感知色度轴收回到 [0,1]。
/// 对应 Python `utils/gamut_compression.py` 的输出侧实现。
enum OutputGamutCompression {
    static let nL = 64
    static let nH = 720
    static let nBisect = 18
    static let defaultLightness: [Double] = [0.7, 1.0, 2.2]

    struct CMaxTable {
        let lGrid: [Double]
        let hGrid: [Double]
        let values: [Double] // [L][h]
    }

    static func reinhardKnee(_ d: Double, threshold: Double, limit: Double, power: Double) -> Double {
        if d <= threshold { return d }
        let scale = limit - threshold
        let x = (d - threshold) / scale
        let y = x / pow(1 + pow(x, power), 1 / power)
        return threshold + scale * y
    }

    static func compressLightness(_ value: Double, params: [Double], white: Double) -> Double {
        let threshold = params[0]
        let limit = params[1]
        let power = params[2]
        let normalized = value / white
        let compressed = reinhardKnee(normalized, threshold: threshold, limit: limit, power: power)
        return compressed * white
    }

    static func cMaxLookup(_ table: CMaxTable, l: Double, h: Double) -> Double {
        guard l.isFinite, h.isFinite else { return 0 }
        let lGrid = table.lGrid
        let hGrid = table.hGrid
        let clampedL = min(max(l, lGrid[0]), lGrid[lGrid.count - 1])
        let hStep = hGrid[1] - hGrid[0]
        let hIndex = (h - hGrid[0]) / hStep
        let hFloor = floor(hIndex)
        guard hFloor.isFinite else { return 0 }
        var hLow = Int(hFloor) % hGrid.count
        if hLow < 0 { hLow += hGrid.count }
        let hHigh = (hLow + 1) % hGrid.count
        let hFraction = hIndex - hFloor

        let lIndex = (clampedL - lGrid[0]) / (lGrid[lGrid.count - 1] - lGrid[0]) * Double(lGrid.count - 1)
        guard lIndex.isFinite else { return 0 }
        let lLow = min(max(Int(floor(lIndex)), 0), lGrid.count - 2)
        let lHigh = lLow + 1
        let lFraction = lIndex - Double(lLow)

        let v00 = table.values[lLow * hGrid.count + hLow]
        let v01 = table.values[lLow * hGrid.count + hHigh]
        let v10 = table.values[lHigh * hGrid.count + hLow]
        let v11 = table.values[lHigh * hGrid.count + hHigh]
        return v00 * (1 - lFraction) * (1 - hFraction)
            + v01 * (1 - lFraction) * hFraction
            + v10 * lFraction * (1 - hFraction)
            + v11 * lFraction * hFraction
    }

    static func buildTable(spaceName: String, kind: String,
                           lRange: (Double, Double), chromaUpper: Double,
                           polarToXYZUnit: (Vec3) -> Vec3) -> CMaxTable {
        let space = ColorDataStore.shared.spaces[spaceName]!
        var lGrid = [Double](repeating: 0, count: nL)
        for i in 0..<nL {
            lGrid[i] = lRange.0 + (lRange.1 - lRange.0) * Double(i) / Double(nL - 1)
        }
        var hGrid = [Double](repeating: 0, count: nH)
        for i in 0..<nH {
            hGrid[i] = -Double.pi + 2 * Double.pi * Double(i) / Double(nH)
        }
        var values = [Double](repeating: 0, count: nL * nH)
        var low = [Double](repeating: 0, count: nL * nH)
        var high = [Double](repeating: chromaUpper, count: nL * nH)
        for _ in 0..<nBisect {
            for li in 0..<nL {
                for hi in 0..<nH {
                    let index = li * nH + hi
                    let mid = (low[index] + high[index]) * 0.5
                    let h = hGrid[hi]
                    let lab = Vec3(lGrid[li], mid * cos(h), mid * sin(h))
                    let xyz = polarToXYZUnit(lab)
                    let rgb = space.fromXYZ.apply(xyz)
                    let inGamut = rgb.x >= -1e-6 && rgb.x <= 1 + 1e-6
                        && rgb.y >= -1e-6 && rgb.y <= 1 + 1e-6
                        && rgb.z >= -1e-6 && rgb.z <= 1 + 1e-6
                    if inGamut { low[index] = mid } else { high[index] = mid }
                }
            }
        }
        for i in 0..<values.count { values[i] = low[i] }
        return CMaxTable(lGrid: lGrid, hGrid: hGrid, values: values)
    }

    static let oklabMatrix1 = Mat3(rows: [
        [0.8189330101, 0.3618667424, -0.1288597137],
        [0.0329845436, 0.9293118715, 0.0361456387],
        [0.0482003018, 0.2643662691, 0.6338517070],
    ])
    static let oklabMatrix2 = Mat3(rows: [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ])
    static let oklabMatrix2Inverse = oklabMatrix2.inverted()
    static let oklabMatrix1Inverse = oklabMatrix1.inverted()

    static let oklrabK1 = 0.206
    static let oklrabK2 = 0.03
    static let oklrabK3 = (1.0 + 0.206) / (1.0 + 0.03)

    static func xyzToOklab(_ xyz: Vec3) -> Vec3 {
        let lms = oklabMatrix1.apply(xyz)
        let root = Vec3(
            CAM16UCS.spow(lms.x, 1.0 / 3.0),
            CAM16UCS.spow(lms.y, 1.0 / 3.0),
            CAM16UCS.spow(lms.z, 1.0 / 3.0)
        )
        return oklabMatrix2.apply(root)
    }

    static func oklabToXYZ(_ lab: Vec3) -> Vec3 {
        let root = oklabMatrix2Inverse.apply(lab)
        let lms = Vec3(
            CAM16UCS.spow(root.x, 3),
            CAM16UCS.spow(root.y, 3),
            CAM16UCS.spow(root.z, 3)
        )
        return oklabMatrix1Inverse.apply(lms)
    }

    static func oklrabLRToOklabL(_ lr: Double) -> Double {
        (lr * (lr + oklrabK1)) / (oklrabK3 * (lr + oklrabK2))
    }

    static func oklabLToOklrabLR(_ l: Double) -> Double {
        let t = oklrabK3 * l - oklrabK1
        return 0.5 * (t + sqrt(t * t + 4 * oklrabK2 * oklrabK3 * l))
    }

    static var tableCache: [String: CMaxTable] = [:]

    static func table(for kind: String, spaceName: String) -> CMaxTable? {
        let key = "\(kind)|\(spaceName)"
        if let cached = tableCache[key] { return cached }
        guard let space = ColorDataStore.shared.spaces[spaceName] else { return nil }
        let white = space.whitepoint
        let table: CMaxTable
        switch kind {
        case "cam16ucs":
            let setup = CAM16UCS.setup(whiteXYZ: white)
            table = buildTable(
                spaceName: spaceName, kind: kind, lRange: (1.0, 110.0), chromaUpper: 150.0,
                polarToXYZUnit: { CAM16UCS.jabToXYZ($0, setup: setup) }
            )
        case "oklch":
            table = buildTable(
                spaceName: spaceName, kind: kind, lRange: (0.02, 1.0), chromaUpper: 0.5,
                polarToXYZUnit: { oklabToXYZ($0) }
            )
        case "oklrab":
            table = buildTable(
                spaceName: spaceName, kind: kind, lRange: (0.02, 1.0), chromaUpper: 0.5,
                polarToXYZUnit: { lab in
                    oklabToXYZ(Vec3(oklrabLRToOklabL(lab.x), lab.y, lab.z))
                }
            )
        case "jzazbz":
            table = buildTable(
                spaceName: spaceName, kind: kind, lRange: (0.002, 0.18), chromaUpper: 0.3,
                polarToXYZUnit: { JzAzBz.jzazbzToXYZ($0) }
            )
        default:
            return nil
        }
        tableCache[key] = table
        return table
    }

    static func whiteLevel(kind: String, spaceName: String) -> Double {
        guard let space = ColorDataStore.shared.spaces[spaceName] else { return 1.0 }
        switch kind {
        case "cam16ucs":
            return CAM16UCS.setup(whiteXYZ: space.whitepoint).jpWhite
        case "oklch", "oklrab":
            return 1.0
        case "jzazbz":
            return JzAzBz.xyzToJzazbz(space.whitepoint).x
        default:
            return 1.0
        }
    }

    static func apply(_ image: ImageRGB, algorithm: String, knee: [Double],
                      outputColorSpace: String) -> ImageRGB {
        if algorithm == "off" { return image }
        let threshold = knee.count > 0 ? knee[0] : 0.0
        let limit = knee.count > 1 ? knee[1] : 1.0
        let power = knee.count > 2 ? knee[2] : 6.0

        if algorithm == "aces_rgc" {
            var output = image
            for i in 0..<(image.width * image.height) {
                let r = image.data[i * 3]
                let g = image.data[i * 3 + 1]
                let b = image.data[i * 3 + 2]
                guard r.isFinite, g.isFinite, b.isFinite else {
                    output.data[i * 3] = 0
                    output.data[i * 3 + 1] = 0
                    output.data[i * 3 + 2] = 0
                    continue
                }
                let achromatic = max(r, max(g, b))
                if achromatic <= 1e-12 {
                    continue
                }
                for c in 0..<3 {
                    let value = image.data[i * 3 + c]
                    let distance = (achromatic - value) / achromatic
                    let compressed = reinhardKnee(distance, threshold: threshold, limit: limit, power: power)
                    output.data[i * 3 + c] = achromatic * (1 - compressed)
                }
            }
            return output
        }

        guard let space = ColorDataStore.shared.spaces[outputColorSpace],
              let table = table(for: algorithm, spaceName: outputColorSpace) else {
            return image
        }
        let white = space.whitepoint
        let whiteLevelValue = whiteLevel(kind: algorithm, spaceName: outputColorSpace)
        let setup = algorithm == "cam16ucs" ? CAM16UCS.setup(whiteXYZ: white) : nil

        var output = image
        for i in 0..<(image.width * image.height) {
            let rgb = Vec3(image.data[i * 3], image.data[i * 3 + 1], image.data[i * 3 + 2])
            guard rgb.x.isFinite, rgb.y.isFinite, rgb.z.isFinite else {
                output.data[i * 3] = 0
                output.data[i * 3 + 1] = 0
                output.data[i * 3 + 2] = 0
                continue
            }
            let xyz = space.toXYZ.apply(rgb)
            guard xyz.x.isFinite, xyz.y.isFinite, xyz.z.isFinite else {
                output.data[i * 3] = 0
                output.data[i * 3 + 1] = 0
                output.data[i * 3 + 2] = 0
                continue
            }
            var lightness: Double
            var a: Double
            var b: Double
            if algorithm == "cam16ucs" {
                let jab = CAM16UCS.xyzToJab(xyz, setup: setup!)
                lightness = jab.x
                a = jab.y
                b = jab.z
            } else if algorithm == "jzazbz" {
                let jab = JzAzBz.xyzToJzazbz(xyz)
                lightness = jab.x
                a = jab.y
                b = jab.z
            } else {
                let lab = xyzToOklab(xyz)
                lightness = lab.x
                a = lab.y
                b = lab.z
            }
            guard lightness.isFinite, a.isFinite, b.isFinite else {
                output.data[i * 3] = 0
                output.data[i * 3 + 1] = 0
                output.data[i * 3 + 2] = 0
                continue
            }
            lightness = compressLightness(lightness, params: defaultLightness, white: whiteLevelValue)
            if algorithm == "oklrab" { lightness = oklabLToOklrabLR(lightness) }
            let chroma = sqrt(a * a + b * b)
            let hue = atan2(b, a)
            guard lightness.isFinite, chroma.isFinite, hue.isFinite else {
                output.data[i * 3] = 0
                output.data[i * 3 + 1] = 0
                output.data[i * 3 + 2] = 0
                continue
            }
            let cMax = max(cMaxLookup(table, l: lightness, h: hue), 1e-9)
            let compressed = reinhardKnee(chroma / cMax, threshold: threshold, limit: limit, power: power)
            let newChroma = compressed * cMax
            let newA = newChroma * cos(hue)
            let newB = newChroma * sin(hue)
            let xyzNew: Vec3
            if algorithm == "cam16ucs" {
                xyzNew = CAM16UCS.jabToXYZ(Vec3(lightness, newA, newB), setup: setup!)
            } else if algorithm == "jzazbz" {
                xyzNew = JzAzBz.jzazbzToXYZ(Vec3(lightness, newA, newB))
            } else {
                let labL = algorithm == "oklrab" ? oklrabLRToOklabL(lightness) : lightness
                xyzNew = oklabToXYZ(Vec3(labL, newA, newB))
            }
            let rgbNew = space.fromXYZ.apply(xyzNew)
            if rgbNew.x.isFinite, rgbNew.y.isFinite, rgbNew.z.isFinite {
                output.data[i * 3] = rgbNew.x
                output.data[i * 3 + 1] = rgbNew.y
                output.data[i * 3 + 2] = rgbNew.z
            } else {
                output.data[i * 3] = 0
                output.data[i * 3 + 1] = 0
                output.data[i * 3 + 2] = 0
            }
        }
        return output
    }
}
