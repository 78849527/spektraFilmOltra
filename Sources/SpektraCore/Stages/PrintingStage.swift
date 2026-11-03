import Foundation

final class PrintingStage {
    private let film: Profile
    private let filmRender: FilmRenderParams
    private let printProfile: Profile
    private let printRender: PrintRenderParams
    private let enlarger: EnlargerParams
    private let settings: SettingsParams
    private let lutService: SpectralLUTService
    private let enlargerService: EnlargerService
    private let colorReference: ColorReferenceService

    init(film: Profile, filmRender: FilmRenderParams, printProfile: Profile, printRender: PrintRenderParams,
         enlarger: EnlargerParams, settings: SettingsParams, lutService: SpectralLUTService,
         enlargerService: EnlargerService, colorReference: ColorReferenceService) {
        self.film = film
        self.filmRender = filmRender
        self.printProfile = printProfile
        self.printRender = printRender
        self.enlarger = enlarger
        self.settings = settings
        self.lutService = lutService
        self.enlargerService = enlargerService
        self.colorReference = colorReference
    }

    func expose(cmyFilmDensity: ImageRGB) -> ImageRGB {
        let densityMin = filmRender.grain.densityMin
        let cmyBlackData = densityMin.map { -$0 }
        let cmyWhiteData = densityCurvesMax(film.data.densityCurves)
        colorReference.logRawPrintBlack = filmCMYToPrintLogRaw(ImageRGB(width: 1, height: 1, data: cmyBlackData))
        colorReference.logRawPrintWhite = filmCMYToPrintLogRaw(ImageRGB(width: 1, height: 1, data: cmyWhiteData))

        let logRaw = lutService.computeEnlarger(
            cmyData: cmyFilmDensity,
            function: { [unowned self] image in self.filmCMYToPrintLogRaw(image) },
            dataMin: cmyBlackData,
            dataMax: cmyWhiteData,
            useLUT: settings.useEnlargerLUT
        )
        var raw = logRaw.map { Vec3(pow(10, $0.x), pow(10, $0.y), pow(10, $0.z)) }
        let exposure = enlarger.printExposure
        raw = raw.map { $0 * exposure }
        let correction = colorReference.blackWhitePrintingExposureCorrection()
        raw = raw.map { $0 * correction }
        raw = applyDiffusion(raw, params: enlarger.diffusionFilter, pixelSizeUM: nil)
        return raw.map { Vec3(ImageMath.log10Safe($0.x), ImageMath.log10Safe($0.y), ImageMath.log10Safe($0.z)) }
    }

    func develop(logRaw: ImageRGB) -> ImageRGB {
        let curves = MorphCurves.applyPrintCurvesMorph(
            logExposure: printProfile.data.logExposure,
            model: printProfile.data.densityCurvesModel,
            params: printRender.densityCurvesMorph,
            profileType: printProfile.info.type
        )
        return DensityCurves.developSimple(
            logRaw: logRaw,
            logExposure: printProfile.data.logExposure,
            densityCurves: curves,
            gammaFactor: [1, 1, 1]
        )
    }

    private func filmCMYToPrintLogRaw(_ cmyFilmDensity: ImageRGB) -> ImageRGB {
        let logSensitivity = printProfile.data.logSensitivity
        var sensitivity = [[Double]](repeating: [0, 0, 0], count: logSensitivity.count)
        for w in 0..<logSensitivity.count {
            for c in 0..<3 {
                let value = pow(10, logSensitivity[w][c])
                sensitivity[w][c] = value.isFinite ? value : 0
            }
        }
        let lightSource = (try? Illuminants.standard(enlarger.illuminant)) ?? []
        let printIlluminant = enlargerService.filteredIlluminant(lightSource)
        let densitySpectral = DensityCurves.computeDensitySpectral(
            channelDensity: film.data.channelDensity,
            densityCMY: cmyFilmDensity,
            baseDensity: film.data.baseDensity
        )
        let pixelCount = cmyFilmDensity.width * cmyFilmDensity.height
        var rawValues = [Double](repeating: 0, count: pixelCount * 3)
        for p in 0..<pixelCount {
            let density = densitySpectral[p]
            for c in 0..<3 {
                var sum = 0.0
                for w in 0..<density.count {
                    let light = densityToLight(density[w], printIlluminant[w])
                    sum += light * sensitivity[w][c]
                }
                rawValues[p * 3 + c] = sum
            }
        }
        var raw = ImageRGB(width: cmyFilmDensity.width, height: cmyFilmDensity.height, data: rawValues)
        let factor = computeExposureFactorMidgray(sensitivity: sensitivity, printIlluminant: printIlluminant)
        raw = raw.map { $0 * factor }
        if enlarger.preflashExposure > 0 {
            let preflashIlluminant = enlargerService.preflashIlluminant(lightSource)
            let baseDensity = film.data.baseDensity
            for p in 0..<pixelCount {
                for c in 0..<3 {
                    var sum = 0.0
                    for w in 0..<baseDensity.count {
                        let light = densityToLight(baseDensity[w], preflashIlluminant[w])
                        sum += light * sensitivity[w][c]
                    }
                    raw.data[p * 3 + c] += sum * enlarger.preflashExposure
                }
            }
        }
        return raw.map { Vec3(ImageMath.log10Safe($0.x), ImageMath.log10Safe($0.y), ImageMath.log10Safe($0.z)) }
    }

    private func computeExposureFactorMidgray(sensitivity: [[Double]], printIlluminant: [Double]) -> Double {
        func factor(for densitySpectral: [[Double]]) -> Double {
            let density = densitySpectral[0]
            var raw = [Double](repeating: 0, count: 3)
            for c in 0..<3 {
                var sum = 0.0
                for w in 0..<density.count {
                    let light = densityToLight(density[w], printIlluminant[w])
                    sum += light * sensitivity[w][c]
                }
                raw[c] = max(sum, 1e-10)
            }
            let logMean = (log(raw[0]) + log(raw[1]) + log(raw[2])) / 3
            return 1.0 / exp(logMean)
        }

        guard let midgray = enlargerService.densitySpectralMidgray else { return 1 }
        let factorMidgray = factor(for: midgray)
        let factorComp: Double
        if let comp = enlargerService.densitySpectralMidgrayComp {
            factorComp = factor(for: comp)
        } else {
            factorComp = 1
        }
        if enlarger.printExposureCompensation && !enlarger.normalizePrintExposure {
            return factorComp / factorMidgray
        } else if enlarger.normalizePrintExposure && enlarger.printExposureCompensation {
            return factorComp
        } else if enlarger.normalizePrintExposure && !enlarger.printExposureCompensation {
            return factorMidgray
        }
        return 1
    }

    private func densityCurvesMax(_ curves: [[Double]]) -> [Double] {
        var result = [Double](repeating: -.infinity, count: 3)
        for row in curves {
            for c in 0..<3 where row[c].isFinite {
                result[c] = max(result[c], row[c])
            }
        }
        return result
    }

    private func densityToLight(_ density: Double, _ light: Double) -> Double {
        let value = pow(10, -density) * light
        return value.isFinite ? value : 0
    }

    private func applyDiffusion(_ image: ImageRGB, params: DiffusionFilterParams, pixelSizeUM: Double?) -> ImageRGB {
        SpatialEffects.diffusionFilter(image, params: params, pixelSizeUM: pixelSizeUM ?? 1)
    }
}

