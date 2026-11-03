import Foundation

enum AutoExposure {
    static func measureEV(image: ImageRGB, colorSpace: String, applyCCTFDecoding: Bool,
                          method: String) -> Double {
        var luminance = [Double](repeating: 0, count: image.width * image.height)
        for p in 0..<(image.width * image.height) {
            let rgb = Vec3(image.data[p * 3], image.data[p * 3 + 1], image.data[p * 3 + 2])
            let xyz = ColorMath.rgbToXYZ(rgb, spaceName: colorSpace, applyCCTFDecoding: applyCCTFDecoding)
            luminance[p] = xyz.y
        }
        var exposure = 1.0
        switch method {
        case "average":
            exposure = luminance.reduce(0, +) / Double(luminance.count) / 0.184
        case "median":
            let sorted = luminance.sorted()
            let mid = sorted.count / 2
            let median = sorted.count % 2 == 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
            exposure = median / 0.184
        case "center_weighted":
            let (x, y) = normalizedCoordinates(image)
            var weighted = 0.0
            var total = 0.0
            let sigma = 0.2
            for row in 0..<image.height {
                for col in 0..<image.width {
                    let mask = exp(-(x[col] * x[col] + y[row] * y[row]) / (2 * sigma * sigma))
                    weighted += luminance[row * image.width + col] * mask
                    total += mask
                }
            }
            exposure = (weighted / max(total, 1e-20)) / 0.184
        case "partial":
            let (x, y) = normalizedCoordinates(image)
            var values: [Double] = []
            for row in 0..<image.height {
                for col in 0..<image.width {
                    let radius = sqrt(x[col] * x[col] + y[row] * y[row])
                    if radius < 0.15 { values.append(luminance[row * image.width + col]) }
                }
            }
            if values.isEmpty { values = luminance }
            exposure = values.reduce(0, +) / Double(values.count) / 0.184
        case "matrix":
            let rows = 5
            let cols = 5
            let cellH = image.height / rows
            let cellW = image.width / cols
            var means: [Double] = []
            var weights: [Double] = []
            for r in 0..<rows {
                for c in 0..<cols {
                    var sum = 0.0
                    var count = 0
                    for yy in (r * cellH)..<min((r + 1) * cellH, image.height) {
                        for xx in (c * cellW)..<min((c + 1) * cellW, image.width) {
                            sum += luminance[yy * image.width + xx]
                            count += 1
                        }
                    }
                    if count == 0 { continue }
                    means.append(sum / Double(count))
                    let dy = (Double(r) - Double(rows - 1) / 2) / (Double(rows - 1) / 2)
                    let dx = (Double(c) - Double(cols - 1) / 2) / (Double(cols - 1) / 2)
                    let distance = sqrt(dx * dx + dy * dy) / sqrt(2)
                    weights.append(0.5 * (1 + cos(.pi * distance)))
                }
            }
            let weightSum = max(weights.reduce(0, +), 1e-20)
            exposure = zip(weights, means).reduce(0) { $0 + $1.0 * $1.1 } / weightSum / 0.184
        case "multi_zone":
            let (x, y) = normalizedCoordinates(image)
            let rings: [(Double, Double, Double)] = [(0, 0.05, 0.5), (0.05, 0.25, 0.3), (0.25, 0.5, 0.2)]
            var weighted = 0.0
            var total = 0.0
            for (low, high, weight) in rings {
                var values: [Double] = []
                for row in 0..<image.height {
                    for col in 0..<image.width {
                        let radius = sqrt(x[col] * x[col] + y[row] * y[row])
                        if radius >= low && radius < high { values.append(luminance[row * image.width + col]) }
                    }
                }
                if values.isEmpty { continue }
                weighted += weight * (values.reduce(0, +) / Double(values.count))
                total += weight
            }
            exposure = (total > 0 ? weighted / total : luminance.reduce(0, +) / Double(luminance.count)) / 0.184
        case "highlight_weighted":
            var weighted = 0.0
            var total = 0.0
            for value in luminance {
                let weight = value * value
                weighted += value * weight
                total += weight
            }
            if total < 1e-12 {
                exposure = luminance.reduce(0, +) / Double(luminance.count) / 0.184
            } else {
                exposure = weighted / total / 0.184
            }
        default:
            exposure = 1
        }
        let ev = -log2(exposure)
        return ev.isFinite ? ev : 0
    }

    private static func normalizedCoordinates(_ image: ImageRGB) -> ([Double], [Double]) {
        let normH = Double(image.height) / Double(max(image.width, image.height))
        let normW = Double(image.width) / Double(max(image.width, image.height))
        let x = (0..<image.width).map { (Double($0) / Double(image.width) - 0.5) * normW }
        let y = (0..<image.height).map { (Double($0) / Double(image.height) - 0.5) * normH }
        return (x, y)
    }
}

enum Resize {
    static func smallPreview(_ image: ImageRGB, maxSize: Int = 256) -> ImageRGB {
        let longEdge = max(image.width, image.height)
        guard longEdge > maxSize else { return image }
        let scale = Double(maxSize) / Double(longEdge)
        let width = max(1, Int(round(Double(image.width) * scale)))
        let height = max(1, Int(round(Double(image.height) * scale)))
        var output = ImageRGB(width: width, height: height)
        for y in 0..<height {
            let sourceY = min(image.height - 1, Int(Double(y) / scale))
            for x in 0..<width {
                let sourceX = min(image.width - 1, Int(Double(x) / scale))
                output.setPixel(x, y, image.pixel(sourceX, sourceY))
            }
        }
        return output
    }

    static func crop(_ image: ImageRGB, center: [Double], size: [Double]) -> ImageRGB {
        let shape = (Double(image.height), Double(image.width))
        let centerNormalized = (center[1], center[0])
        let sizeNormalized = (size[1], size[0])
        var cn = (round(shape.0 * centerNormalized.0), round(shape.1 * centerNormalized.1))
        var sz = (round(max(shape.0, shape.1) * sizeNormalized.0), round(max(shape.0, shape.1) * sizeNormalized.1))
        var x0 = (round(cn.0 - sz.0 / 2), round(cn.1 - sz.1 / 2))
        x0.0 = max(x0.0, 0)
        x0.1 = max(x0.1, 0)
        if x0.0 + sz.0 > shape.0 { x0.0 = shape.0 - sz.0 }
        if x0.1 + sz.1 > shape.1 { x0.1 = shape.1 - sz.1 }
        sz.0 = max(sz.0, 1)
        sz.1 = max(sz.1, 1)
        let width = Int(sz.1)
        let height = Int(sz.0)
        var output = ImageRGB(width: width, height: height)
        for y in 0..<height {
            for x in 0..<width {
                output.setPixel(x, y, image.pixel(Int(x0.1) + x, Int(x0.0) + y))
            }
        }
        return output
    }
}

