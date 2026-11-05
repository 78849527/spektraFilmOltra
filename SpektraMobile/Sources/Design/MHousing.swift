import SwiftUI
#if os(iOS)
import UIKit
#endif

/// 顶部开孔形态：灵动岛 / 刘海 / 没有开孔。
enum MHousingKind: String {
    case island
    case notch
    case none
    case auto
}

private struct MHousingKey: EnvironmentKey {
    static let defaultValue: MHousingKind = .auto
}

extension EnvironmentValues {
    var mHousing: MHousingKind {
        get { self[MHousingKey.self] }
        set { self[MHousingKey.self] = newValue }
    }
}

enum MDeviceHousing {
    /// 显式指定优先（宿主预览用）；真机上按顶部安全区和机型判断。
    static func resolved(_ explicit: MHousingKind) -> MHousingKind {
        if explicit != .auto { return explicit }
        #if os(iOS)
        return detect()
        #else
        return .island
        #endif
    }

    #if os(iOS)
    private static func detect() -> MHousingKind {
        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first,
            let window = scene.windows.first else { return .none }
        if window.safeAreaInsets.top < 20 { return .none }
        return hasIsland(machineIdentifier()) ? .island : .notch
    }

    /// 机型标识：iPhone15,2/15,3 起是 14 Pro 系列；iPhone16,* 起是 15 Pro 与后续机型。
    private static func hasIsland(_ model: String) -> Bool {
        let stripped = model.replacingOccurrences(of: "iPhone", with: "")
        let parts = stripped.split(separator: ",")
        guard parts.count == 2, let major = Int(parts[0]), let minor = Int(parts[1]) else {
            return true
        }
        if major >= 16 { return true }
        if major == 15 { return minor >= 2 }
        return false
    }

    private static func machineIdentifier() -> String {
        var info = utsname()
        uname(&info)
        return Mirror(reflecting: info.machine).children.reduce(into: "") { result, child in
            if let value = child.value as? Int8, value != 0 {
                result.append(Character(UnicodeScalar(UInt8(value))))
            }
        }
    }
    #endif
}
