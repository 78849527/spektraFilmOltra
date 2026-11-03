import Foundation
import AppKit

/// 预览渲染调度：串行队列 + 代际取消 + 共享 LUT 缓存 + 预览降采样。
/// 只保留最后一次请求的结果，过期结果直接丢弃。
final class PreviewRenderer {
    struct Outcome {
        let image: ImageRGB
        let elapsed: TimeInterval
        let cancelled: Bool
    }

    private let queue = DispatchQueue(label: "spektra.preview.render", qos: .userInitiated)
    private let lock = NSLock()
    private var generation = 0
    private var sharedLUT: SpectralLUTService?
    private var lutKey: String?

    func invalidate() {
        lock.lock()
        generation += 1
        lock.unlock()
    }

    private func currentGeneration() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return generation
    }

    private func lutService(for params: RuntimePhotoParams) -> SpectralLUTService {
        let key = "\(params.film.info.stock)|\(params.print.info.stock)|\(params.settings.lutResolution)"
        lock.lock()
        defer { lock.unlock() }
        if let sharedLUT, lutKey == key {
            return sharedLUT
        }
        let service = SpectralLUTService(resolution: params.settings.lutResolution)
        sharedLUT = service
        lutKey = key
        return service
    }

    func render(params: RuntimePhotoParams, image: ImageRGB, maxSize: Int? = nil,
                completion: @escaping (Outcome) -> Void) {
        lock.lock()
        generation += 1
        let token = generation
        lock.unlock()
        let capacity = maxSize ?? params.settings.previewMaxSize
        let prepared = Self.prepared(image, maxSize: capacity)
        queue.async { [weak self] in
            guard let self else { return }
            if self.currentGeneration() != token { return }
            var working = params
            let lut = self.lutService(for: working)
            let pipeline = SimulationPipeline(params: working, lutService: lut, keepTaps: false)
            pipeline.shouldCancel = { self.currentGeneration() != token }
            let start = Date()
            let result = pipeline.process(prepared)
            let elapsed = Date().timeIntervalSince(start)
            if self.currentGeneration() != token { return }
            completion(Outcome(image: result.rgbOut, elapsed: elapsed, cancelled: false))
        }
    }

    static func prepared(_ image: ImageRGB, maxSize: Int) -> ImageRGB {
        let longEdge = max(image.width, image.height)
        guard maxSize > 0, longEdge > maxSize else { return image }
        return Resize.smallPreview(image, maxSize: maxSize)
    }

    /// 8-bit sRGB 显示图（预览仅用于屏幕显示）。
    static func nsImage(from image: ImageRGB) -> NSImage? {
        let width = image.width
        let height = image.height
        guard width > 0, height > 0 else { return nil }
        var pixels = [UInt8](repeating: 255, count: width * height * 4)
        for i in 0..<(width * height) {
            for c in 0..<3 {
                let raw = image.data[i * 3 + c]
                let value = raw.isFinite ? min(max(raw, 0), 1) : 0
                pixels[i * 4 + c] = UInt8((value * 255).rounded())
            }
        }
        let space = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        let cgImage: CGImage? = pixels.withUnsafeMutableBytes { buffer -> CGImage? in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width * 4, space: space,
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            ) else { return nil }
            return context.makeImage()
        }
        guard let cgImage else { return nil }
        return NSImage(cgImage: cgImage, size: NSSize(width: width, height: height))
    }
}
