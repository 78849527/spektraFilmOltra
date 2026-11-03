import Foundation
import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// 把 SpektraCore 引擎接到 SpektraSkin 的只读快照 / 动作协议上。
@MainActor
final class EngineHost: ObservableObject {
    static let shared = EngineHost()

    @Published private(set) var revision = 0
    @Published private(set) var previewImage: NSImage?
    @Published private(set) var isRendering = false
    @Published private(set) var statusMessage = "照片库已就绪"

    let store: LibraryStore
    let renderer = PreviewRenderer()
    let exportQueue = ExportQueue()

    private(set) var selectedID: String?
    private var baseline = PhotoEdit()
    private var quickIntents: [String: Double] = [:]
    private var padIntent = CGPoint(x: 0, y: 0)
    private var loadedImage: ImageRGB?
    private var loadedColorSpace = "ProPhoto RGB"
    private var loadedCCTF = false
    private var thumbnailCache: [String: String] = [:]
    private var previewCache: [String: NSImage] = [:]
    private var previewHistogram: HistogramData?
    private var originalImage: NSImage?
    private(set) var previewScale: Double = 0.25
    private let thumbnailQueue = DispatchQueue(label: "spektra.thumbnail", qos: .utility)

    init(store: LibraryStore = LibraryStore()) {
        self.store = store
        refreshThumbnailCache()
        exportQueue.onUpdate = { [weak self] state in
            guard state.isFinished, let self else { return }
            Task { @MainActor in
                self.statusMessage = state.error == nil ? "导出完成" : "导出失败：\(state.error ?? "")"
                self.revision += 1
            }
        }
    }

    func bump() { revision += 1 }

    var photos: [LibraryPhoto] { store.photos }

    func photo(with id: String) -> LibraryPhoto? {
        store.photos.first { $0.id == id }
    }

    func currentPhoto() -> LibraryPhoto? {
        if let selectedID, let photo = photo(with: selectedID) { return photo }
        return store.photos.first
    }

    func selectedEdit() -> PhotoEdit {
        currentPhoto()?.edit ?? baseline
    }

    private func refreshThumbnailCache() {
        thumbnailCache = [:]
        for photo in store.photos {
            if let path = photo.thumbnailPath { thumbnailCache[photo.id] = path }
        }
    }

    func select(photoID: String) {
        guard let photo = photo(with: photoID) else { return }
        if let previous = selectedID, let image = previewImage {
            previewCache[previous] = image
        }
        selectedID = photoID
        previewHistogram = nil
        if let data = photo.quickBaselineData,
           let decoded = try? JSONDecoder().decode(PhotoEdit.self, from: data) {
            baseline = decoded
        } else {
            baseline = photo.edit
        }
        quickIntents = photo.edit.quickIntents
        padIntent = CGPoint(
            x: photo.edit.enlarger.yFilterShift,
            y: photo.edit.enlarger.mFilterShift
        )
        statusMessage = photo.filename
        loadImage(for: photo)
    }

    private func loadImage(for photo: LibraryPhoto) {
        let url = store.originalURL(for: photo)
        guard let loaded = try? ImageLoader.load(url: url) else {
            statusMessage = "无法读取 \(photo.filename)"
            return
        }
        loadedImage = loaded.image
        loadedColorSpace = loaded.colorSpace
        loadedCCTF = loaded.cctfDecoding
        originalImage = Self.displayImage(
            loaded.image, colorSpace: loaded.colorSpace,
            cctfDecoding: loaded.cctfDecoding
        )
        renderPreview()
        generateThumbnail(for: photo, image: loaded.image)
    }

    private func generateThumbnail(for photo: LibraryPhoto, image: ImageRGB) {
        guard photo.thumbnailPath == nil, var params = try? photo.makeParams() else { return }
        params.io.inputColorSpace = loadedColorSpace
        params.io.inputCCTFDecoding = loadedCCTF
        let small = Resize.smallPreview(image, maxSize: 320)
        thumbnailQueue.async { [weak self] in
            let output = SimulationPipeline(params: params, keepTaps: false).process(small).rgbOut
            guard let self else { return }
            try? self.store.writeThumbnail(id: photo.id, image: output)
            DispatchQueue.main.async {
                self.refreshThumbnailCache()
                self.revision += 1
            }
        }
    }

