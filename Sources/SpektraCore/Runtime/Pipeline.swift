import Foundation

struct PipelineResult {
    var rgbIn: ImageRGB
    var rgbPre: ImageRGB
    var logEFilm: ImageRGB
    var cmyFilm: ImageRGB
    var logEPrint: ImageRGB?
    var cmyPrint: ImageRGB?
    var rgbOut: ImageRGB
}

final class SimulationPipeline {
    let params: RuntimePhotoParams
    private let lutService: SpectralLUTService
    private let enlargerService: EnlargerService
    private let colorReference: ColorReferenceService
    private let filming: FilmingStage
    private let printing: PrintingStage
    private let scanning: ScanningStage
    private let keepTaps: Bool
    /// 协作式取消：每个阶段结束后检查；取消时返回已完成的中间结果。
    var shouldCancel: () -> Bool = { false }

    init(params: RuntimePhotoParams, lutService sharedLUT: SpectralLUTService? = nil,
         keepTaps: Bool = true) {
        var resolved = params
        if resolved.settings.previewMode {
            resolved.enlarger.lensBlur = 0
            resolved.filmRender.dirCouplers.diffusionSizeUM = 0
            resolved.filmRender.grain.active = false
            resolved.filmRender.grain.particleAreaUM2 = 0
            resolved.filmRender.grain.blur = 0
            resolved.printRender.glare.blur = 0
            resolved.camera.lensBlurUM = 0
            resolved.scanner.lensBlur = 0
            resolved.scanner.unsharpMask = [0, 0]
        }
        ParamsDigest.applyFilmSpecifics(&resolved)
        if resolved.debug.lutMode {
            resolved.debug.deactivateSpatialEffects = true
            resolved.debug.deactivateStochasticEffects = true
            resolved.camera.autoExposure = false
            resolved.camera.exposureCompensationEV = 0
            resolved.enlarger.printExposureCompensation = false
            resolved.enlarger.printExposure = 1.0
            resolved.filmRender.halation.boostEV = 0
            resolved.scanner.whiteCorrection = false
            resolved.scanner.blackCorrection = false
            resolved.scanner.unsharpMask = [0, 0]
        }
        if resolved.debug.deactivateSpatialEffects {
            resolved.filmRender.halation.active = false
            resolved.filmRender.halation.scatterCoreUM = [0, 0, 0]
            resolved.filmRender.halation.scatterTailUM = [0, 0, 0]
            resolved.filmRender.halation.halationFirstSigmaUM = [0, 0, 0]
            resolved.filmRender.dirCouplers.diffusionSizeUM = 0
            resolved.filmRender.grain.blur = 0
            resolved.filmRender.grain.blurDyeCloudsUM = 0
            resolved.printRender.glare.blur = 0
            resolved.camera.lensBlurUM = 0
            resolved.enlarger.lensBlur = 0
            resolved.enlarger.diffusionFilter.active = false
            resolved.camera.diffusionFilter.active = false
            resolved.scanner.lensBlur = 0
            resolved.scanner.unsharpMask = [0, 0]
        }
        if resolved.debug.deactivateStochasticEffects {
            resolved.filmRender.grain.active = false
            resolved.printRender.glare.active = false
        }
        if resolved.settings.neutralPrintFiltersFromDatabase,
           let filters = NeutralPrintFilters.lookup(
               filmStock: resolved.film.info.stock,
               printStock: resolved.print.info.stock,
               illuminant: resolved.enlarger.illuminant
           ) {
            resolved.enlarger.cFilterNeutral = filters.c
            resolved.enlarger.mFilterNeutral = filters.m
            resolved.enlarger.yFilterNeutral = filters.y
        }
        self.params = resolved
        self.keepTaps = keepTaps
        self.lutService = sharedLUT ?? SpectralLUTService(resolution: resolved.settings.lutResolution)
        self.lutService.updateResolution(resolved.settings.lutResolution)
        self.enlargerService = EnlargerService(params: resolved.enlarger)
        self.colorReference = ColorReferenceService(
            film: resolved.film, printProfile: resolved.print,
            densityMin: resolved.filmRender.grain.densityMin,
            blackCorrection: resolved.scanner.blackCorrection,
            whiteCorrection: resolved.scanner.whiteCorrection,
            blackLevel: resolved.scanner.blackLevel,
            whiteLevel: resolved.scanner.whiteLevel,
            scanFilm: resolved.io.scanFilm,
            outputColorSpace: resolved.io.outputColorSpace,
            outputCCTFEncoding: resolved.io.outputCCTFEncoding
        )
        self.filming = FilmingStage(
            film: resolved.film, filmRender: resolved.filmRender, camera: resolved.camera,
            io: resolved.io, settings: resolved.settings, lutService: lutService,
            enlargerService: enlargerService, colorReference: colorReference
        )
        self.printing = PrintingStage(
            film: resolved.film, filmRender: resolved.filmRender, printProfile: resolved.print,
            printRender: resolved.printRender, enlarger: resolved.enlarger, settings: resolved.settings,
            lutService: lutService, enlargerService: enlargerService, colorReference: colorReference
        )
        self.scanning = ScanningStage(
            film: resolved.film, filmRender: resolved.filmRender, printProfile: resolved.print,
            printRender: resolved.printRender, scanner: resolved.scanner, io: resolved.io,
            settings: resolved.settings, lutService: lutService, colorReference: colorReference
        )
    }

