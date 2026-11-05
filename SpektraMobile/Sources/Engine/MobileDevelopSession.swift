import Foundation
import SwiftUI

/// 单张照片的显影会话：真实 RAW 解码 → 物理显影 → 双层预览（LUT 预测 + 精算）+ 参数映射 + 撤销。
/// 只写 `PhotoEdit` 的既有字段，不改任何算法。
@MainActor
final class MobileDevelopSession: ObservableObject {
    // MARK: - 对外状态

    @Published private(set) var previewImage: MPlatformImage?
    @Published private(set) var originalImage: MPlatformImage?
    @Published private(set) var isPredicted = false
    @Published private(set) var isRendering = false
    @Published private(set) var phaseLabel = ""
    @Published private(set) var phaseProgress: Double = 0
    @Published private(set) var errorMessage: String?
    @Published private(set) var isLoaded = false
    @Published private(set) var isExporting = false
    @Published private(set) var previewAspect: CGFloat = 4.0 / 3.0

    @Published private(set) var quickValues: [String: Double] = [:]
    @Published private(set) var padX: Double = 0
    @Published private(set) var padY: Double = 0
    @Published private(set) var proValues: [String: Double] = [:]
    @Published private(set) var proToggles: [String: Bool] = [:]
    @Published private(set) var filmID: String
    @Published private(set) var paperID: String
    @Published private(set) var canUndo = false

    // MARK: - 标识

    let photoID: String
    let filename: String
    private let store: LibraryStore
    /// 参数落盘后通知照片库刷新列表。
    var onPersist: ((LibraryPhoto) -> Void)?

    // MARK: - 内部状态

    private let renderer = PreviewRenderer()
    private let handoffRenderer = PreviewRenderer()
    private let lutService = PreviewLUTService()
    private let loadQueue = DispatchQueue(label: "spektra.mobile.develop.load", qos: .userInitiated)
    private let lutQueue = DispatchQueue(label: "spektra.mobile.develop.lut", qos: .userInitiated)
    private let exportQueue = DispatchQueue(label: "spektra.mobile.develop.export", qos: .userInitiated)

    private var edit: PhotoEdit
    private var baseline: PhotoEdit
    private var quickIntents: [String: Double]
    private var image: ImageRGB?
    private var inputColorSpace = "ProPhoto RGB"
    private var inputCCTF = false

    private var undoStack: [PhotoEdit] = []
    private var lastUndoKey = ""
    private var lastUndoTime = Date.distantPast

    private var loadToken = 0
    private var fastToken = 0
    private var renderToken = 0
    private var accurateDoneFastToken = -1
    private var renderInFlight = false
    private var fastInFlight = false
    private var fastDirty = false
    private var pendingSettle: DispatchWorkItem?
    private var persistWork: DispatchWorkItem?
    private var pendingHandoffs: [(Int, (ImageRGB?) -> Void)] = []

    private let previewMaxSize = 960
    /// 交互预测用的低分辨率查找表：33³ 只做拖动期的过渡画面，停手后仍由全精度精算替换。
    private let fastResolution = 33
    private let settleDelay: TimeInterval = 1.0

    init(photo: LibraryPhoto, store: LibraryStore) {
        self.photoID = photo.id
        self.filename = photo.filename
        self.store = store
        self.edit = photo.edit
        if let data = photo.quickBaselineData,
           let decoded = try? JSONDecoder().decode(PhotoEdit.self, from: data) {
            self.baseline = decoded
        } else {
            self.baseline = photo.edit
        }
        self.quickIntents = photo.edit.quickIntents
        self.filmID = photo.edit.filmStock
        self.paperID = photo.edit.printStock
        publishFromEdit()
    }

    // MARK: - 启动

    func start() {
        load()
    }

    func cancel() {
        loadToken += 1
        fastToken += 1
        renderToken += 1
        pendingSettle?.cancel()
        persistWork?.cancel()
        fastDirty = false
        renderer.invalidate()
        handoffRenderer.invalidate()
    }

