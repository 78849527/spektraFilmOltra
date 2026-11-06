import Foundation
import ImageIO

/// 单张照片的非破坏编辑状态（不含 Profile 本体，只存 stock 名）。
struct PhotoEdit: Codable {
    var filmStock: String = "kodak_portra_400"
    var printStock: String = "kodak_supra_endura"
    var camera = CameraParams()
    var enlarger = EnlargerParams()
    var filmRender = FilmRenderParams()
    var printRender = PrintRenderParams()
    var scanner = ScannerParams()
    var io = IOParams()
    var settings = SettingsParams()
    var debug = DebugParams()
    var quickIntents: [String: Double] = [:]

    func runtimeParams() throws -> RuntimePhotoParams {
        var params = RuntimePhotoParams(
            film: try ProfileStore.load(filmStock),
            print: try ProfileStore.load(printStock)
        )
        params.camera = camera
        params.enlarger = enlarger
        params.filmRender = filmRender
        params.printRender = printRender
        params.scanner = scanner
        params.io = io
        params.settings = settings
        params.debug = debug
        return params
    }
}

struct LibraryPhoto: Codable, Identifiable, Hashable {
    var id: String
    var filename: String
    var originalPath: String
    var thumbnailPath: String?
    var width: Int
    var height: Int
    var isRaw: Bool
    var favorite: Bool = false
    var colorLabel: String?
    var importedAt: Date = Date()
    var edit = PhotoEdit()
    /// 快速控制的基线（编码后的 PhotoEdit）；缺失时以当前 edit 为准。
    var quickBaselineData: Data? = nil

    static func == (lhs: LibraryPhoto, rhs: LibraryPhoto) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }

    func makeParams() throws -> RuntimePhotoParams { try edit.runtimeParams() }
}

/// 照片库：索引持久化 + 原图拷贝 + 缩略图路径。
final class LibraryStore {
    private(set) var photos: [LibraryPhoto] = []
    let root: URL
    private let ioQueue = DispatchQueue(label: "spektrafilm.library.io", qos: .utility)
    private var indexURL: URL { root.appendingPathComponent("index.json") }
    private var originalsURL: URL { root.appendingPathComponent("Originals", isDirectory: true) }
    private var thumbnailsURL: URL { root.appendingPathComponent("Thumbnails", isDirectory: true) }

    init(root: URL? = nil) {
        let base = root ?? FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        )[0].appendingPathComponent("Spektrafilm/Library", isDirectory: true)
        self.root = base
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: originalsURL, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: thumbnailsURL, withIntermediateDirectories: true)
        reload()
    }

    func reload() {
        guard let data = try? Data(contentsOf: indexURL),
              let decoded = try? JSONDecoder().decode([LibraryPhoto].self, from: data) else {
            photos = []
            return
        }
        // 显影台只接受 RAW；旧索引里的 JPEG/TIFF 不再进入库。
        photos = decoded.filter {
            ImageLoader.rawSuffixes.contains(
                URL(fileURLWithPath: $0.originalPath).pathExtension.lowercased()
            )
        }
    }

    func save() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(photos)
        try data.write(to: indexURL)
    }

    /// 参数类更新：先快照，再异步写索引。主线程不再做 JSON 编码与磁盘 IO，
    /// 拖动滑条时每 0.7 秒一次的落盘不会再卡住手势。
    private func persistIndexAsync() {
        let snapshot = photos
        let url = indexURL
        ioQueue.async {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            guard let data = try? encoder.encode(snapshot) else { return }
            try? data.write(to: url, options: .atomic)
        }
    }

    func originalURL(for photo: LibraryPhoto) -> URL {
        Self.resolve(photo.originalPath, root: root, folder: "Originals")
    }

    func thumbnailURL(for photo: LibraryPhoto) -> URL? {
        photo.thumbnailPath.map { Self.resolve($0, root: root, folder: "Thumbnails") }
    }

    /// 索引里存相对路径（Originals/…）；老索引是绝对路径，容器目录一变就失效，
    /// 这里按目录段重新定位，避免 App 更新后整库「找不到原图」。
    static func resolve(_ storedPath: String, root: URL, folder: String) -> URL {
        if storedPath.hasPrefix("/") {
            let absolute = URL(fileURLWithPath: storedPath)
            if FileManager.default.fileExists(atPath: absolute.path) { return absolute }
            if let range = storedPath.range(of: "/\(folder)/") {
                let name = String(storedPath[range.upperBound...])
                return root.appendingPathComponent(folder).appendingPathComponent(name)
            }
            return absolute
        }
        return root.appendingPathComponent(storedPath)
    }

    @discardableResult
    func importPhoto(from source: URL) throws -> LibraryPhoto {
        let ext = source.pathExtension.lowercased()
        guard ImageLoader.rawSuffixes.contains(ext) else {
            throw NSError(domain: "Spektrafilm.Library", code: 2,
                          userInfo: [NSLocalizedDescriptionKey:
                            "显影台只支持 RAW，拒绝导入 \(source.lastPathComponent)"])
        }
        let detected = ImageLoader.detectColorSpace(url: source)
        let dimensions = Self.pixelSize(url: source)
        // 同名 + 同尺寸视为同一张：重复导入不再产生副本（相册选取与验收脚本都会重复触发）。
        if let existing = photos.first(where: {
            $0.filename == source.lastPathComponent
                && $0.width == dimensions.width && $0.height == dimensions.height
        }) {
            return existing
        }
        let id = UUID().uuidString
        let destination = originalsURL.appendingPathComponent("\(id).\(ext)")
        try FileManager.default.copyItem(at: source, to: destination)
        var edit = PhotoEdit()
        edit.io.inputColorSpace = detected.space
        edit.io.inputCCTFDecoding = detected.cctfDecoding
        let photo = LibraryPhoto(
            id: id,
            filename: source.lastPathComponent,
            originalPath: "Originals/\(id).\(ext)",
            thumbnailPath: nil,
            width: dimensions.width,
            height: dimensions.height,
            isRaw: true,
            edit: edit
        )
        photos.append(photo)
        try save()
        return photo
    }

    func update(_ photo: LibraryPhoto) throws {
        if let index = photos.firstIndex(where: { $0.id == photo.id }) {
            photos[index] = photo
            persistIndexAsync()
        }
    }

    func remove(id: String) throws {
        guard let index = photos.firstIndex(where: { $0.id == id }) else { return }
        let photo = photos[index]
        try? FileManager.default.removeItem(at: originalURL(for: photo))
        if let thumbnail = photo.thumbnailPath {
            try? FileManager.default.removeItem(at: Self.resolve(thumbnail, root: root, folder: "Thumbnails"))
        }
        photos.remove(at: index)
        try save()
    }

    func writeThumbnail(id: String, image: ImageRGB) throws {
        guard let index = photos.firstIndex(where: { $0.id == id }) else { return }
        let url = thumbnailsURL.appendingPathComponent("\(id).png")
        try ImageExport.save(image, to: url, bitDepth: 8,
                             colorSpace: photos[index].edit.io.outputColorSpace)
        photos[index].thumbnailPath = "Thumbnails/\(id).png"
        persistIndexAsync()
    }

    static func pixelSize(url: URL) -> (width: Int, height: Int) {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)
                as? [String: Any] else { return (0, 0) }
        let width = properties[kCGImagePropertyPixelWidth as String] as? Int ?? 0
        let height = properties[kCGImagePropertyPixelHeight as String] as? Int ?? 0
        return (width, height)
    }
}
