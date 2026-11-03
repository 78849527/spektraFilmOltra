import Foundation

/// 扫描眩光：屏幕/镜头杂散光在 XYZ 上的加性随机底噪。
/// 对应 Python `model/glare.py`；随机项只要求统计同构。
enum Glare {
    static func addGlare(_ xyz: ImageRGB, illuminantXYZ: Vec3, params: GlareParams?,
                         seed: UInt64 = 11) -> ImageRGB {
        guard let params, params.active, params.percent > 0 else { return xyz }
        let width = xyz.width
        let height = xyz.height
        let count = width * height
        var rng = SplitMix64(seed: seed)
        var amount = [Double](repeating: 0, count: count)
        for i in 0..<count {
            amount[i] = RandomStats.lognormalFromMeanStd(
                params.percent, params.roughness * params.percent, &rng
            )
        }
        amount = FastGaussian.filterChannel(amount, width: width, height: height, sigma: params.blur)
        var output = xyz
        for i in 0..<count {
            let value = amount[i] / 100
            output.data[i * 3] = xyz.data[i * 3] + value * illuminantXYZ.x
            output.data[i * 3 + 1] = xyz.data[i * 3 + 1] + value * illuminantXYZ.y
            output.data[i * 3 + 2] = xyz.data[i * 3 + 2] + value * illuminantXYZ.z
        }
        return output
    }
}