    /// 为库中所有缺少缩略图的照片补渲染（首屏网格 / 胶片条直接显示真实画面）。
    func warmThumbnails() {
        let pending = store.photos.filter { $0.thumbnailPath == nil }
        for photo in pending {
            thumbnailQueue.async { [weak self] in
                guard let self,
                      let current = self.store.photos.first(where: { $0.id == photo.id }),
                      current.thumbnailPath == nil,
                      let loaded = try? ImageLoader.load(url: self.store.originalURL(for: current)),
                      var params = try? current.makeParams() else { return }
                params.io.inputColorSpace = loaded.colorSpace
                params.io.inputCCTFDecoding = loaded.cctfDecoding
                let small = Resize.smallPreview(loaded.image, maxSize: 320)
                let output = SimulationPipeline(params: params, keepTaps: false).process(small).rgbOut
                try? self.store.writeThumbnail(id: current.id, image: output)
                DispatchQueue.main.async {
                    self.refreshThumbnailCache()
                    self.revision += 1
                }
            }
        }
    }

    func applyQuick(_ id: String, _ q: Double) {
        guard var photo = currentPhoto() else { return }
        quickIntents[id] = q
        photo.edit.quickIntents = quickIntents
        applyQuickMapping(id: id, q: q, edit: &photo.edit)
        persist(photo)
        renderPreview()
    }

    func applyPad(_ x: Double, _ y: Double) {
        guard var photo = currentPhoto() else { return }
        padIntent = CGPoint(x: x, y: y)
        photo.edit.enlarger.yFilterShift = min(max(baseline.enlarger.yFilterShift + 40 * x / 100, -60), 60)
        photo.edit.enlarger.mFilterShift = min(max(baseline.enlarger.mFilterShift + 40 * y / 100, -60), 60)
        persist(photo)
        renderPreview()
    }

    private func persist(_ photo: LibraryPhoto) {
        var photo = photo
        if photo.edit.quickIntents.isEmpty {
            photo.quickBaselineData = nil
        } else if photo.quickBaselineData == nil {
            photo.quickBaselineData = try? JSONEncoder().encode(baseline)
        }
        try? store.update(photo)
        bump()
    }

    func renderPreview() {
        guard let photo = currentPhoto(), let image = loadedImage,
              var params = try? photo.makeParams() else { return }
        params.io.inputColorSpace = loadedColorSpace
        params.io.inputCCTFDecoding = loadedCCTF
        isRendering = true
        bump()
        let longEdge = max(image.width, image.height)
        let maxSize = max(160, Int(Double(longEdge) * previewScale))
        renderer.render(params: params, image: image, maxSize: maxSize) { outcome in
            let histogram = Self.histogram(from: outcome.image)
            Task { @MainActor in
                self.previewImage = PreviewRenderer.nsImage(from: outcome.image)
                self.previewHistogram = histogram
                self.isRendering = false
                self.statusMessage = String(format: "预览 %.2f s", outcome.elapsed)
                self.bump()
            }
        }
    }

    func setFilm(_ id: String) {
        guard var photo = currentPhoto(), id != photo.edit.filmStock else { return }
        var edit = baseline
        edit.filmStock = id
        edit.quickIntents = quickIntents
        for (control, q) in quickIntents where abs(q) > 1e-9 {
            applyQuickMapping(id: control, q: q, edit: &edit)
        }
        photo.edit = edit
        persist(photo)
        renderPreview()
    }

    func setPaper(_ id: String) {
        guard var photo = currentPhoto(), id != photo.edit.printStock else { return }
        photo.edit.printStock = id
        persist(photo)
        renderPreview()
    }

    func resetParameters() {
        guard var photo = currentPhoto() else { return }
        photo.edit = baseline
        photo.edit.quickIntents = [:]
        quickIntents = [:]
        padIntent = .zero
        persist(photo)
        renderPreview()
    }

    @discardableResult
    func importPhotos(_ urls: [URL]) -> String? {
        var firstID: String?
        var imported = 0
        for url in urls {
            if let photo = try? store.importPhoto(from: url) {
                imported += 1
                firstID = firstID ?? photo.id
            }
        }
        bump()
        if let id = firstID {
            select(photoID: id)
        }
        warmThumbnails()
        statusMessage = imported > 0
            ? "已导入 \(imported) 张 RAW"
            : "未导入：显影台只支持 RAW"
        return firstID
    }

