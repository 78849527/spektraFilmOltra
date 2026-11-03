import Foundation

struct ImageRGB {
    var width: Int
    var height: Int
    var data: [Double] // HWC, 3 channels

    init(width: Int, height: Int, data: [Double]? = nil) {
        self.width = width
        self.height = height
        let count = width * height * 3
        self.data = data ?? [Double](repeating: 0, count: count)
        precondition(self.data.count == count)
    }

    init(width: Int, height: Int, r: Double, g: Double, b: Double) {
        self.width = width
        self.height = height
        self.data = [Double](repeating: 0, count: width * height * 3)
        for i in 0..<(width * height) {
            data[i * 3] = r
            data[i * 3 + 1] = g
            data[i * 3 + 2] = b
        }
    }

    subscript(x: Int, y: Int, c: Int) -> Double {
        get { data[(y * width + x) * 3 + c] }
        set { data[(y * width + x) * 3 + c] = newValue }
    }

    func pixel(_ x: Int, _ y: Int) -> Vec3 {
        Vec3(self[x, y, 0], self[x, y, 1], self[x, y, 2])
    }

    mutating func setPixel(_ x: Int, _ y: Int, _ value: Vec3) {
        self[x, y, 0] = value.x
        self[x, y, 1] = value.y
        self[x, y, 2] = value.z
    }

    func map(_ transform: (Vec3) -> Vec3) -> ImageRGB {
        var output = self
        for y in 0..<height {
            for x in 0..<width {
                output.setPixel(x, y, transform(pixel(x, y)))
            }
        }
        return output
    }
}

enum ImageMath {
    static func clamp(_ value: Double, _ low: Double, _ high: Double) -> Double {
        min(max(value, low), high)
    }

    static func log10Safe(_ value: Double) -> Double {
        log10(max(value, 0) + 1e-10)
    }

    static func pow10(_ value: Double) -> Double {
        pow(10.0, value)
    }
}