    /// 离开页面时把参数写盘。
    func finish() {
        persistWork?.cancel()
        persistNow()
    }

    private func load() {
        guard let photo = store.photos.first(where: { $0.id == photoID }) else {
            errorMessage = "照片不在库中"
            return
        }
        let originalURL = store.originalURL(for: photo)
        loadToken += 1
        let token = loadToken
        let maxSize = previewMaxSize
        isRendering = true
        phaseLabel = "读取 RAW"
        phaseProgress = 0
        loadQueue.async { [weak self] in
            do {
                let loaded = try ImageLoader.load(url: originalURL)
                let preview = Resize.smallPreview(loaded.image, maxSize: maxSize)
                let display = Self.displayImage(preview, colorSpace: loaded.colorSpace,
                                                cctfDecoding: loaded.cctfDecoding)
                let original = PreviewRenderer.cgImage(from: display)
                Task { @MainActor [weak self] in
                    guard let self, self.loadToken == token else { return }
                    self.image = loaded.image
                    self.inputColorSpace = loaded.colorSpace
                    self.inputCCTF = loaded.cctfDecoding
                    self.isLoaded = true
                    self.previewAspect = CGFloat(loaded.image.width) / CGFloat(max(1, loaded.image.height))
                    if let original {
                        self.originalImage = MImage.make(cgImage: original)
                        if self.previewImage == nil {
                            self.previewImage = self.originalImage
                        }
                    }
                    self.isRendering = false
                    self.phaseLabel = ""
                    self.prewarmLUT()
                    self.schedulePreview(immediate: true)
                    self.flushHandoffs()
                }
            } catch {
                Task { @MainActor [weak self] in
                    guard let self, self.loadToken == token else { return }
                    self.isRendering = false
                    self.phaseLabel = ""
                    self.errorMessage = String(describing: error)
                    self.flushHandoffs()
                }
            }
        }
    }

    // MARK: - 参数映射

    func applyQuick(_ id: String, _ q: Double) {
        guard MobileCatalog.quickGroups.flatMap(\.axes).contains(where: { $0.id == id }) else { return }
        if id == "temperature" {
            applyPad(x: q, y: padY)
            return
        }
        pushUndo(key: id)
        quickIntents[id] = q
        edit.quickIntents = quickIntents
        applyQuickMapping(id: id, q: q)
        quickValues[id] = q
        persistSoon()
        schedulePreview()
    }

    func applyPad(x: Double, y: Double) {
        pushUndo(key: "pad")
        padX = min(max(x, -100), 100)
        padY = min(max(y, -100), 100)
        quickValues["temperature"] = padX
        quickIntents["temperature"] = padX
        edit.enlarger.yFilterShift = clamp(
            baseline.enlarger.yFilterShift + 40 * padX / 100, -60, 60)
        edit.enlarger.mFilterShift = clamp(
            baseline.enlarger.mFilterShift + 40 * padY / 100, -60, 60)
        edit.quickIntents = quickIntents
        persistSoon()
        schedulePreview()
    }

    func applyPro(_ id: String, _ value: Double) {
        pushUndo(key: "pro." + id)
        writePro(id, value)
        edit.quickIntents = quickIntents
        proValues[id] = value
        persistSoon()
        schedulePreview()
    }

    func applyProToggle(_ id: String, _ value: Bool) {
        pushUndo(key: "toggle." + id)
        switch id {
        case "auto_exposure": edit.camera.autoExposure = value
        default: break
        }
        proToggles[id] = value
        persistSoon()
        schedulePreview()
    }

    func setFilm(_ id: String) {
        guard id != edit.filmStock else { return }
        pushUndo(key: "film")
        var next = baseline
        next.filmStock = id
        next.quickIntents = quickIntents
        for (control, q) in quickIntents where abs(q) > 1e-9 {
            applyQuickMapping(id: control, q: q, edit: &next)
        }
        edit = next
        filmID = id
        publishFromEdit()
        persistNow()
        schedulePreview()
    }