    func importFolder(_ url: URL) {
        var raws: [URL] = []
        if let enumerator = FileManager.default.enumerator(
            at: url, includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        ) {
            for case let file as URL in enumerator
            where ImageLoader.rawSuffixes.contains(file.pathExtension.lowercased()) {
                raws.append(file)
            }
        }
        if raws.isEmpty {
            statusMessage = "文件夹中没有 RAW"
        } else {
            importPhotos(raws)
        }
    }

    func toggleFavorite(_ photoID: String) {
        guard var photo = photo(with: photoID) else { return }
        photo.favorite.toggle()
        persist(photo)
    }

    func setColorLabel(_ photoID: String, _ label: ColorLabel?) {
        guard var photo = photo(with: photoID) else { return }
        photo.colorLabel = label?.rawValue
        persist(photo)
    }

    func removePhoto(_ photoID: String) {
        guard selectedID != photoID || store.photos.count > 1 else {
            try? store.remove(id: photoID)
            selectedID = nil
            loadedImage = nil
            previewImage = nil
            originalImage = nil
            previewCache.removeAll()
            refreshThumbnailCache()
            bump()
            return
        }
        try? store.remove(id: photoID)
        previewCache.removeValue(forKey: photoID)
        refreshThumbnailCache()
        if selectedID == photoID {
            selectedID = nil
            if let next = store.photos.first {
                select(photoID: next.id)
            } else {
                loadedImage = nil
                previewImage = nil
                originalImage = nil
            }
        }
        bump()
    }

    func setPreviewScale(_ scale: Double) {
        let value = min(max(scale, 0.125), 1.0)
        guard value != previewScale else { return }
        previewScale = value
        previewCache.removeAll()
        bump()
        renderPreview()
    }

