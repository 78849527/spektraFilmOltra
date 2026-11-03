import Foundation

/// 颗粒模型：逐层粒子显影统计 + 染料云模糊 + 微结构调制。
/// 逐行对应 Python `model/grain.py`；随机数只要求分布同构。
enum Grain {
    static func maxPerChannel(_ curves: [[Double]]) -> [Double] {
        var result = [Double](repeating: -.infinity, count: 3)
        for row in curves {
            for c in 0..<min(3, row.count) where row[c].isFinite { result[c] = max(result[c], row[c]) }
        }
        return result
    }

    static func maxLayers(_ layers: [[[Double]]]) -> [[Double]] {
        guard let first = layers.first else { return [] }
        let layerCount = first.count
        var result = [[Double]](repeating: [Double](repeating: -.infinity, count: 3), count: layerCount)
        for point in layers {
            for layer in 0..<min(layerCount, point.count) {
                for c in 0..<min(3, point[layer].count) where point[layer][c].isFinite {
                    result[layer][c] = max(result[layer][c], point[layer][c])
                }
            }
        }
        return result
    }

    /// 与 numpy `searchsorted(side='right')` 一致的 1D 线性插值。
    static func interpValue(_ x: Double, xp: [Double], yp: [Double]) -> Double {
        let count = xp.count
        guard count > 0, yp.count == count else { return .nan }
        if count == 1 { return yp[0] }
        if x <= xp[0] { return yp[0] }
        if x >= xp[count - 1] { return yp[count - 1] }
        var low = 0
        var high = count - 1
        while low < high {
            let mid = (low + high) / 2
            if xp[mid] <= x { low = mid + 1 } else { high = mid }
        }
        let index = low - 1
        if index < 0 { return yp[0] }
        if index >= count - 1 { return yp[count - 1] }
        let dx = xp[index + 1] - xp[index]
        let inv = dx != 0 ? 1.0 / dx : 0.0
        return yp[index] + (x - xp[index]) * inv * (yp[index + 1] - yp[index])
    }

    static func layerParticleModel(density: [Double], densityMax: Double,
                                   nParticlesPerPixel: Double, grainUniformity: Double,
                                   seed: UInt64, blurParticle: Double,
                                   width: Int, height: Int) -> [Double] {
        guard densityMax > 0, nParticlesPerPixel > 0 else { return [Double](repeating: 0, count: density.count) }
        var rng = SplitMix64(seed: seed)
        let odParticle = densityMax / nParticlesPerPixel
        var output = [Double](repeating: 0, count: density.count)
        for i in 0..<density.count {
            var probability = density[i] / densityMax
            if !probability.isFinite { probability = 0 }
            probability = min(max(probability, 1e-6), 1 - 1e-6)
            let saturation = 1 - probability * grainUniformity * (1 - 1e-6)
            let seeds = RandomStats.poisson(nParticlesPerPixel / saturation, &rng)
            let developed = RandomStats.binomial(seeds, probability, &rng)
            output[i] = Double(developed) * odParticle * saturation
        }
        if blurParticle > 0 {
            let sigma = blurParticle * sqrt(odParticle)
            output = FastGaussian.filterChannel(output, width: width, height: height, sigma: sigma)
        }
        return output
    }

