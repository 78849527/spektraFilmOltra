import Foundation

enum Interpolation {
    static func interp1D(image: ImageRGB, xAxis: [Double], yValues: [[Double]]) -> ImageRGB {
        var output = image
        let count = xAxis.count
        guard count >= 2 else { return output }
        var invDX = [Double](repeating: 0, count: count - 1)
        for i in 0..<(count - 1) {
            let dx = xAxis[i + 1] - xAxis[i]
            invDX[i] = dx != 0 ? 1.0 / dx : 0
        }
        for y in 0..<image.height {
            for x in 0..<image.width {
                for c in 0..<3 {
                    let value = image[x, y, c]
                    if value <= xAxis[0] {
                        output[x, y, c] = yValues[0][c]
                    } else if value >= xAxis[count - 1] {
                        output[x, y, c] = yValues[count - 1][c]
                    } else {
                        var idx = 1
                        while idx < count && xAxis[idx] <= value { idx += 1 }
                        let low = idx - 1
                        let t = (value - xAxis[low]) * invDX[low]
                        output[x, y, c] = yValues[low][c] + t * (yValues[low + 1][c] - yValues[low][c])
                    }
                }
            }
        }
        return output
    }

    static func interp1D(image: ImageRGB, xAxisPerChannel: [[Double]], yValues: [[Double]]) -> ImageRGB {
        var output = image
        let count = xAxisPerChannel.count
        guard count >= 2 else { return output }
        var invDX = [[Double]](repeating: [0, 0, 0], count: count - 1)
        for i in 0..<(count - 1) {
            for c in 0..<3 {
                let dx = xAxisPerChannel[i + 1][c] - xAxisPerChannel[i][c]
                invDX[i][c] = dx != 0 ? 1.0 / dx : 0
            }
        }
        for y in 0..<image.height {
            for x in 0..<image.width {
                for c in 0..<3 {
                    let value = image[x, y, c]
                    if value <= xAxisPerChannel[0][c] {
                        output[x, y, c] = yValues[0][c]
                    } else if value >= xAxisPerChannel[count - 1][c] {
                        output[x, y, c] = yValues[count - 1][c]
                    } else {
                        var idx = 1
                        while idx < count && xAxisPerChannel[idx][c] <= value { idx += 1 }
                        let low = idx - 1
                        let t = (value - xAxisPerChannel[low][c]) * invDX[low][c]
                        output[x, y, c] = yValues[low][c] + t * (yValues[low + 1][c] - yValues[low][c])
                    }
                }
            }
        }
        return output
    }
}

struct LUT3D {
    let size: Int
    let values: [Double] // size^3 * 3

    init(size: Int, values: [Double]) {
        self.size = size
        self.values = values
        precondition(values.count == size * size * size * 3)
    }

    subscript(x: Int, y: Int, z: Int, c: Int) -> Double {
        values[((x * size + y) * size + z) * 3 + c]
    }
}

struct PreparedPCHIP3D {
    let lut: LUT3D
    let slopeX: [Double]
    let slopeY: [Double]
    let slopeZ: [Double]
    let cellMin: [Double]
    let cellMax: [Double]
}

enum LUTInterpolation {
    static func fillMonotoneSlopes(_ values: [Double]) -> [Double] {
        let size = values.count
        var slopes = [Double](repeating: 0, count: size)
        if size == 1 { return slopes }
        var deltas = [Double](repeating: 0, count: size - 1)
        for i in 0..<(size - 1) { deltas[i] = values[i + 1] - values[i] }
        if size == 2 {
            slopes[0] = deltas[0]
            slopes[1] = deltas[0]
            return slopes
        }
        var left = 0.5 * (3.0 * deltas[0] - deltas[1])
        if left * deltas[0] <= 0 {
            left = 0
        } else if deltas[0] * deltas[1] < 0 && abs(left) > abs(3.0 * deltas[0]) {
            left = 3.0 * deltas[0]
        }
        slopes[0] = left
        for i in 1..<(size - 1) {
            let previous = deltas[i - 1]
            let next = deltas[i]
            if previous == 0 || next == 0 || previous * next <= 0 {
                slopes[i] = 0
            } else {
                slopes[i] = 2.0 * previous * next / (previous + next)
            }
        }
        var right = 0.5 * (3.0 * deltas[size - 2] - deltas[size - 3])
        if right * deltas[size - 2] <= 0 {
            right = 0
        } else if deltas[size - 2] * deltas[size - 3] < 0 && abs(right) > abs(3.0 * deltas[size - 2]) {
            right = 3.0 * deltas[size - 2]
        }
        slopes[size - 1] = right
        return slopes
    }

