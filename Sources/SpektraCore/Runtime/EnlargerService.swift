import Foundation

struct EnlargerParams {
    var illuminant: String = "TH-KG3"
    var printExposure: Double = 1.0
    var printExposureCompensation: Bool = true
    var normalizePrintExposure: Bool = true
    var yFilterShift: Double = 0
    var mFilterShift: Double = 0
    var yFilterNeutral: Double = 55
    var mFilterNeutral: Double = 65
    var cFilterNeutral: Double = 0
    var lensBlur: Double = 0
    var diffusionFilter = DiffusionFilterParams()
    var preflashExposure: Double = 0
    var preflashYFilterShift: Double = 0
    var preflashMFilterShift: Double = 0
}

final class EnlargerService {
    var densitySpectralMidgray: [[Double]]?
    var densitySpectralMidgrayComp: [[Double]]?
    let printExposureCompensation: Bool
    private let params: EnlargerParams

    init(params: EnlargerParams) {
        self.params = params
        self.printExposureCompensation = params.printExposureCompensation
    }

    func filteredIlluminant(_ lightSource: [Double]) -> [Double] {
        EnlargerFilters.applyCC(lightSource, cc: [
            params.cFilterNeutral,
            params.mFilterNeutral + params.mFilterShift,
            params.yFilterNeutral + params.yFilterShift,
        ])
    }

    func neutralIlluminant(_ lightSource: [Double]) -> [Double] {
        EnlargerFilters.applyCC(lightSource, cc: [
            params.cFilterNeutral,
            params.mFilterNeutral,
            params.yFilterNeutral,
        ])
    }

    func preflashIlluminant(_ lightSource: [Double]) -> [Double] {
        EnlargerFilters.applyCC(lightSource, cc: [
            params.cFilterNeutral,
            params.mFilterNeutral + params.preflashMFilterShift,
            params.yFilterNeutral + params.preflashYFilterShift,
        ])
    }
}