    func exportAs(_ format: String) {
        guard let photo = currentPhoto() else {
            statusMessage = "没有可导出的照片"
            return
        }
        let ext: String
        let bitDepth: Int
        var colorSpace: String?
        var cctfEncoding: Bool?
        switch format {
        case "tiff8":
            ext = "tif"; bitDepth = 8
        case "tiff16-prophoto":
            ext = "tif"; bitDepth = 16
            colorSpace = "ProPhoto RGB"; cctfEncoding = false
        case "exr16":
            ext = "exr"; bitDepth = 16
            colorSpace = "ACES2065-1"; cctfEncoding = false
        default:
            ext = "tif"; bitDepth = 16
        }
        let panel = NSSavePanel()
        panel.canCreateDirectories = true
        panel.allowedContentTypes = [UTType(filenameExtension: ext) ?? .data]
        let base = (photo.filename as NSString).deletingPathExtension
        panel.nameFieldStringValue = "\(base)-spektra.\(ext)"
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let destination = panel.url else { return }
            self?.enqueueExport(photo: photo, destination: destination,
                                bitDepth: bitDepth, colorSpace: colorSpace,
                                cctfEncoding: cctfEncoding)
        }
        if let window = NSApp.keyWindow {
            panel.beginSheetModal(for: window, completionHandler: completion)
        } else {
            completion(panel.runModal())
        }
    }

    private func enqueueExport(photo: LibraryPhoto, destination: URL, bitDepth: Int,
                               colorSpace: String? = nil, cctfEncoding: Bool? = nil) {
        exportQueue.enqueue(
            ExportRequest(photoID: photo.id, destination: destination,
                          bitDepth: bitDepth, colorSpace: colorSpace,
                          cctfEncoding: cctfEncoding),
            photo: photo
        )
        statusMessage = "开始导出 \(destination.lastPathComponent)"
    }

    func exportCurrent(to destination: URL? = nil) {
        guard let photo = currentPhoto() else { return }
        let target = destination ?? FileManager.default.temporaryDirectory
            .appendingPathComponent("Spektrafilm-\(photo.id).tif")
        exportQueue.enqueue(
            ExportRequest(photoID: photo.id, destination: target, bitDepth: 16),
            photo: photo
        )
        statusMessage = "开始导出 \(target.lastPathComponent)"
    }

    private func clamp(_ value: Double, _ low: Double, _ high: Double) -> Double {
        min(max(value, low), high)
    }

    /// 56 桶 RGB 直方图，取自当前预览输出（线性显示空间，桶内最大值归一）。
    private static func histogram(from image: ImageRGB, binCount: Int = 56) -> HistogramData {
        var bins = [[Double]](repeating: [Double](repeating: 0, count: binCount), count: 3)
        let pixels = image.width * image.height
        guard pixels > 0 else { return PreviewData.histogram }
        let stride = max(1, pixels / 200_000)
        var index = 0
        while index < pixels {
            for channel in 0..<3 {
                let value = min(max(image.data[index * 3 + channel], 0), 1)
                let bucket = min(binCount - 1, Int(value * Double(binCount)))
                bins[channel][bucket] += 1
            }
            index += stride
        }
        let peak = bins.flatMap { $0 }.max() ?? 0
        guard peak > 0 else { return PreviewData.histogram }
        return HistogramData(
            red: bins[0].map { $0 / peak },
            green: bins[1].map { $0 / peak },
            blue: bins[2].map { $0 / peak }
        )
    }

    /// 把线性工作图转成屏幕显示用的 sRGB 8-bit NSImage（用于“对比”原图）。
    private static func displayImage(_ image: ImageRGB, colorSpace: String,
                                     cctfDecoding: Bool) -> NSImage? {
        var output = image
        if cctfDecoding {
            let kind = ColorMath.cctfKind(for: colorSpace)
            output = output.map { Vec3(
                ColorMath.cctfDecode($0.x, kind: kind),
                ColorMath.cctfDecode($0.y, kind: kind),
                ColorMath.cctfDecode($0.z, kind: kind)
            ) }
        }
        output = output.map { pixel in
            let converted = ColorMath.rgbToRGB(pixel, from: colorSpace, to: "sRGB")
            return Vec3(converted.x, converted.y, converted.z)
        }
        let kind = ColorMath.cctfKind(for: "sRGB")
        output = output.map { Vec3(
            ColorMath.cctfEncode($0.x, kind: kind),
            ColorMath.cctfEncode($0.y, kind: kind),
            ColorMath.cctfEncode($0.z, kind: kind)
        ) }
        return PreviewRenderer.nsImage(from: output.sanitizedNonFinite())
    }

    private func applyQuickMapping(id: String, q: Double, edit: inout PhotoEdit) {
        switch id {
        case "camera_exposure":
            edit.camera.exposureCompensationEV = clamp(
                baseline.camera.exposureCompensationEV + q, -5, 5)
        case "print_brightness":
            let b = baseline.enlarger.printExposure
            edit.enlarger.printExposure = clamp(b * pow(2, -q), 0.125, 8)
        case "tonal_contrast":
            let morph = baseline.printRender.densityCurvesMorph
            let value = clamp(morph.gammaFactor * (1 + 0.35 * q / 100), 0.55, 1.8)
            edit.printRender.densityCurvesMorph.gammaFactor = value
            edit.printRender.densityCurvesMorph.active = q != 0 ? true : morph.active
        case "color_density":
            let b = baseline.filmRender.dirCouplers.inhibitionInterlayer
            edit.filmRender.dirCouplers.inhibitionInterlayer = clamp(b * (1 + 0.5 * q / 100), 0.5, 1.5)
            edit.filmRender.dirCouplers.active = q != 0 ? true : baseline.filmRender.dirCouplers.active
        case "grain_amount":
            let grain = baseline.filmRender.grain
            let density = clamp(grain.densityMin[0] * (1 + 0.9 * q / 100), 0.005, 0.08)
            edit.filmRender.grain.densityMin = [density, density, density]
            edit.filmRender.grain.uniformity = grain.uniformity.map {
                clamp($0 - 0.06 * q / 100, 0.90, 0.995)
            }
            edit.filmRender.grain.active = q <= -99 ? false : grain.active
        case "grain_size":
            let grain = baseline.filmRender.grain
            edit.filmRender.grain.particleAreaUM2 = clamp(
                grain.particleAreaUM2 * pow(2, 0.9 * q / 100), 0.03, 1.2)
            edit.filmRender.grain.blur = clamp(grain.blur * (1 + 0.25 * q / 100), 0.4, 1.2)
        case "halation_amount":
            let h = baseline.filmRender.halation
            edit.filmRender.halation.halationAmount = clamp(h.halationAmount * (1 + 1.2 * q / 100), 0, 3)
            edit.filmRender.halation.active = q <= -99 ? false : h.active
        case "halation_scale":
            let h = baseline.filmRender.halation
            edit.filmRender.halation.halationSpatialScale = clamp(
                h.halationSpatialScale * pow(2, 0.6 * q / 100), 0.5, 2.5)
        case "diffusion":
            let base = baseline.camera.diffusionFilter
            if q > 0 {
                edit.camera.diffusionFilter.active = true
                edit.camera.diffusionFilter.strength = clamp(0.125 + 1.375 * q / 100, 0.125, 1.5)
            } else {
                edit.camera.diffusionFilter.active = base.active
                edit.camera.diffusionFilter.strength = base.strength
            }
        case "scanner_clarity":
            let scanner = baseline.scanner
            if q > 0 {
                let amount = scanner.unsharpMask[1]
                edit.scanner.unsharpMask = [
                    scanner.unsharpMask[0],
                    clamp(amount + (1.8 - amount) * q / 100, 0, 2),
                ]
                edit.scanner.lensBlur = scanner.lensBlur
            } else {
                edit.scanner.lensBlur = clamp(scanner.lensBlur + 0.6 * (-q) / 100, 0, 0.8)
                edit.scanner.unsharpMask = scanner.unsharpMask
            }
        default:
            break
        }
    }

    func applyPro(_ id: String, _ value: Double) {
        guard var photo = currentPhoto() else { return }
        var edit = photo.edit
        switch id {
        case "print_exposure": edit.enlarger.printExposure = value
        case "exposure_compensation_ev": edit.camera.exposureCompensationEV = value
        case "film_gamma_factor":
            edit.printRender.densityCurvesMorph.gammaFactor = value
            edit.printRender.densityCurvesMorph.active = true
        case "developer_exhaustion": edit.printRender.densityCurvesMorph.developerExhaustion = value
        case "gamma_factor": edit.printRender.densityCurvesMorph.gammaFactor = value
        case "gamma_factor_fast": edit.printRender.densityCurvesMorph.gammaFactorFast = value
        case "gamma_factor_slow": edit.printRender.densityCurvesMorph.gammaFactorSlow = value
        case "gamma_factor_red": edit.printRender.densityCurvesMorph.gammaFactorRed = value
        case "gamma_factor_green": edit.printRender.densityCurvesMorph.gammaFactorGreen = value
        case "gamma_factor_blue": edit.printRender.densityCurvesMorph.gammaFactorBlue = value
        case "white_level": edit.scanner.whiteLevel = value
        case "black_level": edit.scanner.blackLevel = value
        case "glare_percent": edit.printRender.glare.percent = value
        case "glare_roughness": edit.printRender.glare.roughness = value
        case "preflash_exposure": edit.enlarger.preflashExposure = value
        case "preflash_y": edit.enlarger.preflashYFilterShift = value
        case "preflash_m": edit.enlarger.preflashMFilterShift = value
        case "print_y_filter_shift": edit.enlarger.yFilterShift = value
        case "print_m_filter_shift": edit.enlarger.mFilterShift = value
        case "inhibition_interlayer": edit.filmRender.dirCouplers.inhibitionInterlayer = value
        case "inhibition_samelayer": edit.filmRender.dirCouplers.inhibitionSameLayer = value
        case "coupler_amount": edit.filmRender.dirCouplers.amount = value
        case "diffusion_size_um": edit.filmRender.dirCouplers.diffusionSizeUM = value
        case "particle_area_um2": edit.filmRender.grain.particleAreaUM2 = value
        case "grain_blur": edit.filmRender.grain.blur = value
        case "blur_dye_clouds_um": edit.filmRender.grain.blurDyeCloudsUM = value
        case "halation_amount": edit.filmRender.halation.halationAmount = value
        case "scatter_amount": edit.filmRender.halation.scatterAmount = value
        case "halation_spatial_scale": edit.filmRender.halation.halationSpatialScale = value
        case "boost_ev": edit.filmRender.halation.boostEV = value
        case "protect_ev": edit.filmRender.halation.protectEV = value
        case "lens_blur": edit.scanner.lensBlur = value
        case "lens_blur_um": edit.camera.lensBlurUM = value
        case "diffusion_strength": edit.camera.diffusionFilter.strength = value
        case "film_format_mm": edit.camera.filmFormatMM = value
        case "upscale_factor": edit.io.upscaleFactor = value
        default: break
        }
        photo.edit = edit
        persist(photo)
        renderPreview()
    }

    func applyProToggle(_ id: String, _ value: Bool) {
        guard var photo = currentPhoto() else { return }
        var edit = photo.edit
        switch id {
        case "print_exposure_compensation": edit.enlarger.printExposureCompensation = value
        case "auto_exposure": edit.camera.autoExposure = value
        case "white_correction": edit.scanner.whiteCorrection = value
        case "black_correction": edit.scanner.blackCorrection = value
        case "glare_active": edit.printRender.glare.active = value
        case "couplers_active": edit.filmRender.dirCouplers.active = value
        case "grain_active": edit.filmRender.grain.active = value
        case "halation_active": edit.filmRender.halation.active = value
        case "chemistry_active": edit.printRender.densityCurvesMorph.active = value
        case "camera_diffusion_active": edit.camera.diffusionFilter.active = value
        case "input_cctf_decoding": edit.io.inputCCTFDecoding = value
        case "input_crop": edit.io.crop = value
        case "saving_cctf": edit.io.outputCCTFEncoding = value
        default: break
        }
        photo.edit = edit
        persist(photo)
        renderPreview()
    }
}