    func setPaper(_ id: String) {
        guard id != edit.printStock else { return }
        pushUndo(key: "paper")
        edit.printStock = id
        paperID = id
        persistNow()
        schedulePreview()
    }

    func resetQuick() {
        pushUndo(key: "reset.quick")
        quickIntents = [:]
        edit.quickIntents = [:]
        edit.camera.exposureCompensationEV = baseline.camera.exposureCompensationEV
        edit.enlarger.printExposure = baseline.enlarger.printExposure
        edit.enlarger.yFilterShift = baseline.enlarger.yFilterShift
        edit.enlarger.mFilterShift = baseline.enlarger.mFilterShift
        edit.printRender.densityCurvesMorph = baseline.printRender.densityCurvesMorph
        edit.filmRender.dirCouplers = baseline.filmRender.dirCouplers
        edit.filmRender.grain = baseline.filmRender.grain
        edit.scanner = baseline.scanner
        publishFromEdit()
        persistNow()
        schedulePreview()
    }

    func resetPro() {
        pushUndo(key: "reset.pro")
        edit = baseline
        edit.filmStock = filmID
        edit.printStock = paperID
        quickIntents = [:]
        edit.quickIntents = [:]
        publishFromEdit()
        persistNow()
        schedulePreview()
    }

    func undo() {
        guard let previous = undoStack.popLast() else { return }
        edit = previous
        quickIntents = previous.quickIntents
        canUndo = !undoStack.isEmpty
        lastUndoKey = ""
        publishFromEdit()
        persistNow()
        schedulePreview()
    }

    // MARK: - 导出

