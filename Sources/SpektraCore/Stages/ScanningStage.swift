import Foundation

final class ScanningStage {
    private let film: Profile
    private let filmRender: FilmRenderParams
    private let printProfile: Profile
    private let printRender: PrintRenderParams
    private let scanner: ScannerParams
    private let io: IOParams
    private let settings: SettingsParams
    private let lutService: SpectralLUTService
    private let colorReference: ColorReferenceService
    private let cmyToLogXYZ: (ImageRGB) -> ImageRGB

    init(film: Profile, filmRender: FilmRenderParams, printProfile: Profile, printRender: PrintRenderParams,
         scanner: ScannerParams, io: IOParams, settings: SettingsParams,
         lutService: SpectralLUTService, colorReference: ColorReferenceService) {
        self.film = film
        self.filmRender = filmRender
        self.printProfile = printProfile
        self.printRender = printRender
        self.scanner = scanner
        self.io = io
        self.settings = settings
        self.lutService = lutService
        self.colorReference = colorReference
        self.cmyToLogXYZ = ScanningStage.makeCmyToLogXYZ(film: film, printProfile: printProfile, io: io)
        colorReference.cmyToLogXYZ = self.cmyToLogXYZ
    }

    func scan(densityChannels: ImageRGB) -> ImageRGB {
        let rgb = densityToRGB(densityChannels, useLUT: settings.useScannerLUT)
        let blurred = applyBlurAndUnsharp(rgb)
        return applyCCTFEncoding(blurred)
    }

    private func densityToRGB(_ densityChannels: ImageRGB, useLUT: Bool) -> ImageRGB {
        let densityMin: [Double]
        let densityMax: [Double]
        let scanIlluminant: [Double]
        if io.scanFilm {
            densityMin = filmRender.grain.densityMin.map { -$0 }
            densityMax = densityCurvesMax(film.data.densityCurves)
            scanIlluminant = (try? Illuminants.standard(film.info.viewingIlluminant)) ?? []
        } else {
            densityMin = densityCurvesMin(printProfile.data.densityCurves)
            densityMax = densityCurvesMax(printProfile.data.densityCurves)
            scanIlluminant = (try? Illuminants.standard(printProfile.info.viewingIlluminant)) ?? []
        }

        let logXYZ = lutService.computeScanner(
            densityData: densityChannels,
            function: cmyToLogXYZ,
            dataMin: densityMin,
            dataMax: densityMax,
            useLUT: useLUT
        )
        var xyz = logXYZ.map { Vec3(pow(10, $0.x), pow(10, $0.y), pow(10, $0.z)) }
        xyz = colorReference.blackWhiteXYZCorrection(xyz)

        let cmfs = ColorDataStore.shared.cmfs
        let normalization = scanIlluminant.enumerated().reduce(0.0) { partial, item in
            partial + item.element * cmfs[item.offset][1]
        }
        var illuminantXYZ = Vec3(0, 0, 0)
        for w in 0..<min(scanIlluminant.count, cmfs.count) {
            illuminantXYZ.x += scanIlluminant[w] * cmfs[w][0]
            illuminantXYZ.y += scanIlluminant[w] * cmfs[w][1]
            illuminantXYZ.z += scanIlluminant[w] * cmfs[w][2]
        }
        illuminantXYZ = illuminantXYZ / normalization
        let illuminantXY = ColorMath.xyzToXY(illuminantXYZ)

        xyz = addGlare(xyz, illuminantXYZ: illuminantXYZ, glare: io.scanFilm ? nil : printRender.glare)
        var rgb = xyz.map { point in
            ColorMath.xyzToRGB(point, spaceName: io.outputColorSpace, illuminantXY: illuminantXY,
                               applyCCTFEncoding: false, adaptation: ColorMath.cat02)
        }
        rgb = compressRGB(rgb)
        return rgb
    }

    private func applyBlurAndUnsharp(_ rgb: ImageRGB) -> ImageRGB {
        var output = applyGaussianBlur(rgb, sigma: scanner.lensBlur)
        let sigma = scanner.unsharpMask[0]
        let amount = scanner.unsharpMask[1]
        if sigma > 0 && amount > 0 {
            output = applyUnsharpMask(output, sigma: sigma, amount: amount)
        }
        return output
    }