    static func preparePCHIP(_ lut: LUT3D) -> PreparedPCHIP3D {
        let size = lut.size
        let valueCount = size * size * size * 3
        var slopeX = [Double](repeating: 0, count: valueCount)
        var slopeY = [Double](repeating: 0, count: valueCount)
        var slopeZ = [Double](repeating: 0, count: valueCount)
        let cellCount = (size - 1) * (size - 1) * (size - 1) * 3
        var cellMin = [Double](repeating: 0, count: cellCount)
        var cellMax = [Double](repeating: 0, count: cellCount)
        let cellStrideC = (size - 1) * (size - 1) * (size - 1)

        for j in 0..<size {
            for k in 0..<size {
                for c in 0..<3 {
                    var line = [Double](repeating: 0, count: size)
                    for i in 0..<size { line[i] = lut[i, j, k, c] }
                    let slopes = fillMonotoneSlopes(line)
                    for i in 0..<size { slopeX[((i * size + j) * size + k) * 3 + c] = slopes[i] }
                }
            }
        }
        for i in 0..<size {
            for k in 0..<size {
                for c in 0..<3 {
                    var line = [Double](repeating: 0, count: size)
                    for j in 0..<size { line[j] = lut[i, j, k, c] }
                    let slopes = fillMonotoneSlopes(line)
                    for j in 0..<size { slopeY[((i * size + j) * size + k) * 3 + c] = slopes[j] }
                }
            }
        }
        for i in 0..<size {
            for j in 0..<size {
                for c in 0..<3 {
                    var line = [Double](repeating: 0, count: size)
                    for k in 0..<size { line[k] = lut[i, j, k, c] }
                    let slopes = fillMonotoneSlopes(line)
                    for k in 0..<size { slopeZ[((i * size + j) * size + k) * 3 + c] = slopes[k] }
                }
            }
        }
        for i in 0..<(size - 1) {
            for j in 0..<(size - 1) {
                for k in 0..<(size - 1) {
                    for c in 0..<3 {
                        var minValue = lut[i, j, k, c]
                        var maxValue = minValue
                        for di in 0...1 {
                            for dj in 0...1 {
                                for dk in 0...1 {
                                    let sample = lut[i + di, j + dj, k + dk, c]
                                    if sample < minValue { minValue = sample }
                                    if sample > maxValue { maxValue = sample }
                                }
                            }
                        }
                        let index = (((i * (size - 1) + j) * (size - 1) + k) * 3) + c
                        cellMin[index] = minValue
                        cellMax[index] = maxValue
                    }
                }
            }
        }
        _ = cellStrideC
        return PreparedPCHIP3D(
            lut: lut, slopeX: slopeX, slopeY: slopeY, slopeZ: slopeZ,
            cellMin: cellMin, cellMax: cellMax
        )
    }

    private static func hermite(_ y0: Double, _ y1: Double, _ m0: Double, _ m1: Double, _ t: Double) -> Double {
        let t2 = t * t
        let t3 = t2 * t
        let h00 = 2 * t3 - 3 * t2 + 1
        let h10 = t3 - 2 * t2 + t
        let h01 = -2 * t3 + 3 * t2
        let h11 = t3 - t2
        return h00 * y0 + h10 * m0 + h01 * y1 + h11 * m1
    }

    private static func mix(_ v0: Double, _ v1: Double, _ t: Double) -> Double {
        v0 + t * (v1 - v0)
    }

    private static func bilinearMix(_ v00: Double, _ v10: Double, _ v01: Double,
                                    _ v11: Double, _ tx: Double, _ ty: Double) -> Double {
        mix(mix(v00, v10, tx), mix(v01, v11, tx), ty)
    }

    private static func clamp(_ value: Double, _ minValue: Double, _ maxValue: Double) -> Double {
        value < minValue ? minValue : (value > maxValue ? maxValue : value)
    }

