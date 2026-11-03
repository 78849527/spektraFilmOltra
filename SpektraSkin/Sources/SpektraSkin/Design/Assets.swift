import AppKit
import SwiftUI

private final class SkinAssetCache {
    static let shared = NSCache<NSString, NSImage>()
}

extension Image {
    init(skinAsset name: String) {
        let key = name as NSString
        if let cached = SkinAssetCache.shared.object(forKey: key) {
            self.init(nsImage: cached)
            return
        }

        #if SWIFT_PACKAGE
        let bundles: [Bundle] = [.main, .module]
        #else
        let bundles: [Bundle] = [.main]
        #endif

        var image: NSImage?
        for bundle in bundles {
            for subdirectory in [nil, "SamplePhotos", "Resources/SamplePhotos"] as [String?] {
                if let url = bundle.url(forResource: name, withExtension: "jpg", subdirectory: subdirectory),
                   let loaded = NSImage(contentsOf: url) {
                    image = loaded
                    break
                }
            }
            if image != nil { break }
        }

        guard let image else {
            self.init(systemName: "photo")
            return
        }
        SkinAssetCache.shared.setObject(image, forKey: key)
        self.init(nsImage: image)
    }
}