    func process(_ input: ImageRGB, progress: ((String, Int, Int) -> Void)? = nil) -> PipelineResult {
        let total = params.io.scanFilm ? 4 : 6
        var step = 0
        func advance(_ label: String) {
            step += 1
            progress?(label, step, total)
        }
        let empty = ImageRGB(width: 0, height: 0)
        let rgbIn = keepTaps ? input : empty
        let pre = preprocess(input)
        advance("preprocess")
        if shouldCancel() {
            return PipelineResult(rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                                   logEFilm: empty, cmyFilm: empty,
                                   logEPrint: nil, cmyPrint: nil, rgbOut: pre)
        }
        let logFilm = filming.expose(pre)
        advance("filming.expose")
        if shouldCancel() {
            return PipelineResult(rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                                   logEFilm: keepTaps ? logFilm : empty, cmyFilm: empty,
                                   logEPrint: nil, cmyPrint: nil, rgbOut: pre)
        }
        let cmyFilm = filming.develop(logFilm)
        advance("filming.develop")
        if shouldCancel() {
            return PipelineResult(rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                                   logEFilm: keepTaps ? logFilm : empty,
                                   cmyFilm: keepTaps ? cmyFilm : empty,
                                   logEPrint: nil, cmyPrint: nil, rgbOut: cmyFilm)
        }
        if params.io.scanFilm {
            let out = scanning.scan(densityChannels: cmyFilm).sanitizedNonFinite()
            advance("scanning.scan_film")
            return PipelineResult(
                rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                logEFilm: keepTaps ? logFilm : empty,
                cmyFilm: keepTaps ? cmyFilm : empty,
                logEPrint: nil, cmyPrint: nil, rgbOut: out
            )
        }
        let logPrint = printing.expose(cmyFilmDensity: cmyFilm)
        advance("printing.expose")
        if shouldCancel() {
            return PipelineResult(rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                                   logEFilm: keepTaps ? logFilm : empty,
                                   cmyFilm: keepTaps ? cmyFilm : empty,
                                   logEPrint: keepTaps ? logPrint : empty,
                                   cmyPrint: nil, rgbOut: cmyFilm)
        }
        let cmyPrint = printing.develop(logRaw: logPrint)
        advance("printing.develop")
        if shouldCancel() {
            return PipelineResult(rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
                                   logEFilm: keepTaps ? logFilm : empty,
                                   cmyFilm: keepTaps ? cmyFilm : empty,
                                   logEPrint: keepTaps ? logPrint : empty,
                                   cmyPrint: keepTaps ? cmyPrint : empty, rgbOut: cmyPrint)
        }
        let out = scanning.scan(densityChannels: cmyPrint).sanitizedNonFinite()
        advance("scanning.scan_print")
        return PipelineResult(
            rgbIn: rgbIn, rgbPre: keepTaps ? pre : empty,
            logEFilm: keepTaps ? logFilm : empty,
            cmyFilm: keepTaps ? cmyFilm : empty,
            logEPrint: keepTaps ? logPrint : empty,
            cmyPrint: keepTaps ? cmyPrint : empty, rgbOut: out
        )
    }

    private func preprocess(_ input: ImageRGB) -> ImageRGB {
        var image = input
        image = filming.autoExposure(image)
        if params.io.crop {
            image = Resize.crop(image, center: params.io.cropCenter, size: params.io.cropSize)
        }
        let longEdge = max(image.width, image.height)
        filming.pixelSizeUM = params.camera.filmFormatMM * 1000 / Double(longEdge)
        if params.io.upscaleFactor != 1 {
            filming.pixelSizeUM /= params.io.upscaleFactor
            image = Resize.upscale(image, factor: params.io.upscaleFactor)
        }
        printing.pixelSizeUM = filming.pixelSizeUM
        return image
    }
}

