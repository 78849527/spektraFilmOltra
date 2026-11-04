import Foundation
import AppKit

@main
@MainActor
struct HostSmoke {
    static func main() async throws {
        // 非有限像素回归：色域压缩不允许再因 NaN/Inf 索引陷阱崩溃。
        var edge = ImageRGB(width: 3, height: 1, data: [
            .nan, .infinity, -.infinity,
            1e300, -1e300, 0,
            0.18, 0.18, 0.18,
        ])
        for algorithm in ["cam16ucs", "oklch", "oklrab", "jzazbz", "aces_rgc"] {
            let out = OutputGamutCompression.apply(
                edge, algorithm: algorithm, knee: [0, 1, 6],
                outputColorSpace: "sRGB"
            )
            let finite = out.data.allSatisfy(\.isFinite)
            if !finite { throw NSError(domain: "smoke", code: 2, userInfo: [
                NSLocalizedDescriptionKey: "non-finite output from \(algorithm)"
            ]) }
        }
        edge.data[0] = 0
        edge.data[1] = 0
        edge.data[2] = 0

        let gradeReport = try runGradeSmoke()

        let args = ProcessInfo.processInfo.environment
        guard let rawPath = args["RAW_PATH"], FileManager.default.fileExists(atPath: rawPath) else {
            let data = try JSONSerialization.data(
                withJSONObject: ["edgeCompression": "finite", "raw": "skipped", "grade": gradeReport],
                options: [.sortedKeys, .prettyPrinted]
            )
            print(String(data: data, encoding: .utf8) ?? "{}")
            return
        }
        let rawURL = URL(fileURLWithPath: rawPath)
        let root = URL(fileURLWithPath: "/tmp/spektra_host_smoke")
        try? FileManager.default.removeItem(at: root)
        let store = LibraryStore(root: root)
        let photo = try store.importPhoto(from: rawURL)
        let host = EngineHost(store: store)

        host.select(photoID: photo.id)
        var waited = 0.0
        while host.previewImage == nil && waited < 180 {
            try await Task.sleep(nanoseconds: 100_000_000)
            waited += 0.1
            if host.previewImage == nil && waited > 30 && host.statusMessage.contains("无法读取") {
                throw NSError(domain: "smoke", code: 1, userInfo: [
                    NSLocalizedDescriptionKey: host.statusMessage
                ])
            }
        }
        guard host.previewImage != nil else {
            throw NSError(domain: "smoke", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "RAW preview never arrived: \(host.statusMessage)"
            ])
        }
        let firstElapsed = host.statusMessage
        let snapshot = host.editorSnapshot(for: photo.id)

        host.applyQuick("camera_exposure", 1.0)
        host.applyQuick("tonal_contrast", 40)
        var second = 0.0
        while (host.isRendering || host.renderPhase.isBusy) && second < 120 {
            try await Task.sleep(nanoseconds: 100_000_000)
            second += 0.1
        }

        let exportURL = URL(fileURLWithPath: "/tmp/spektra_host_smoke_export.tif")
        try? FileManager.default.removeItem(at: exportURL)
        host.exportCurrent(to: exportURL)
        var exportWait = 0.0
        while !FileManager.default.fileExists(atPath: exportURL.path) && exportWait < 300 {
            try await Task.sleep(nanoseconds: 200_000_000)
            exportWait += 0.2
        }
        let exported = FileManager.default.fileExists(atPath: exportURL.path)
        let size = (try? FileManager.default.attributesOfItem(
            atPath: exportURL.path)[.size] as? Int) ?? 0

        // 调色台整链：交接图 → 调色预览 → 暖调重渲 → 导出。
        host.beginGrade()
        let sourceWait = await wait(120) { host.gradeSourceReady }
        let firstGradeWait = await wait(120) {
            host.gradePreviewImage != nil && !host.gradePhase.isBusy
        }
        let warm = GradeRecipe(
            light: LightRecipe(contrast: 8, shadows: 10),
            color: ColorRecipe(temperature: 12, vibrance: 8),
            transparency: TransparencyRecipe(tonal: 18, color: 0)
        )
        host.setGradeRecipe(warm)
        let recipeWait = await wait(120) {
            !host.gradePhase.isBusy && host.gradeAnalysis != nil
        }

