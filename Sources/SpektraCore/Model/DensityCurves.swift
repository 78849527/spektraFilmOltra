import Foundation

enum DensityCurves {
    static func computeDensitySpectral(channelDensity: [[Double]], densityCMY: ImageRGB,
                                       baseDensity: [Double]?) -> [[Double]] {
        let pixelCount = densityCMY.width * densityCMY.height
        let wavelengthCount = channelDensity.count
        var output = [[Double]](repeating: [Double](repeating: 0, count: wavelengthCount), count: pixelCount)
        for p in 0..<pixelCount {
            let r = densityCMY.data[p * 3]
            let g = densityCMY.data[p * 3 + 1]
            let b = densityCMY.data[p * 3 + 2]
            for w in 0..<wavelengthCount {
                let row = channelDensity[w]
                var value = r * row[0] + g * row[1] + b * row[2]
                if let baseDensity, w < baseDensity.count {
                    value += baseDensity[w]
                }
                output[p][w] = value
            }
        }
        return output
    }

    static func interpolateExposureToDensity(logExposureRGB: ImageRGB, densityCurves: [[Double]],
                                             logExposure: [Double], gammaFactor: [Double]) -> ImageRGB {
        var xAxis = [[Double]](repeating: [0, 0, 0], count: logExposure.count)
        for i in 0..<logExposure.count {
            for c in 0..<3 {
                xAxis[i][c] = logExposure[i] / gammaFactor[c]
            }
        }
        return Interpolation.interp1D(image: logExposureRGB, xAxisPerChannel: xAxis, yValues: densityCurves)
    }

    static func developSimple(logRaw: ImageRGB, logExposure: [Double], densityCurves: [[Double]],
                              gammaFactor: [Double]) -> ImageRGB {
        interpolateExposureToDensity(
            logExposureRGB: logRaw, densityCurves: densityCurves,
            logExposure: logExposure, gammaFactor: gammaFactor
        )
    }
}