    static func sample(_ prepared: PreparedPCHIP3D, _ r: Double, _ g: Double, _ b: Double) -> Vec3 {
        let size = prepared.lut.size
        let (i, tr) = SpectralUpsampling.cubicBaseFraction(r, size)
        let (j, tg) = SpectralUpsampling.cubicBaseFraction(g, size)
        let (k, tb) = SpectralUpsampling.cubicBaseFraction(b, size)
        var out = Vec3(0, 0, 0)
        let cellBase = (((i * (size - 1) + j) * (size - 1) + k) * 3)
        for c in 0..<3 {
            let v000 = hermite(prepared.lut[i, j, k, c], prepared.lut[i + 1, j, k, c],
                               prepared.slopeX[stride(i, j, k, c, size)],
                               prepared.slopeX[stride(i + 1, j, k, c, size)], tr)
            let v010 = hermite(prepared.lut[i, j + 1, k, c], prepared.lut[i + 1, j + 1, k, c],
                               prepared.slopeX[stride(i, j + 1, k, c, size)],
                               prepared.slopeX[stride(i + 1, j + 1, k, c, size)], tr)
            let v001 = hermite(prepared.lut[i, j, k + 1, c], prepared.lut[i + 1, j, k + 1, c],
                               prepared.slopeX[stride(i, j, k + 1, c, size)],
                               prepared.slopeX[stride(i + 1, j, k + 1, c, size)], tr)
            let v011 = hermite(prepared.lut[i, j + 1, k + 1, c], prepared.lut[i + 1, j + 1, k + 1, c],
                               prepared.slopeX[stride(i, j + 1, k + 1, c, size)],
                               prepared.slopeX[stride(i + 1, j + 1, k + 1, c, size)], tr)

            let sy00 = mix(prepared.slopeY[stride(i, j, k, c, size)],
                           prepared.slopeY[stride(i + 1, j, k, c, size)], tr)
            let sy10 = mix(prepared.slopeY[stride(i, j + 1, k, c, size)],
                           prepared.slopeY[stride(i + 1, j + 1, k, c, size)], tr)
            let sy01 = mix(prepared.slopeY[stride(i, j, k + 1, c, size)],
                           prepared.slopeY[stride(i + 1, j, k + 1, c, size)], tr)
            let sy11 = mix(prepared.slopeY[stride(i, j + 1, k + 1, c, size)],
                           prepared.slopeY[stride(i + 1, j + 1, k + 1, c, size)], tr)

            let vz0 = hermite(v000, v010, sy00, sy10, tg)
            let vz1 = hermite(v001, v011, sy01, sy11, tg)

            let sz0 = bilinearMix(prepared.slopeZ[stride(i, j, k, c, size)],
                                  prepared.slopeZ[stride(i + 1, j, k, c, size)],
                                  prepared.slopeZ[stride(i, j + 1, k, c, size)],
                                  prepared.slopeZ[stride(i + 1, j + 1, k, c, size)], tr, tg)
            let sz1 = bilinearMix(prepared.slopeZ[stride(i, j, k + 1, c, size)],
                                  prepared.slopeZ[stride(i + 1, j, k + 1, c, size)],
                                  prepared.slopeZ[stride(i, j + 1, k + 1, c, size)],
                                  prepared.slopeZ[stride(i + 1, j + 1, k + 1, c, size)], tr, tg)

            let interpolated = hermite(vz0, vz1, sz0, sz1, tb)
            let cellIndex = cellBase + c
            out[c] = clamp(interpolated, prepared.cellMin[cellIndex], prepared.cellMax[cellIndex])
        }
        return out
    }

    private static func stride(_ x: Int, _ y: Int, _ z: Int, _ c: Int, _ size: Int) -> Int {
        ((x * size + y) * size + z) * 3 + c
    }

    static func applyPCHIP(_ prepared: PreparedPCHIP3D, image: ImageRGB) -> ImageRGB {
        var output = image
        let scale = Double(prepared.lut.size - 1)
        for y in 0..<image.height {
            for x in 0..<image.width {
                let r = image[x, y, 0] * scale
                let g = image[x, y, 1] * scale
                let b = image[x, y, 2] * scale
                output.setPixel(x, y, sample(prepared, r, g, b))
            }
        }
        return output
    }
}