        let gradeDirectory = URL(fileURLWithPath: "/tmp/spektra_host_smoke_grade")
        try? FileManager.default.removeItem(at: gradeDirectory)
        host.exportGrade(ExportSettings(
            format: .tiff16, longEdge: 1200,
            directory: gradeDirectory, filenameTemplate: "{name}-grade-smoke"
        ))
        var gradeExportWait = 0.0
        var gradeFile: URL?
        while gradeExportWait < 400 {
            let contents = (try? FileManager.default.contentsOfDirectory(
                at: gradeDirectory, includingPropertiesForKeys: nil
            )) ?? []
            if let first = contents.first {
                gradeFile = first
                break
            }
            try await Task.sleep(nanoseconds: 200_000_000)
            gradeExportWait += 0.2
        }
        var gradeBytes = 0
        if let gradeFile,
           let attributes = try? FileManager.default.attributesOfItem(atPath: gradeFile.path),
           let value = attributes[.size] as? Int {
            gradeBytes = value
        }

        let report: [String: Any] = [
            "raw": rawURL.lastPathComponent,
            "edgeCompression": "finite",
            "previewReady": host.previewImage != nil,
            "firstStatus": firstElapsed,
            "asSeconds": waited,
            "quickAxes": snapshot.quickGroups.flatMap(\.axes).count,
            "proRows": snapshot.proPages.flatMap(\.groups).flatMap(\.rows).count,
            "renderAfterEdit": second,
            "exported": exported,
            "exportWait": exportWait,
            "exportBytes": size,
            "status": host.statusMessage,
            "grade": gradeReport,
            "gradeSourceWait": sourceWait,
            "gradeFirstPreviewWait": firstGradeWait,
            "gradeRecipeWait": recipeWait,
            "gradePreviewReady": host.gradePreviewImage != nil,
            "gradeExportWait": gradeExportWait,
            "gradeExportBytes": gradeBytes,
            "gradeExportPath": gradeFile?.lastPathComponent ?? "",
            "gradeAnalysis": host.gradeAnalysis?.summary ?? "",
        ]
        let data = try JSONSerialization.data(withJSONObject: report,
                                              options: [.sortedKeys, .prettyPrinted])
        print(String(data: data, encoding: .utf8) ?? "{}")
    }

    private static func wait(_ timeout: Double, _ condition: () -> Bool) async -> Double {
        var elapsed = 0.0
        while !condition() && elapsed < timeout {
            try? await Task.sleep(nanoseconds: 100_000_000)
            elapsed += 0.1
        }
        return elapsed
    }

    /// 调色引擎回归：identity 配方与 sRGB 编码一致、暖调输出有限、identity LUT 不改变像素。
    private static func runGradeSmoke() throws -> [String: Any] {
        let width = 32
        let height = 32
        var data = [Double](repeating: 0, count: width * height * 3)
        for y in 0..<height {
            for x in 0..<width {
                let index = (y * width + x) * 3
                data[index] = Double(x) / Double(width - 1)
                data[index + 1] = Double(y) / Double(height - 1)
                data[index + 2] = Double((x + y) % 17) / 17.0
            }
        }
        let source = ImageRGB(width: width, height: height, data: data)
        let identity = try GradeEngine.render(source, recipe: GradeRecipe(), analyze: false)

        func encode(_ value: Double) -> Double {
            let positive = max(value, 0)
            return positive <= 0.0031308
                ? positive * 12.92
                : 1.055 * pow(positive, 1.0 / 2.4) - 0.055
        }
        var identityDiff = 0.0
        for i in 0..<data.count {
            let expected = min(max(encode(data[i]), 0), 1)
            identityDiff = max(identityDiff, abs(identity.image.data[i] - expected))
        }

        let warm = GradeRecipe(
            light: LightRecipe(contrast: 6, highlights: -8),
            color: ColorRecipe(
                temperature: 12, vibrance: 8,
                grading: ColorGrading(
                    shadows: GradeZone(hue: 30, saturation: 8),
                    highlights: GradeZone(hue: 40, saturation: 18)
                )
            ),
            transparency: TransparencyRecipe(tonal: 10, color: 0)
        )
        let warmResult = try GradeEngine.render(source, recipe: warm, analyze: false)
        let warmFinite = warmResult.image.data.allSatisfy(\.isFinite)

        let lutURL = URL(fileURLWithPath: "/tmp/spektra_smoke_identity.cube")
        let cube = """
        LUT_3D_SIZE 2
        0 0 0
        1 0 0
        0 1 0
        1 1 0
        0 0 1
        1 0 1
        0 1 1
        1 1 1
        """
        try cube.write(to: lutURL, atomically: true, encoding: .utf8)
        let lutRecipe = GradeRecipe(lut: LutRecipe(path: lutURL.path, strength: 100))
        let lutResult = try GradeEngine.render(source, recipe: lutRecipe, analyze: false)
        var lutDiff = 0.0
        for i in 0..<data.count {
            lutDiff = max(lutDiff, abs(lutResult.image.data[i] - identity.image.data[i]))
        }

        return [
            "identityMaxDiff": identityDiff,
            "warmFinite": warmFinite,
            "lutIdentityMaxDiff": lutDiff,
        ]
    }
}