extension EngineHost {
    func filmDisplayName(_ stock: String) -> String {
        PreviewData.films.first { $0.id == stock }?.name ?? stock
    }

    func paperDisplayName(_ stock: String) -> String {
        PreviewData.papers.first { $0.id == stock }?.name ?? stock
    }

    func photoItem(_ photo: LibraryPhoto) -> PhotoItem {
        PhotoItem(
            id: photo.id,
            filename: photo.filename,
            asset: "",
            film: filmDisplayName(photo.edit.filmStock),
            paper: paperDisplayName(photo.edit.printStock),
            dimensions: "\(photo.width)×\(photo.height)",
            isRaw: photo.isRaw,
            favorite: photo.favorite,
            color: photo.colorLabel.flatMap(ColorLabel.init(rawValue:)),
            isGraded: !photo.edit.quickIntents.isEmpty,
            thumbnailPath: thumbnailCache[photo.id] ?? photo.thumbnailPath
        )
    }

    func librarySnapshot() -> LibrarySnapshot {
        let items = store.photos.map(photoItem)
        return LibrarySnapshot(
            folderCount: 1,
            photoCount: items.count,
            sectionTitle: "全部照片",
            sectionCount: "\(items.count) 张照片",
            folders: [
                FolderItem(id: "all", name: "全部照片", count: items.count, isCurrent: true),
            ],
            photos: items,
            statusMessage: statusMessage,
            currentID: selectedID
        )
    }

