import Foundation
import CoreImage
import ImageIO

/// RAW 解码（macOS 原生路径）。
///
/// Python 参考实现使用 LibRaw（rawpy）输出线性 ACES RGB；macOS 没有 LibRaw，
/// 这里使用 ImageIO / Core Image 的 RAW 管线（CIRAWFilter）做去马赛克与相机矩阵，
/// 再转换到请求的输出色彩空间。去马赛克与白平衡细节无法与 LibRaw 逐像素一致，
/// 因此这部分不参与数值对拍，只保证接口与色彩空间链路正确。
enum RawDecoder {
    struct Options {
        var whiteBalance: String = "as_shot"
        var temperature: Double?
        var tint: Double?
        var outputColorSpace: String = "ACES2065-1"
        var outputCCTFEncoding: Bool = false
        var lensCorrection: Bool = true
    }

    enum DecodeError: Error, CustomStringConvertible {
        case unsupported(String)
        case renderFailed(String)

        var description: String {
            switch self {
            case .unsupported(let message): return "RAW decode unsupported: \(message)"
            case .renderFailed(let message): return "RAW render failed: \(message)"
            }
        }
    }

    static func decode(url: URL, options: Options = Options()) throws -> ImageRGB {
        guard let filter = CIRAWFilter(imageURL: url) else {
            throw DecodeError.unsupported(url.lastPathComponent)
        }
        filter.isDraftModeEnabled = false
        filter.isLensCorrectionEnabled = options.lensCorrection
        filter.boostAmount = 0
        filter.boostShadowAmount = 0

        switch options.whiteBalance {
        case "as_shot", "daylight":
            break
        case "tungsten":
            filter.neutralTemperature = 2850
        case "custom":
            if let temperature = options.temperature {
                filter.neutralTemperature = Float(temperature)
            }
            if let tint = options.tint {
                // CIRAWFilter 的 tint 轴为 [-150, 150]；Python 的 tint 是绿色乘子（1.0 为中性）。
                filter.neutralTint = Float((tint - 1.0) * 100.0)
            }
        default:
            break
        }

        guard let output = filter.outputImage else {
            throw DecodeError.renderFailed("no output image")
        }
        let extent = output.extent.integral
        let width = Int(extent.width)
        let height = Int(extent.height)
        guard width > 0, height > 0 else {
            throw DecodeError.renderFailed("empty extent")
        }

        let linearSRGB = CGColorSpace(name: CGColorSpace.extendedLinearSRGB)
            ?? CGColorSpaceCreateDeviceRGB()
        var buffer = [Float](repeating: 0, count: width * height * 4)
        let context = CIContext(options: [.workingColorSpace: linearSRGB])
        buffer.withUnsafeMutableBytes { raw in
            context.render(
                output, toBitmap: raw.baseAddress!, rowBytes: width * 4 * MemoryLayout<Float>.size,
                bounds: extent, format: .RGBAf, colorSpace: linearSRGB
            )
        }

        var values = [Double](repeating: 0, count: width * height * 3)
        for i in 0..<(width * height) {
            for c in 0..<3 { values[i * 3 + c] = Double(buffer[i * 4 + c]) }
        }
        var image = ImageRGB(width: width, height: height, data: values)
        if options.outputColorSpace != "sRGB" {
            image = image.map { pixel in
                ColorMath.rgbToRGB(pixel, from: "sRGB", to: options.outputColorSpace)
            }
        }
        if options.outputCCTFEncoding {
            let kind = ColorMath.cctfKind(for: options.outputColorSpace)
            image = image.map { pixel in
                Vec3(
                    ColorMath.cctfEncode(pixel.x, kind: kind),
                    ColorMath.cctfEncode(pixel.y, kind: kind),
                    ColorMath.cctfEncode(pixel.z, kind: kind)
                )
            }
        }
        return image.sanitizedNonFinite()
    }

    /// 基础 EXIF（相机 / 镜头 / 焦距 / 光圈），供导出与界面显示使用。
    static func metadata(url: URL) -> [String: Any]? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any] else {
            return nil
        }
        var result: [String: Any] = [:]
        if let tiff = properties[kCGImagePropertyTIFFDictionary as String] as? [String: Any] {
            if let make = tiff[kCGImagePropertyTIFFMake as String] { result["make"] = make }
            if let model = tiff[kCGImagePropertyTIFFModel as String] { result["model"] = model }
        }
        if let exif = properties[kCGImagePropertyExifDictionary as String] as? [String: Any] {
            if let lens = exif[kCGImagePropertyExifLensModel as String] { result["lensModel"] = lens }
            if let focal = exif[kCGImagePropertyExifFocalLength as String] { result["focalLength"] = focal }
            if let aperture = exif[kCGImagePropertyExifFNumber as String] { result["fNumber"] = aperture }
            if let exposure = exif[kCGImagePropertyExifExposureTime as String] { result["exposureTime"] = exposure }
            if let iso = exif[kCGImagePropertyExifISOSpeedRatings as String] { result["iso"] = iso }
        }
        return result
    }
}