    /// 对齐 numpy `(x, y, layer, rgb)` 的逐层密度插值。
    static func interpDensityCMYLayers(densityCMY: ImageRGB, densityCurves: [[Double]],
                                       densityCurvesLayers: [[[Double]]],
                                       positive: Bool) -> [[[Double]]] {
        let pixelCount = densityCMY.width * densityCMY.height
        let layerCount = densityCurvesLayers.first?.count ?? 0
        var result = [[[Double]]](repeating: [[Double]](repeating: [0, 0, 0], count: layerCount),
                                  count: pixelCount)
        guard layerCount > 0 else { return result }
        for c in 0..<3 {
            let curveColumn = densityCurves.indices.map { densityCurves[$0][c] }
            let sign: Double = positive ? -1 : 1
            for layer in 0..<layerCount {
                let layerColumn = densityCurvesLayers.indices.map { densityCurvesLayers[$0][layer][c] }
                let xp = sign == -1 ? curveColumn.map { -$0 } : curveColumn
                let yp = sign == -1 ? layerColumn.map { -$0 } : layerColumn
                for p in 0..<pixelCount {
                    let value = sign == -1 ? -densityCMY.data[p * 3 + c] : densityCMY.data[p * 3 + c]
                    let interpolated = interpValue(value, xp: xp, yp: yp)
                    result[p][layer][c] = sign == -1 ? -interpolated : interpolated
                }
            }
        }
        return result
    }

    static func applyToDensityLayers(densityCMY: ImageRGB, pixelSizeUM: Double, params: GrainParams,
                                     densityCurves: [[Double]], densityCurvesLayers: [[[Double]]],
                                     positive: Bool) -> ImageRGB {
        let width = densityCMY.width
        let height = densityCMY.height
        let pixelCount = width * height
        let layerCount = densityCurvesLayers.first?.count ?? 0
        guard layerCount > 0 else { return densityCMY }

        let densityMaxLayers = maxLayers(densityCurvesLayers)
        var densityMaxTotal = [Double](repeating: 0, count: 3)
        for layer in 0..<layerCount {
            for c in 0..<3 { densityMaxTotal[c] += densityMaxLayers[layer][c] }
        }
        var fractions = [[Double]](repeating: [0, 0, 0], count: layerCount)
        var minLayers = [[Double]](repeating: [0, 0, 0], count: layerCount)
        for layer in 0..<layerCount {
            for c in 0..<3 {
                fractions[layer][c] = densityMaxLayers[layer][c] / densityMaxTotal[c]
                minLayers[layer][c] = fractions[layer][c] * params.densityMin[c]
            }
        }
        let pixelArea = pixelSizeUM * pixelSizeUM
        var particlesPerPixel = [[Double]](repeating: [0, 0, 0], count: layerCount)
        for layer in 0..<layerCount {
            for c in 0..<3 {
                let area = params.particleAreaUM2 * params.particleScale[c] * params.particleScaleLayers[layer]
                particlesPerPixel[layer][c] = pixelArea * fractions[layer][c] / area
            }
        }

        var output = ImageRGB(width: width, height: height)
        for c in 0..<3 {
            let curveColumn = densityCurves.indices.map { densityCurves[$0][c] }
            let sign: Double = positive ? -1 : 1
            let xp = sign == -1 ? curveColumn.map { -$0 } : curveColumn
            for layer in 0..<layerCount {
                let layerColumn = densityCurvesLayers.indices.map { densityCurvesLayers[$0][layer][c] }
                let yp = sign == -1 ? layerColumn.map { -$0 } : layerColumn
                var plane = [Double](repeating: 0, count: pixelCount)
                for p in 0..<pixelCount {
                    let value = sign == -1 ? -densityCMY.data[p * 3 + c] : densityCMY.data[p * 3 + c]
                    let interpolated = interpValue(value, xp: xp, yp: yp)
                    plane[p] = (sign == -1 ? -interpolated : interpolated) + minLayers[layer][c]
                }
                let seed = UInt64(c + layer * 10)
                let modelled = layerParticleModel(
                    density: plane,
                    densityMax: densityMaxLayers[layer][c],
                    nParticlesPerPixel: particlesPerPixel[layer][c],
                    grainUniformity: params.uniformity[c],
                    seed: seed,
                    blurParticle: params.blurDyeCloudsUM,
                    width: width, height: height
                )
                for p in 0..<pixelCount { output.data[p * 3 + c] += modelled[p] }
            }
        }

        addMicroStructure(&output, micro: params.microStructure, pixelSizeUM: pixelSizeUM)
        for c in 0..<3 {
            for p in 0..<pixelCount { output.data[p * 3 + c] -= params.densityMin[c] }
        }
        if params.blur > 0 {
            output = FastGaussian.filter(output, sigma: params.blur)
        }
        return output
    }