    func editorSnapshot(for photoID: String) -> EditorSnapshot {
        guard let photo = self.photo(with: photoID) ?? currentPhoto() else {
            return previewEditorSnapshot()
        }
        let item = photoItem(photo)
        let strip = [photo] + store.photos.filter { $0.id != photo.id }.prefix(3)
        let image = (photo.id == selectedID) ? previewImage : previewCache[photo.id]
        let edit = photo.edit
        let baselineEdit = (photo.id == selectedID) ? baseline : edit
        return EditorSnapshot(
            photo: item,
            filmName: filmDisplayName(edit.filmStock),
            paperName: paperDisplayName(edit.printStock),
            filmstrip: strip.map(photoItem),
            quickGroups: quickGroups(edit: edit, baseline: baselineEdit),
            proPages: proPages(edit: edit, film: filmDisplayName(edit.filmStock),
                               paper: paperDisplayName(edit.printStock)),
            histogram: (photo.id == selectedID ? previewHistogram : nil) ?? PreviewData.histogram,
            dirtyCount: edit.quickIntents.filter { abs($0.value) > 1e-9 }.count,
            currentFilmID: edit.filmStock,
            currentPaperID: edit.printStock,
            stripCount: store.photos.count,
            previewImage: image,
            originalImage: photo.id == selectedID ? originalImage : nil,
            previewScale: previewScale
        )
    }

    private func previewEditorSnapshot() -> EditorSnapshot {
        let item = PhotoItem(
            id: "empty", filename: "未选择照片", asset: "window-still",
            film: "—", paper: nil, dimensions: "0×0", isRaw: false,
            favorite: false, color: nil, isGraded: false
        )
        return EditorSnapshot(
            photo: item, filmName: "—", paperName: "—", filmstrip: [],
            quickGroups: PreviewData.quickGroups, proPages: PreviewData.proPages,
            histogram: PreviewData.histogram, dirtyCount: 0,
            currentFilmID: "kodak_portra_400", currentPaperID: "kodak_supra_endura",
            stripCount: 0
        )
    }