    /// 导出请求：`format` 0 sRGB TIFF16、1 ProPhoto 线性 TIFF16、2 ACES 线性 EXR、3 JPEG。
    func export(format: Int, longEdgeIndex: Int, completion: @escaping (Result<URL, Error>) -> Void) {
        guard !isExporting, let image else {
            completion(.failure(MobileExportError.busy))
            return
        }
        let requested = ExportEdge.resolve(index: longEdgeIndex, originalLongEdge: max(image.width, image.height))
        var params: RuntimePhotoParams
        do {
            params = try edit.runtimeParams()
        } catch {
            completion(.failure(error))
            return
        }
        params.io.inputColorSpace = inputColorSpace
        params.io.inputCCTFDecoding = inputCCTF
        let ext: String
        let bitDepth: Int
        switch format {
        case 1:
            params.io.outputColorSpace = "ProPhoto RGB"
            params.io.outputCCTFEncoding = false
            ext = "tif"; bitDepth = 16
        case 2:
            params.io.outputColorSpace = "ACES2065-1"
            params.io.outputCCTFEncoding = false
            ext = "exr"; bitDepth = 16
        case 3:
            params.io.outputColorSpace = "sRGB"
            params.io.outputCCTFEncoding = true
            ext = "jpg"; bitDepth = 8
        default:
            params.io.outputColorSpace = "sRGB"
            params.io.outputCCTFEncoding = true
            ext = "tif"; bitDepth = 16
        }
        let colorSpace = params.io.outputColorSpace
        let cctf = params.io.outputCCTFEncoding
        let destination = Self.exportURL(filename: filename, ext: ext)
        isExporting = true
        phaseLabel = "导出"
        phaseProgress = 0
        exportQueue.async { [weak self] in
            let pipeline = SimulationPipeline(params: params, keepTaps: false)
            let prepared = PreviewRenderer.prepared(image, maxSize: requested)
            let result = pipeline.process(prepared, progress: { label, index, total in
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    self.phaseLabel = "导出 · " + Self.stageLabel(label)
                    self.phaseProgress = total > 0 ? Double(index) / Double(total) : 0
                }
            })
            do {
                try FileManager.default.createDirectory(
                    at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
                try ImageExport.save(result.rgbOut, to: destination, bitDepth: bitDepth,
                                     colorSpace: colorSpace, cctfEncoding: cctf)
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    self.isExporting = false
                    self.phaseLabel = ""
                    self.phaseProgress = 0
                    completion(.success(destination))
                }
            } catch {
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    self.isExporting = false
                    self.phaseLabel = ""
                    self.phaseProgress = 0
                    completion(.failure(error))
                }
            }
        }
    }

    // MARK: - 交接给调色台

    /// 显影 → 线性 ProPhoto 交接像素。调色台只接收这一份结果，不再接触 RAW。
    /// 若 RAW 还在解码，先挂起，解码完成或失败后再回调。
    func prepareHandoff(maxEdge: Int = 1600, completion: @escaping (ImageRGB?) -> Void) {
        if let image {
            renderHandoff(image, maxEdge: maxEdge, completion: completion)
            return
        }
        if errorMessage != nil {
            completion(nil)
            return
        }
        pendingHandoffs.append((maxEdge, completion))
    }

    private func renderHandoff(_ image: ImageRGB, maxEdge: Int,
                               completion: @escaping (ImageRGB?) -> Void) {
        guard var params = try? edit.runtimeParams() else {
            completion(nil)
            return
        }
        params.io.inputColorSpace = inputColorSpace
        params.io.inputCCTFDecoding = inputCCTF
        params.io.outputColorSpace = "ProPhoto RGB"
        params.io.outputCCTFEncoding = false
        handoffRenderer.render(params: params, image: image, maxSize: maxEdge) { outcome in
            completion(outcome.image)
        }
    }

    private func flushHandoffs() {
        guard let image else {
            let items = pendingHandoffs
            pendingHandoffs.removeAll()
            for (_, completion) in items { completion(nil) }
            return
        }
        let items = pendingHandoffs
        pendingHandoffs.removeAll()
        for (edge, completion) in items {
            renderHandoff(image, maxEdge: edge, completion: completion)
        }
    }

    // MARK: - 渲染

    /// 换片后在后台预烘预测表，首次拖滑杆不必等冷启动烘焙。
    private func prewarmLUT() {
        guard var params = try? edit.runtimeParams(), !params.io.scanFilm else { return }
        params.io.inputColorSpace = inputColorSpace
        params.io.inputCCTFDecoding = inputCCTF
        let key = PreviewLUTService.cacheKey(
            edit: edit, inputColorSpace: inputColorSpace, inputCCTF: inputCCTF)
        let service = lutService
        let resolution = fastResolution
        lutQueue.asyncAfter(deadline: .now() + 0.3) {
            _ = service.bundle(for: params, key: key, resolution: resolution)
        }
    }

    private func schedulePreview(immediate: Bool = false) {
        guard image != nil else { return }
        pendingSettle?.cancel()
        fastToken += 1
        if renderInFlight {
            renderToken += 1
            renderer.invalidate()
            renderInFlight = false
        }
        if immediate {
            fastDirty = false
            renderAccurate()
            return
        }
        isRendering = true
        phaseLabel = ""
        phaseProgress = 0
        requestFast()
        let settle = DispatchWorkItem { [weak self] in
            self?.pendingSettle = nil
            self?.renderAccurate()
        }
        pendingSettle = settle
        DispatchQueue.main.asyncAfter(deadline: .now() + settleDelay, execute: settle)
    }

    /// 拖动期间按“在途 + 补跑”节流，不再用 150ms 防抖，否则连续拖动永远出不了预测帧。
    private func requestFast() {
        if fastInFlight {
            fastDirty = true
            return
        }
        startFast()
    }

    private func renderAccurate() {
        guard let image, var params = try? edit.runtimeParams() else { return }
        params.io.inputColorSpace = inputColorSpace
        params.io.inputCCTFDecoding = inputCCTF
        renderToken += 1
        let token = renderToken
        renderInFlight = true
        isRendering = true
        phaseLabel = "显影中"
        phaseProgress = 0
        renderer.render(
            params: params,
            image: image,
            maxSize: previewMaxSize,
            progress: { label, index, total in
                Task { @MainActor [weak self] in
                    guard let self, self.renderToken == token else { return }
                    self.phaseLabel = Self.stageLabel(label)
                    self.phaseProgress = total > 0 ? Double(index) / Double(total) : 0
                }
            }
        ) { [weak self] outcome in
            let display = PreviewRenderer.cgImage(from: outcome.image)
            Task { @MainActor [weak self] in
                guard let self, self.renderToken == token else { return }
                if let display, !outcome.cancelled {
                    self.previewImage = MImage.make(cgImage: display)
                }
                self.isPredicted = false
                self.isRendering = false
                self.renderInFlight = false
                self.phaseLabel = ""
                self.phaseProgress = 0
                self.accurateDoneFastToken = self.fastToken
            }
        }
    }

    private func startFast() {
        guard let image, var params = try? edit.runtimeParams(), !params.io.scanFilm else { return }
        params.io.inputColorSpace = inputColorSpace
        params.io.inputCCTFDecoding = inputCCTF
        let key = PreviewLUTService.cacheKey(
            edit: edit, inputColorSpace: inputColorSpace, inputCCTF: inputCCTF)
        let source = PreviewRenderer.prepared(image, maxSize: previewMaxSize)
        let service = lutService
        let token = fastToken
        let resolution = fastResolution
        fastInFlight = true
        fastDirty = false
        lutQueue.async { [weak self] in
            guard let bundle = service.bundle(
                for: params, key: key, resolution: resolution
            ) else {
                Task { @MainActor [weak self] in
                    self?.finishFast(token: token, cgImage: nil)
                }
                return
            }
            var autoEV = 0.0
            if params.camera.autoExposure {
                autoEV = PreviewLUTService.measureAutoEV(
                    source: source, colorSpace: params.io.inputColorSpace,
                    applyCCTFDecoding: params.io.inputCCTFDecoding,
                    method: params.camera.autoExposureMethod)
            }
            let linear = bundle.predict(
                source: source, autoEV: autoEV,
                exposureEV: params.camera.exposureCompensationEV,
                printExposure: params.enlarger.printExposure,
                compensate: params.enlarger.printExposureCompensation)
            let display = PreviewLUTService.displayImage(fromLinear: linear)
            let cgImage = PreviewRenderer.cgImage(from: display)
            Task { @MainActor [weak self] in
                self?.finishFast(token: token, cgImage: cgImage)
            }
        }
    }

    private func finishFast(token: Int, cgImage: CGImage?) {
        fastInFlight = false
        if let cgImage, token > accurateDoneFastToken {
            previewImage = MImage.make(cgImage: cgImage)
            isPredicted = true
        }
        if fastDirty, !renderInFlight {
            startFast()
        }
    }

    // MARK: - 写入

    private func applyQuickMapping(id: String, q: Double) {
        applyQuickMapping(id: id, q: q, edit: &edit)
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
            edit.printRender.densityCurvesMorph.gammaFactor = clamp(
                morph.gammaFactor * (1 + 0.35 * q / 100), 0.55, 1.8)
            edit.printRender.densityCurvesMorph.active = q != 0 ? true : morph.active
        case "color_density":
            let b = baseline.filmRender.dirCouplers.inhibitionInterlayer
            edit.filmRender.dirCouplers.inhibitionInterlayer = clamp(
                b * (1 + 0.5 * q / 100), 0.5, 1.5)
            edit.filmRender.dirCouplers.active = q != 0 ? true : baseline.filmRender.dirCouplers.active
        case "grain_amount":
            let grain = baseline.filmRender.grain
            let density = clamp(grain.densityMin[0] * (1 + 0.9 * q / 100), 0.005, 0.08)
            edit.filmRender.grain.densityMin = [density, density, density]
            edit.filmRender.grain.uniformity = grain.uniformity.map {
                clamp($0 - 0.06 * q / 100, 0.90, 0.995)
            }
            edit.filmRender.grain.active = q <= -99 ? false : grain.active
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
        case "temperature":
            edit.enlarger.yFilterShift = clamp(
                baseline.enlarger.yFilterShift + 40 * q / 100, -60, 60)
        default:
            break
        }
    }

    private func writePro(_ id: String, _ value: Double) {
        switch id {
        case "exposure_compensation_ev": edit.camera.exposureCompensationEV = value
        case "print_exposure": edit.enlarger.printExposure = value
        case "gamma_factor":
            edit.printRender.densityCurvesMorph.gammaFactor = value
            edit.printRender.densityCurvesMorph.active = true
        case "developer_exhaustion":
            edit.printRender.densityCurvesMorph.developerExhaustion = value
            edit.printRender.densityCurvesMorph.active = true
        case "gamma_factor_fast":
            edit.printRender.densityCurvesMorph.gammaFactorFast = value
            edit.printRender.densityCurvesMorph.active = true
        case "print_y_filter_shift": edit.enlarger.yFilterShift = value
        case "print_m_filter_shift": edit.enlarger.mFilterShift = value
        case "inhibition_interlayer": edit.filmRender.dirCouplers.inhibitionInterlayer = value
        case "coupler_amount": edit.filmRender.dirCouplers.amount = value
        case "film_format_mm": edit.camera.filmFormatMM = value
        case "diffusion_size_um": edit.filmRender.dirCouplers.diffusionSizeUM = value
        case "halation_amount": edit.filmRender.halation.halationAmount = value
        case "preflash_exposure": edit.enlarger.preflashExposure = value
        case "scanner_unsharp_amount":
            edit.scanner.unsharpMask = [edit.scanner.unsharpMask[0], value]
        case "scanner_unsharp_sigma":
            edit.scanner.unsharpMask = [value, edit.scanner.unsharpMask[1]]
        case "scanner_lens_blur": edit.scanner.lensBlur = value
        case "particle_area_um2": edit.filmRender.grain.particleAreaUM2 = value
        default: break
        }
    }

    /// 专业行的基线读数：用于判断滑条是否被改过，避免拿目录默认值误判。
    func proBaseline(_ id: String) -> Double {
        proValue(id, in: baseline)
    }

    private func proValue(_ id: String) -> Double {
        proValue(id, in: edit)
    }

    private func proValue(_ id: String, in edit: PhotoEdit) -> Double {
        switch id {
        case "exposure_compensation_ev": return edit.camera.exposureCompensationEV
        case "print_exposure": return edit.enlarger.printExposure
        case "gamma_factor": return edit.printRender.densityCurvesMorph.gammaFactor
        case "developer_exhaustion": return edit.printRender.densityCurvesMorph.developerExhaustion
        case "gamma_factor_fast": return edit.printRender.densityCurvesMorph.gammaFactorFast
        case "print_y_filter_shift": return edit.enlarger.yFilterShift
        case "print_m_filter_shift": return edit.enlarger.mFilterShift
        case "inhibition_interlayer":
            return edit.filmRender.dirCouplers.inhibitionInterlayer
        case "coupler_amount": return edit.filmRender.dirCouplers.amount
        case "film_format_mm": return edit.camera.filmFormatMM
        case "diffusion_size_um": return edit.filmRender.dirCouplers.diffusionSizeUM
        case "halation_amount": return edit.filmRender.halation.halationAmount
        case "preflash_exposure": return edit.enlarger.preflashExposure
        case "scanner_unsharp_amount": return edit.scanner.unsharpMask[1]
        case "scanner_unsharp_sigma": return edit.scanner.unsharpMask[0]
        case "scanner_lens_blur": return edit.scanner.lensBlur
        case "particle_area_um2": return edit.filmRender.grain.particleAreaUM2
        default: return 0
        }
    }

    private func proToggleValue(_ id: String) -> Bool {
        switch id {
        case "auto_exposure": return edit.camera.autoExposure
        default: return false
        }
    }

    private func publishFromEdit() {
        var quick: [String: Double] = [:]
        for group in MobileCatalog.quickGroups {
            for axis in group.axes {
                quick[axis.id] = quickIntents[axis.id] ?? axis.base
            }
        }
        padX = clamp((edit.enlarger.yFilterShift - baseline.enlarger.yFilterShift) / 40 * 100, -100, 100)
        padY = clamp((edit.enlarger.mFilterShift - baseline.enlarger.mFilterShift) / 40 * 100, -100, 100)
        quick["temperature"] = padX
        quickValues = quick

        var values: [String: Double] = [:]
        var toggles: [String: Bool] = [:]
        for page in MobileCatalog.proPages {
            for group in page.groups {
                for row in group.rows {
                    switch row.control {
                    case .slider:
                        values[row.id] = proValue(row.id)
                    case .toggle:
                        toggles[row.id] = proToggleValue(row.id)
                    case .choice:
                        break
                    }
                }
            }
        }
        proValues = values
        proToggles = toggles
        filmID = edit.filmStock
        paperID = edit.printStock
    }

    private func pushUndo(key: String) {
        let now = Date()
        if lastUndoKey == key, now.timeIntervalSince(lastUndoTime) < 1.2 {
            lastUndoTime = now
            return
        }
        lastUndoKey = key
        lastUndoTime = now
        undoStack.append(edit)
        if undoStack.count > 40 { undoStack.removeFirst() }
        canUndo = true
    }

    private func persistSoon() {
        persistWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.persistWork = nil
            self?.persistNow()
        }
        persistWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7, execute: work)
    }

    private func persistNow() {
        guard var photo = store.photos.first(where: { $0.id == photoID }) else { return }
        edit.quickIntents = quickIntents
        photo.edit = edit
        if quickIntents.isEmpty {
            photo.quickBaselineData = nil
        } else if photo.quickBaselineData == nil {
            photo.quickBaselineData = try? JSONEncoder().encode(baseline)
        }
        try? store.update(photo)
        onPersist?(photo)
    }

    // MARK: - 工具

    private func clamp(_ value: Double, _ low: Double, _ high: Double) -> Double {
        min(max(value, low), high)
    }

    private static func stageLabel(_ label: String) -> String {
        switch label {
        case "preprocess": return "预处理"
        case "filming.expose": return "胶片曝光"
        case "filming.develop": return "胶片显影"
        case "printing.expose": return "印相曝光"
        case "printing.develop": return "印相显影"
        case "scanning.scan_print": return "扫描打印"
        case "scanning.scan_film": return "正片扫描"
        default: return label
        }
    }

    /// 输入原片转成屏幕 sRGB，供长按对比使用。
    private nonisolated static func displayImage(_ image: ImageRGB, colorSpace: String,
                                                 cctfDecoding: Bool) -> ImageRGB {
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
        return output.sanitizedNonFinite()
    }

    private static func exportURL(filename: String, ext: String) -> URL {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Spektrafilm/Exports", isDirectory: true)
        let stem = (filename as NSString).deletingPathExtension
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return base.appendingPathComponent("\(stem)-\(formatter.string(from: Date())).\(ext)")
    }
}

enum MobileExportError: Error {
    case busy
}

/// 导出长边档位：0 原始、1 2048、2 4096；原始超过手机内存上限时钳位。
enum ExportEdge {
    static let cap = 4096

    static func resolve(index: Int, originalLongEdge: Int) -> Int {
        switch index {
        case 1: return min(2048, max(1, originalLongEdge))
        case 2: return min(4096, max(1, originalLongEdge))
        default: return min(cap, max(1, originalLongEdge))
        }
    }
}
