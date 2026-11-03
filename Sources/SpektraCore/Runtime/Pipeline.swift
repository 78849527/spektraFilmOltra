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

    init(params: RuntimePhotoParams) {
        self.params = params
        self.lutService = SpectralLUTService(resolution: params.settings.lutResolution)
        self.enlargerService = EnlargerService(params: params.enlarger)
        self.colorReference = ColorReferenceService(
            film: params.film, printProfile: params.print,
            densityMin: params.filmRender.grain.densityMin,
            blackCorrection: params.scanner.blackCorrection,
            whiteCorrection: params.scanner.whiteCorrection,
            blackLevel: params.scanner.blackLevel,
            whiteLevel: params.scanner.whiteLevel,
            scanFilm: params.io.scanFilm,
            outputColorSpace: params.io.outputColorSpace,
            outputCCTFEncoding: params.io.outputCCTFEncoding
        )
        self.filming = FilmingStage(
            film: params.film, filmRender: params.filmRender, camera: params.camera,
            io: params.io, settings: params.settings, lutService: lutService,
            enlargerService: enlargerService, colorReference: colorReference
        )
        self.printing = PrintingStage(
            film: params.film, filmRender: params.filmRender, printProfile: params.print,
            printRender: params.printRender, enlarger: params.enlarger, settings: params.settings,
            lutService: lutService, enlargerService: enlargerService, colorReference: colorReference
        )
        self.scanning = ScanningStage(
            film: params.film, filmRender: params.filmRender, printProfile: params.print,
            printRender: params.printRender, scanner: params.scanner, io: params.io,
            settings: params.settings, lutService: lutService, colorReference: colorReference
        )
    }

    func process(_ input: ImageRGB, progress: ((String, Int, Int) -> Void)? = nil) -> PipelineResult {
        let total = params.io.scanFilm ? 4 : 6
        var step = 0
        func advance(_ label: String) {
            step += 1
            progress?(label, step, total)
        }
        let rgbIn = input
        let pre = preprocess(input)
        advance("preprocess")
        let logFilm = filming.expose(pre)
        advance("filming.expose")
        let cmyFilm = filming.develop(logFilm)
        advance("filming.develop")
        if params.io.scanFilm {
            let out = scanning.scan(densityChannels: cmyFilm)
            advance("scanning.scan_film")
            return PipelineResult(
                rgbIn: rgbIn, rgbPre: pre, logEFilm: logFilm, cmyFilm: cmyFilm,
                logEPrint: nil, cmyPrint: nil, rgbOut: out
            )
        }
        let logPrint = printing.expose(cmyFilmDensity: cmyFilm)
        advance("printing.expose")
        let cmyPrint = printing.develop(logRaw: logPrint)
        advance("printing.develop")
        let out = scanning.scan(densityChannels: cmyPrint)
        advance("scanning.scan_print")
        return PipelineResult(
            rgbIn: rgbIn, rgbPre: pre, logEFilm: logFilm, cmyFilm: cmyFilm,
            logEPrint: logPrint, cmyPrint: cmyPrint, rgbOut: out
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
        if params.io.upscaleFactor > 1 {
            filming.pixelSizeUM /= params.io.upscaleFactor
        }
        return image
    }
}

