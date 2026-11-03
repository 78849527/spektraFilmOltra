import Foundation

func log(_ text: String) {
    FileHandle.standardError.write((text + "\n").data(using: .utf8)!)
}

@main
struct CoreSmoke {
    static func main() throws {
        log("start")
        let store = ColorDataStore.shared
        log("cmfs \(store.cmfs.count) \(store.cmfs.first?.count ?? 0)")
        log("spaces \(store.spaces.keys.sorted())")
        let profile = try ProfileStore.load("kodak_portra_400")
        log("profile \(profile.info.name) \(profile.data.wavelengths.count) \(profile.data.logSensitivity.count) \(profile.data.densityCurves.count)")
        log("lut \(SpectralUpsampling.lut.size) \(SpectralUpsampling.lut.channels)")
        let sensitivity = profile.data.logSensitivity.map { row in
            row.map { value in
                let v = pow(10.0, value)
                return v.isFinite ? v : 0
            }
        }
        var adaptation = profile.hanatos2025Adaptation
        adaptation.applyWindow = true
        adaptation.applySurface = false
        let tcLUT = SpectralUpsampling.computeHanatosTCPLUT(sensitivity: sensitivity, adaptation: adaptation)
        let samples: [(String, Vec3)] = [
            ("gray18", Vec3(0.184, 0.184, 0.184)),
            ("white", Vec3(1, 1, 1)),
            ("red", Vec3(1, 0, 0)),
            ("green", Vec3(0, 1, 0)),
            ("blue", Vec3(0, 0, 1)),
            ("skin", Vec3(0.65, 0.42, 0.32)),
        ]
        for (name, rgb) in samples {
            let raw = SpectralUpsampling.rgbToRawHanatos(
                rgb, sensitivity: sensitivity, colorSpace: "ProPhoto RGB",
                applyCCTFDecoding: false, referenceIlluminant: profile.info.referenceIlluminant,
                tcLUT: tcLUT
            )
            log("\(name) \(String(format: "%.9f %.9f %.9f", raw.x, raw.y, raw.z))")
        }
    }
}

