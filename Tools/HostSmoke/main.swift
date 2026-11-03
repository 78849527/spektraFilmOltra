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

        let args = ProcessInfo.processInfo.environment
        guard let rawPath = args["RAW_PATH"], FileManager.default.fileExists(atPath: rawPath) else {
            print(#"{"edgeCompression":"finite","raw":"skipped"}"#)
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
        while host.isRendering && second < 120 {
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
        ]
        let data = try JSONSerialization.data(withJSONObject: report,
                                              options: [.sortedKeys, .prettyPrinted])
        print(String(data: data, encoding: .utf8) ?? "{}")
    }
}