    private func applyCCTFEncoding(_ rgb: ImageRGB) -> ImageRGB {
        guard io.outputCCTFEncoding else { return rgb }
        let kind = ColorMath.cctfKind(for: io.outputColorSpace)
        return rgb.map { value in
            let converted = ColorMath.rgbToRGB(value, from: io.outputColorSpace, to: io.outputColorSpace)
            return Vec3(
                ColorMath.cctfEncode(converted.x, kind: kind),
                ColorMath.cctfEncode(converted.y, kind: kind),
                ColorMath.cctfEncode(converted.z, kind: kind)
            )
        }
    }

    private static func makeCmyToLogXYZ(film: Profile, printProfile: Profile, io: IOParams) -> (ImageRGB) -> ImageRGB {
        let scanFilm = io.scanFilm
        let channelDensity = scanFilm ? film.data.channelDensity : printProfile.data.channelDensity
        let baseDensity = scanFilm ? film.data.baseDensity : printProfile.data.baseDensity
        let scanIlluminant = (try? Illuminants.standard(
            scanFilm ? film.info.viewingIlluminant : printProfile.info.viewingIlluminant
        )) ?? []
        let cmfs = ColorDataStore.shared.cmfs
        let normalization = scanIlluminant.enumerated().reduce(0.0) { partial, item in
            partial + item.element * cmfs[item.offset][1]
        }
        return { densityCMY in
            let densitySpectral = DensityCurves.computeDensitySpectral(
                channelDensity: channelDensity, densityCMY: densityCMY, baseDensity: baseDensity
            )
            let pixelCount = densityCMY.width * densityCMY.height
            var output = [Double](repeating: 0, count: pixelCount * 3)
            for p in 0..<pixelCount {
                let density = densitySpectral[p]
                var xyz = Vec3(0, 0, 0)
                for w in 0..<min(density.count, scanIlluminant.count) {
                    let lightValue = pow(10, -density[w]) * scanIlluminant[w]
                    let light = lightValue.isFinite ? lightValue : 0
                    xyz.x += light * cmfs[w][0]
                    xyz.y += light * cmfs[w][1]
                    xyz.z += light * cmfs[w][2]
                }
                xyz = xyz / normalization
                output[p * 3] = ImageMath.log10Safe(xyz.x)
                output[p * 3 + 1] = ImageMath.log10Safe(xyz.y)
                output[p * 3 + 2] = ImageMath.log10Safe(xyz.z)
            }
            return ImageRGB(width: densityCMY.width, height: densityCMY.height, data: output)
        }
    }

    private func densityCurvesMax(_ curves: [[Double]]) -> [Double] {
        var result = [Double](repeating: -.infinity, count: 3)
        for row in curves {
            for c in 0..<3 where row[c].isFinite { result[c] = max(result[c], row[c]) }
        }
        return result
    }

    private func densityCurvesMin(_ curves: [[Double]]) -> [Double] {
        var result = [Double](repeating: .infinity, count: 3)
        for row in curves {
            for c in 0..<3 where row[c].isFinite { result[c] = min(result[c], row[c]) }
        }
        return result
    }

    private func applyGaussianBlur(_ image: ImageRGB, sigma: Double) -> ImageRGB {
        SpatialEffects.gaussianBlurUM(image, sigmaUM: sigma, pixelSizeUM: 1)
    }

    private func applyUnsharpMask(_ image: ImageRGB, sigma: Double, amount: Double) -> ImageRGB {
        SpatialEffects.applyUnsharpMask(image, sigma: sigma, amount: amount)
    }

    private func addGlare(_ xyz: ImageRGB, illuminantXYZ: Vec3, glare: GlareParams?) -> ImageRGB {
        Glare.addGlare(xyz, illuminantXYZ: illuminantXYZ, params: glare)
    }

    private func compressRGB(_ rgb: ImageRGB) -> ImageRGB {
        OutputGamutCompression.apply(
            rgb,
            algorithm: io.outputGamutCompressAlgorithm,
            knee: io.outputGamutCompressKnee,
            outputColorSpace: io.outputColorSpace
        )
    }
}