    static func addMicroStructure(_ density: inout ImageRGB, micro: [Double], pixelSizeUM: Double) {
        guard micro.count >= 2, pixelSizeUM > 0 else { return }
        let blurPixels = micro[0] / pixelSizeUM
        let sigma = micro[1] * 0.001 / pixelSizeUM
        guard sigma > 0.05 else { return }
        let pixelCount = density.width * density.height
        var rng = SplitMix64(seed: 7)
        var clumping = [Double](repeating: 0, count: pixelCount)
        for p in 0..<pixelCount {
            clumping[p] = RandomStats.lognormalFromMeanStd(1.0, sigma, &rng)
        }
        if blurPixels > 0.4 {
            clumping = FastGaussian.filterChannel(clumping, width: density.width, height: density.height, sigma: blurPixels)
        }
        for c in 0..<3 {
            for p in 0..<pixelCount { density.data[p * 3 + c] *= clumping[p] }
        }
    }

    static func applyToDensity(densityCMY: ImageRGB, pixelSizeUM: Double, params: GrainParams,
                               densityCurves: [[Double]]) -> ImageRGB {
        let densityMaxCurves = maxPerChannel(densityCurves)
        let pixelArea = pixelSizeUM * pixelSizeUM
        let subLayers = max(params.nSubLayers, 1)
        var densityMax = [Double](repeating: 0, count: 3)
        var particles = [Double](repeating: 0, count: 3)
        for c in 0..<3 {
            densityMax[c] = densityMaxCurves[c] + params.densityMin[c]
            let area = params.particleAreaUM2 * params.particleScale[c]
            particles[c] = pixelArea / area / Double(subLayers)
        }
        let width = densityCMY.width
        let height = densityCMY.height
        let pixelCount = width * height
        var working = densityCMY
        for c in 0..<3 {
            for p in 0..<pixelCount { working.data[p * 3 + c] += params.densityMin[c] }
        }
        var output = ImageRGB(width: width, height: height)
        for c in 0..<3 {
            var plane = [Double](repeating: 0, count: pixelCount)
            for p in 0..<pixelCount { plane[p] = working.data[p * 3 + c] }
            for sub in 0..<subLayers {
                let modelled = layerParticleModel(
                    density: plane, densityMax: densityMax[c],
                    nParticlesPerPixel: particles[c], grainUniformity: params.uniformity[c],
                    seed: UInt64(c + sub * 10), blurParticle: 0,
                    width: width, height: height
                )
                for p in 0..<pixelCount { output.data[p * 3 + c] += modelled[p] }
            }
        }
        for c in 0..<3 {
            for p in 0..<pixelCount {
                output.data[p * 3 + c] = output.data[p * 3 + c] / Double(subLayers) - params.densityMin[c]
            }
        }
        if params.blur > 0.4 {
            output = FastGaussian.filter(output, sigma: params.blur)
        }
        return output
    }

    static func apply(densityCMY: ImageRGB, pixelSizeUM: Double, params: GrainParams,
                      densityCurves: [[Double]], densityCurvesLayers: [[[Double]]],
                      profileType: String, bypass: Bool) -> ImageRGB {
        guard params.active, !bypass, pixelSizeUM > 0 else { return densityCMY }
        if !params.sublayersActive {
            return applyToDensity(densityCMY: densityCMY, pixelSizeUM: pixelSizeUM,
                                  params: params, densityCurves: densityCurves)
        }
        return applyToDensityLayers(
            densityCMY: densityCMY, pixelSizeUM: pixelSizeUM, params: params,
            densityCurves: densityCurves, densityCurvesLayers: densityCurvesLayers,
            positive: profileType == "positive"
        )
    }
}