    func gradeSnapshot(for photoID: String) -> GradeSnapshot {
        guard let photo = self.photo(with: photoID) else {
            return GradeSnapshot(photo: PhotoItem(
                id: "empty", filename: "未选择照片", asset: "window-still",
                film: "—", paper: nil, dimensions: "0×0", isRaw: false,
                favorite: false, color: nil, isGraded: false
            ), handoffMeta: "")
        }
        let item = photoItem(photo)
        return GradeSnapshot(
            photo: item,
            handoffMeta: "\(item.dimensions) · \(item.film) · 16-bit ProPhoto 线性交接图",
            previewImage: photo.id == selectedID ? previewImage : previewCache[photo.id]
        )
    }

    func quickValue(_ id: String, edit: PhotoEdit, baseline: PhotoEdit) -> Double {
        switch id {
        case "camera_exposure":
            return edit.camera.exposureCompensationEV - baseline.camera.exposureCompensationEV
        case "print_brightness":
            let b = baseline.enlarger.printExposure
            guard b > 0, edit.enlarger.printExposure > 0 else { return 0 }
            return -log2(edit.enlarger.printExposure / b)
        case "tonal_contrast":
            let b = baseline.printRender.densityCurvesMorph.gammaFactor
            guard b > 0 else { return 0 }
            return (edit.printRender.densityCurvesMorph.gammaFactor / b - 1) / 0.35 * 100
        case "color_density":
            let b = baseline.filmRender.dirCouplers.inhibitionInterlayer
            guard b > 0 else { return 0 }
            return (edit.filmRender.dirCouplers.inhibitionInterlayer / b - 1) / 0.5 * 100
        case "grain_amount":
            let b = baseline.filmRender.grain.densityMin[0]
            guard b > 0 else { return 0 }
            return (edit.filmRender.grain.densityMin[0] / b - 1) / 0.9 * 100
        case "grain_size":
            let b = baseline.filmRender.grain.particleAreaUM2
            guard b > 0 else { return 0 }
            return log2(edit.filmRender.grain.particleAreaUM2 / b) / 0.9 * 100
        case "halation_amount":
            let b = baseline.filmRender.halation.halationAmount
            guard b > 0 else { return 0 }
            return (edit.filmRender.halation.halationAmount / b - 1) / 1.2 * 100
        case "halation_scale":
            let b = baseline.filmRender.halation.halationSpatialScale
            guard b > 0 else { return 0 }
            return log2(edit.filmRender.halation.halationSpatialScale / b) / 0.6 * 100
        case "diffusion":
            let editFilter = edit.camera.diffusionFilter
            let base = baseline.camera.diffusionFilter
            guard editFilter.active, !base.active else { return 0 }
            return (editFilter.strength - 0.125) / 1.375 * 100
        case "scanner_clarity":
            let bAmount = baseline.scanner.unsharpMask[1]
            let amount = edit.scanner.unsharpMask[1]
            if abs(amount - bAmount) > 1e-9 {
                return (amount - bAmount) / max(1.8 - bAmount, 1e-6) * 100
            }
            let blurDelta = edit.scanner.lensBlur - baseline.scanner.lensBlur
            guard abs(blurDelta) > 1e-9 else { return 0 }
            return -blurDelta / 0.6 * 100
        default:
            return 0
        }
    }

    func quickGroups(edit: PhotoEdit, baseline: PhotoEdit) -> [QuickGroup] {
        PreviewData.quickGroups.map { group in
            let axes = group.axes.map { axis in
                QuickAxis(
                    id: axis.id, label: axis.label, range: axis.range,
                    step: axis.step, decimals: axis.decimals, suffix: axis.suffix,
                    baseValue: 0,
                    value: quickValue(axis.id, edit: edit, baseline: baseline),
                    unavailableReason: nil
                )
            }
            let pad = group.pad.map { template in
                QuickPad(
                    title: template.title,
                    x: (edit.enlarger.yFilterShift - baseline.enlarger.yFilterShift) / 40 * 100,
                    y: (edit.enlarger.mFilterShift - baseline.enlarger.mFilterShift) / 40 * 100
                )
            }
            return QuickGroup(id: group.id, title: group.title, axes: axes, pad: pad)
        }
    }

