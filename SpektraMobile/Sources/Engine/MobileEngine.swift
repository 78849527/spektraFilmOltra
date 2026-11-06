import Foundation
import SwiftUI

/// 移动端状态中枢：照片库、导入、缩略图、显影/调色会话。
/// 照片库放在 `Spektrafilm/MobileLibrary`，与桌面版库互不干扰。
@MainActor
final class MobileEngine: ObservableObject {
    struct ImportReport {
        var imported: Int = 0
        var rejected: Int = 0
        var firstID: String?
        /// 第一张被拒的原因（文件名 / 错误文案），用于把失败原因透出到 toast 与日志。
        var reason: String = ""
    }

    let store: LibraryStore

    @Published private(set) var photos: [MPhoto] = []
    @Published private(set) var developSession: MobileDevelopSession?
    @Published private(set) var gradeSession: MobileGradeSession?
    @Published private(set) var isImporting = false

    private let thumbnailQueue = DispatchQueue(label: "spektra.mobile.thumb", qos: .utility)

    init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Spektrafilm/MobileLibrary", isDirectory: true)
        store = LibraryStore(root: base)
        refreshPhotos()
        warmThumbnails()
        importDebugFileIfNeeded()
    }

    /// 验收脚本用：`--import <绝对路径>` 在启动时把指定 RAW 入库，省掉手工点「导入」。
    /// 只在显式传入该参数时生效，Release 构建也保留（自动化截图需要）。
    private func importDebugFileIfNeeded() {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "--import"), args.indices.contains(index + 1) else { return }
        let path = args[index + 1]
        guard FileManager.default.fileExists(atPath: path) else { return }
        _ = importPhotos([URL(fileURLWithPath: path)])
    }

    // MARK: - 照片库

    func refreshPhotos() {
        photos = store.photos
            .sorted { $0.importedAt > $1.importedAt }
            .map(makePhoto)
    }

    @discardableResult
    func importPhotos(_ urls: [URL]) -> ImportReport {
        var report = ImportReport()
        isImporting = true
        for url in urls {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                let photo = try store.importPhoto(from: url)
                report.imported += 1
                report.firstID = report.firstID ?? photo.id
                generateThumbnail(for: photo)
            } catch {
                report.rejected += 1
                if report.reason.isEmpty {
                    report.reason = "\(url.lastPathComponent)：\((error as NSError).localizedDescription)"
                }
                NSLog("MImport rejected %@ — %@", url.lastPathComponent,
                      (error as NSError).localizedDescription)
            }
        }
        isImporting = false
        refreshPhotos()
        return report
    }

    func remove(photoID: String) {
        if let photo = store.photos.first(where: { $0.id == photoID }),
           let thumbnail = photo.thumbnailPath {
            MThumbnailCache.shared.remove(path: thumbnail)
        }
        try? store.remove(id: photoID)
        refreshPhotos()
    }

    func setFavorite(photoID: String, value: Bool) {
        mutate(photoID: photoID) { $0.favorite = value }
    }

    func setColorLabel(photoID: String, label: MColorLabel?) {
        mutate(photoID: photoID) { $0.colorLabel = label?.rawValue }
    }

    private func mutate(photoID: String, _ body: (inout LibraryPhoto) -> Void) {
        guard let photo = store.photos.first(where: { $0.id == photoID }) else { return }
        var copy = photo
        body(&copy)
        try? store.update(copy)
        refreshPhotos()
    }

    private func makePhoto(_ photo: LibraryPhoto) -> MPhoto {
        let ev = photo.edit.camera.exposureCompensationEV
        let exposure: String
        if abs(ev) < 0.05 {
            exposure = "0"
        } else {
            exposure = String(format: "%+.1f EV", ev)
        }
        return MPhoto(
            id: photo.id,
            filename: photo.filename,
            film: MobileCatalog.filmName(photo.edit.filmStock),
            paper: MobileCatalog.paperName(photo.edit.printStock),
            dimensions: photo.width > 0 ? "\(photo.width)×\(photo.height)" : "",
            isRaw: photo.isRaw,
            favorite: photo.favorite,
            color: photo.colorLabel.flatMap(MColorLabel.init(rawValue:)),
            isGraded: !photo.edit.quickIntents.isEmpty,
            exposure: exposure,
            thumbnailURL: store.thumbnailURL(for: photo)
        )
    }

    private func warmThumbnails() {
        for photo in store.photos where photo.thumbnailPath == nil {
            generateThumbnail(for: photo)
        }
    }

    private func generateThumbnail(for photo: LibraryPhoto) {
        guard photo.thumbnailPath == nil else { return }
        let id = photo.id
        let url = store.originalURL(for: photo)
        let edit = photo.edit
        thumbnailQueue.async { [weak self] in
            guard let self else { return }
            guard let loaded = try? ImageLoader.load(url: url, maxSize: 320),
                  var params = try? edit.runtimeParams() else { return }
            params.io.inputColorSpace = loaded.colorSpace
            params.io.inputCCTFDecoding = loaded.cctfDecoding
            let small = Resize.smallPreview(loaded.image, maxSize: 320)
            let output = SimulationPipeline(params: params, keepTaps: false).process(small).rgbOut
            Task { @MainActor in
                try? self.store.writeThumbnail(id: id, image: output)
                self.refreshPhotos()
            }
        }
    }

    // MARK: - 显影会话

    @discardableResult
    func openDevelop(photoID: String) -> MobileDevelopSession? {
        guard let photo = store.photos.first(where: { $0.id == photoID }) else { return nil }
        developSession?.cancel()
        let session = MobileDevelopSession(photo: photo, store: store)
        session.onPersist = { [weak self] _ in self?.refreshPhotos() }
        developSession = session
        session.start()
        return session
    }

    func closeDevelop() {
        developSession?.finish()
        developSession?.cancel()
        developSession = nil
        refreshPhotos()
    }

    // MARK: - 调色会话

    /// 从主页直接进调色台时，临时建一个不显示的显影会话，只为产出交接像素。
    func openGrade(photoID: String, entry: MGradeEntry) -> MobileGradeSession? {
        guard let photo = store.photos.first(where: { $0.id == photoID }) else { return nil }
        let develop: MobileDevelopSession
        if let current = developSession, current.photoID == photoID {
            develop = current
            current.finish()
        } else {
            develop = MobileDevelopSession(photo: photo, store: store)
            develop.start()
        }
        let grade = MobileGradeSession(photo: photo, store: store, develop: develop)
        gradeSession = grade
        grade.start()
        return grade
    }

    func closeGrade() {
        gradeSession?.cancel()
        gradeSession = nil
    }
}
