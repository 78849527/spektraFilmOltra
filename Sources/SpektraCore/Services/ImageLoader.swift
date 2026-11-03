import Foundation
import CoreGraphics
import CoreImage
import ImageIO

struct LoadedImage {
    var image: ImageRGB
    var colorSpace: String
    var cctfDecoding: Bool
    var isRaw: Bool
}

/// 输入图像识别与解码。对齐 Python `spektrafilm_gui/input_color.py`：
/// RAW → ProPhoto 线性；EXR/HDR → ACES 线性；编码图按 ICC 描述匹配，缺省 sRGB + CCTF 解码。
enum ImageLoader {
    static let rawSuffixes: Set<String> = [
        "cr2", "cr3", "nef", "arw", "dng", "raf", "orf", "rw2", "pef",
        "srw", "3fr", "iiq", "x3f", "erf", "mef", "mos", "mrw", "nrw",
        "rwl", "srf", "sr2",
    ]
    static let linearSuffixes: Set<String> = ["exr", "hdr"]
    static let encodedSuffixes: Set<String> = ["png", "tif", "tiff", "bmp", "webp"]
    static let rejectedSuffixes: Set<String> = ["jpg", "jpeg"]

    static let iccMappings: [(String, String)] = [
        ("display p3", "Display P3"),
        ("dci-p3", "DCI-P3"),
        ("adobe rgb", "Adobe RGB (1998)"),
        ("prophoto", "ProPhoto RGB"),
        ("romm", "ProPhoto RGB"),
        ("aces", "ACES2065-1"),
        ("rec.2020", "ITU-R BT.2020"),
        ("bt.2020", "ITU-R BT.2020"),
        ("rec.709", "sRGB"),
        ("bt.709", "sRGB"),
        ("srgb", "sRGB"),
        ("iec61966", "sRGB"),
    ]

    static func detectColorSpace(url: URL) -> (space: String, cctfDecoding: Bool) {
        let suffix = url.pathExtension.lowercased()
        if rawSuffixes.contains(suffix) { return ("ProPhoto RGB", false) }
        if linearSuffixes.contains(suffix) { return ("ACES2065-1", false) }
        if let description = profileName(url: url)?.lowercased() {
            for (token, space) in iccMappings where description.contains(token) {
                return (space, space != "ACES2065-1")
            }
        }
        return ("sRGB", true)
    }

    static func profileName(url: URL) -> String? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)
                as? [String: Any] else { return nil }
        return properties[kCGImagePropertyProfileName as String] as? String
    }

    static func load(url: URL) throws -> LoadedImage {
        let detected = detectColorSpace(url: url)
        let suffix = url.pathExtension.lowercased()
        if rejectedSuffixes.contains(suffix) {
            throw NSError(domain: "Spektrafilm.ImageLoader", code: 3,
                          userInfo: [NSLocalizedDescriptionKey:
                            "显影台不支持 JPEG 输入：\(url.lastPathComponent)"])
        }
        if rawSuffixes.contains(suffix) {
            let image = try RawDecoder.decode(
                url: url,
                options: RawDecoder.Options(outputColorSpace: detected.space)
            )
            return LoadedImage(image: image, colorSpace: detected.space,
                               cctfDecoding: false, isRaw: true)
        }
        if linearSuffixes.contains(suffix) {
            var image = try renderToImage(url: url, colorSpace: "sRGB",
                                          linear: true)
            image = image.map { ColorMath.rgbToRGB($0, from: "sRGB", to: "ACES2065-1") }
            return LoadedImage(image: image, colorSpace: "ACES2065-1",
                               cctfDecoding: false, isRaw: false)
        }
        let image = try renderToImage(url: url, colorSpace: detected.space,
                                      linear: !detected.cctfDecoding)
        return LoadedImage(image: image, colorSpace: detected.space,
                           cctfDecoding: detected.cctfDecoding, isRaw: false)
    }

    /// 用 Core Image 渲染到 RGBAf；`linear` 为 true 时用扩展线性 sRGB 工作空间。
    static func renderToImage(url: URL, colorSpace: String, linear: Bool) throws -> ImageRGB {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw ImageExport.ExportError.encodeFailed("image source \(url.lastPathComponent)")
        }
        let extent = CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height)
        let outputSpace: CGColorSpace
        if linear {
            outputSpace = CGColorSpace(name: CGColorSpace.extendedLinearSRGB)
                ?? CGColorSpaceCreateDeviceRGB()
        } else if let icc = ImageExport.iccProfile(colorSpace: colorSpace, cctfEncoding: true),
                  let profile = CGColorSpace(iccData: icc as CFData) {
            outputSpace = profile
        } else {
            outputSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        }
        let ciImage = CIImage(cgImage: cgImage)
        let context = CIContext(options: [.workingColorSpace: outputSpace])
        var buffer = [Float](repeating: 0, count: cgImage.width * cgImage.height * 4)
        buffer.withUnsafeMutableBytes { raw in
            context.render(
                ciImage, toBitmap: raw.baseAddress!,
                rowBytes: cgImage.width * 4 * MemoryLayout<Float>.size,
                bounds: extent, format: .RGBAf, colorSpace: outputSpace
            )
        }
        var values = [Double](repeating: 0, count: cgImage.width * cgImage.height * 3)
        for i in 0..<(cgImage.width * cgImage.height) {
            for c in 0..<3 { values[i * 3 + c] = Double(buffer[i * 4 + c]) }
        }
        return ImageRGB(width: cgImage.width, height: cgImage.height, data: values)
    }
}