    func proValue(_ id: String, edit: PhotoEdit) -> Double? {
        let morph = edit.printRender.densityCurvesMorph
        switch id {
        case "print_exposure": return edit.enlarger.printExposure
        case "exposure_compensation_ev": return edit.camera.exposureCompensationEV
        case "film_gamma_factor": return morph.gammaFactor
        case "developer_exhaustion": return morph.developerExhaustion
        case "gamma_factor": return morph.gammaFactor
        case "gamma_factor_fast": return morph.gammaFactorFast
        case "gamma_factor_slow": return morph.gammaFactorSlow
        case "gamma_factor_red": return morph.gammaFactorRed
        case "gamma_factor_green": return morph.gammaFactorGreen
        case "gamma_factor_blue": return morph.gammaFactorBlue
        case "white_level": return edit.scanner.whiteLevel
        case "black_level": return edit.scanner.blackLevel
        case "glare_percent": return edit.printRender.glare.percent
        case "glare_roughness": return edit.printRender.glare.roughness
        case "preflash_exposure": return edit.enlarger.preflashExposure
        case "preflash_y": return edit.enlarger.preflashYFilterShift
        case "preflash_m": return edit.enlarger.preflashMFilterShift
        case "print_y_filter_shift": return edit.enlarger.yFilterShift
        case "print_m_filter_shift": return edit.enlarger.mFilterShift
        case "inhibition_interlayer": return edit.filmRender.dirCouplers.inhibitionInterlayer
        case "inhibition_samelayer": return edit.filmRender.dirCouplers.inhibitionSameLayer
        case "coupler_amount": return edit.filmRender.dirCouplers.amount
        case "diffusion_size_um": return edit.filmRender.dirCouplers.diffusionSizeUM
        case "particle_area_um2": return edit.filmRender.grain.particleAreaUM2
        case "grain_blur": return edit.filmRender.grain.blur
        case "blur_dye_clouds_um": return edit.filmRender.grain.blurDyeCloudsUM
        case "halation_amount": return edit.filmRender.halation.halationAmount
        case "scatter_amount": return edit.filmRender.halation.scatterAmount
        case "halation_spatial_scale": return edit.filmRender.halation.halationSpatialScale
        case "boost_ev": return edit.filmRender.halation.boostEV
        case "protect_ev": return edit.filmRender.halation.protectEV
        case "lens_blur": return edit.scanner.lensBlur
        case "lens_blur_um": return edit.camera.lensBlurUM
        case "diffusion_strength": return edit.camera.diffusionFilter.strength
        case "film_format_mm": return edit.camera.filmFormatMM
        case "upscale_factor": return edit.io.upscaleFactor
        default: return nil
        }
    }

    func proToggle(_ id: String, edit: PhotoEdit) -> Bool? {
        switch id {
        case "print_exposure_compensation": return edit.enlarger.printExposureCompensation
        case "auto_exposure": return edit.camera.autoExposure
        case "white_correction": return edit.scanner.whiteCorrection
        case "black_correction": return edit.scanner.blackCorrection
        case "glare_active": return edit.printRender.glare.active
        case "couplers_active": return edit.filmRender.dirCouplers.active
        case "grain_active": return edit.filmRender.grain.active
        case "halation_active": return edit.filmRender.halation.active
        case "chemistry_active": return edit.printRender.densityCurvesMorph.active
        case "camera_diffusion_active": return edit.camera.diffusionFilter.active
        case "input_cctf_decoding": return edit.io.inputCCTFDecoding
        case "input_crop": return edit.io.crop
        case "saving_cctf": return edit.io.outputCCTFEncoding
        default: return nil
        }
    }

    func proPages(edit: PhotoEdit, film: String, paper: String) -> [ParamPage] {
        PreviewData.proPages(film: film, paper: paper).map { page in
            ParamPage(id: page.id, title: page.title, groups: page.groups.map { group in
                ParamGroup(id: group.id, title: group.title, rows: group.rows.map { row in
                    switch row.control {
                    case .slider(let template, _, _):
                        guard let value = proValue(row.id, edit: edit) else { return row }
                        return ParamRow(
                            id: row.id, label: row.label,
                            control: .slider(value: value, valueText: format(value),
                                             dirty: abs(value - template) > 1e-9),
                            isEnabled: row.isEnabled
                        )
                    case .toggle(let template):
                        guard let value = proToggle(row.id, edit: edit) else { return row }
                        return ParamRow(
                            id: row.id, label: row.label,
                            control: .toggle(isOn: value),
                            isEnabled: row.isEnabled || template
                        )
                    case .choice:
                        return row
                    }
                })
            })
        }
    }

    private func format(_ value: Double) -> String {
        var text = String(format: "%.2f", value)
        if text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(".") { text.removeLast() }
        return text
    }
}
