import Foundation

enum FastGaussian {
    static let smallSigmaMax = 3.0
    static let exponentialFits3: [(Double, Double)] = [
        (0.1633, 0.5360), (0.6496, 1.5236), (0.1870, 2.7684),
    ]
    static let exponentialFits2: [(Double, Double)] = [
        (0.6235, 0.9401), (0.3765, 2.5177),
    ]

    static func reflect(_ index: Int, _ count: Int) -> Int {
        if index >= 0 && index < count { return index }
        if index < 0 && index >= -count { return -index - 1 }
        if index >= count && index < 2 * count { return 2 * count - 1 - index }
        var value = index % (2 * count)
        if value < 0 { value += 2 * count }
        if value >= count { value = 2 * count - 1 - value }
        return value
    }

    static func kernel(sigma: Double, truncate: Double) -> ([Double], Int) {
        let radius = Int(truncate * sigma + 0.5)
        let size = 2 * radius + 1
        var values = [Double](repeating: 0, count: size)
        var total = 0.0
        for i in 0..<size {
            let x = Double(i - radius)
            let value = exp(-0.5 * pow(x / sigma, 2))
            values[i] = value
            total += value
        }
        for i in 0..<size { values[i] /= total }
        return (values, radius)
    }

    static func filterChannel(_ input: [Double], width: Int, height: Int,
                              sigma: Double, truncate: Double = 3.0) -> [Double] {
        if sigma <= 0 { return input }
        if sigma >= smallSigmaMax { return iirFilter(input, width: width, height: height, sigma: sigma) }
        let (kernel, radius) = self.kernel(sigma: sigma, truncate: truncate)
        var temporary = [Double](repeating: 0, count: input.count)
        for y in 0..<height {
            for x in 0..<width {
                var sum = 0.0
                for k in -radius...radius {
                    sum += input[reflect(y + k, height) * width + x] * kernel[k + radius]
                }
                temporary[y * width + x] = sum
            }
        }
        var output = [Double](repeating: 0, count: input.count)
        for y in 0..<height {
            for x in 0..<width {
                var sum = 0.0
                for k in -radius...radius {
                    sum += temporary[y * width + reflect(x + k, width)] * kernel[k + radius]
                }
                output[y * width + x] = sum
            }
        }
        return output
    }

    static func iirCoefficients(_ sigma: Double) -> (Double, Double, Double, Double) {
        let q: Double
        if sigma >= 2.5 {
            q = 0.98711 * sigma - 0.96330
        } else {
            q = 3.97156 - 4.14554 * sqrt(1 - 0.26891 * sigma)
        }
        let q2 = q * q
        let q3 = q2 * q
        let b0 = 1.57825 + 2.44413 * q + 1.4281 * q2 + 0.422205 * q3
        let b1 = 2.44413 * q + 2.85619 * q2 + 1.26661 * q3
        let b2 = -(1.4281 * q2 + 1.26661 * q3)
        let b3 = 0.422205 * q3
        let B = 1 - (b1 + b2 + b3) / b0
        return (B, b1 / b0, b2 / b0, b3 / b0)
    }

    static func iirFilter(_ input: [Double], width: Int, height: Int, sigma: Double) -> [Double] {
        guard sigma >= 0.5 else {
            return filterChannel(input, width: width, height: height, sigma: sigma, truncate: 3.0)
        }
        let (B, B1, B2, B3) = iirCoefficients(sigma)
        var temporary = [Double](repeating: 0, count: input.count)
        for y in 0..<height {
            var w1 = input[y * width]
            var w2 = w1
            var w3 = w1
            for x in 0..<width {
                let w = B * input[y * width + x] + B1 * w1 + B2 * w2 + B3 * w3
                temporary[y * width + x] = w
                w3 = w2
                w2 = w1
                w1 = w
            }
            var y1 = temporary[y * width + width - 1]
            var y2 = y1
            var y3 = y1
            for x in stride(from: width - 1, through: 0, by: -1) {
                let value = B * temporary[y * width + x] + B1 * y1 + B2 * y2 + B3 * y3
                temporary[y * width + x] = value
                y3 = y2
                y2 = y1
                y1 = value
            }
        }
        var output = [Double](repeating: 0, count: input.count)
        for x in 0..<width {
            var w1 = temporary[x]
            var w2 = w1
            var w3 = w1
            for y in 0..<height {
                let w = B * temporary[y * width + x] + B1 * w1 + B2 * w2 + B3 * w3
                output[y * width + x] = w
                w3 = w2
                w2 = w1
                w1 = w
            }
            var y1 = output[(height - 1) * width + x]
            var y2 = y1
            var y3 = y1
            for y in stride(from: height - 1, through: 0, by: -1) {
                let value = B * output[y * width + x] + B1 * y1 + B2 * y2 + B3 * y3
                output[y * width + x] = value
                y3 = y2
                y2 = y1
                y1 = value
            }
        }
        return output
    }

    static func filter(_ image: ImageRGB, sigma: [Double], truncate: Double = 3.0) -> ImageRGB {
        var output = image
        for c in 0..<3 {
            var channel = [Double](repeating: 0, count: image.width * image.height)
            for i in 0..<channel.count { channel[i] = image.data[i * 3 + c] }
            let filtered = filterChannel(channel, width: image.width, height: image.height,
                                         sigma: sigma[c], truncate: truncate)
            for i in 0..<filtered.count { output.data[i * 3 + c] = filtered[i] }
        }
        return output
    }

    static func filter(_ image: ImageRGB, sigma: Double, truncate: Double = 3.0) -> ImageRGB {
        filter(image, sigma: [sigma, sigma, sigma], truncate: truncate)
    }

    static func exponentialFilter(_ image: ImageRGB, decay: [Double], nGaussians: Int = 3) -> ImageRGB {
        let fits = nGaussians == 2 ? exponentialFits2 : exponentialFits3
        var result = ImageRGB(width: image.width, height: image.height)
        for (index, fit) in fits.enumerated() {
            let component = filter(image, sigma: decay.map { $0 * fit.1 })
            for c in 0..<3 {
                for i in 0..<(image.width * image.height) {
                    let value = fit.0 * component.data[i * 3 + c]
                    if index == 0 { result.data[i * 3 + c] = value }
                    else { result.data[i * 3 + c] += value }
                }
            }
        }
        return result
    }

    static func exponentialFilter(_ image: ImageRGB, decay: Double, nGaussians: Int = 3) -> ImageRGB {
        exponentialFilter(image, decay: [decay, decay, decay], nGaussians: nGaussians)
    }
}
