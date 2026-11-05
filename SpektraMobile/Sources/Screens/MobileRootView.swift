import SwiftUI

struct MobileRootView: View {
    @StateObject private var engine = MobileEngine()
    @Environment(\.mHousing) private var housingSetting

    @State private var screen: MScreen = .home
    @State private var develop: MobileDevelopSession?
    @State private var grade: MobileGradeSession?
    @State private var gradeEntry: MGradeEntry = .direct
    @State private var gradeReturn: MScreen = .home
    @State private var toast: String? = nil
    @State private var toastToken = 0
    @State private var debugOpened = false

    // 显影 → 调色的「吸入」过渡
    @State private var rootSize: CGSize = CGSize(width: 393, height: 852)
    @State private var flightPhase: MFlightPhase = .idle
    @State private var flightImage: MPlatformImage?
    @State private var flightRect: CGRect = .zero
    @State private var flightRadius: CGFloat = 3
    @State private var flightOpacity: Double = 0
    @State private var developPreviewHidden = false

    private enum MFlightPhase { case idle, sucking }

    init() {
        let args = ProcessInfo.processInfo.arguments
        var start: MScreen = .home
        if let index = args.firstIndex(of: "--screen"), args.indices.contains(index + 1) {
            switch args[index + 1] {
            case "develop": start = .develop
            case "grade": start = .grade
            default: break
            }
        }
        _screen = State(initialValue: start)
    }

    var body: some View {
        ZStack {
            HomeScreen(
                engine: engine,
                onOpenDevelop: { photo in
                    openDevelop(photo.id)
                },
                onOpenGrade: { photo in
                    openGrade(photo.id, entry: .direct, returningTo: .home)
                },
                onToast: showToast
            )
            .offset(x: screen == .home ? 0 : -72)
            .allowsHitTesting(screen == .home)

            if let develop {
                DevelopScreen(
                    session: develop,
                    onBack: { closeDevelop() },
                    onOpenGrade: { image, rect in
                        beginSuck(image: image, from: rect, photoID: develop.photoID)
                    },
                    previewHidden: developPreviewHidden,
                    onToast: showToast
                )
                .offset(x: screen == .grade && gradeReturn == .develop ? -72 : 0)
                .allowsHitTesting(screen == .develop)
                .transition(.move(edge: .trailing))
                .zIndex(1)
            }

            if let grade {
                GradeScreen(
                    session: grade,
                    entry: gradeEntry,
                    onBack: { closeGrade() },
                    onGoHome: goHome,
                    onToast: showToast
                )
                .transition(.move(edge: .trailing))
                .zIndex(2)
            }

            if let toast {
                VStack {
                    Spacer()
                    Text(toast)
                        .font(.mSans(11, .medium))
                        .foregroundStyle(MColor.text1)
                        .padding(.horizontal, 15)
                        .frame(height: 38)
                        .background(Capsule().fill(MColor.surface3.opacity(0.96)))
                        .overlay(Capsule().strokeBorder(MColor.hairlineStrong, lineWidth: 1))
                        .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
                        .padding(.bottom, MMetric.safeBottom + 76)
                }
                .transition(.opacity.combined(with: .offset(y: 8)))
                .allowsHitTesting(false)
            }

            if let flightImage {
                MImage.swiftUI(flightImage)
                    .resizable()
                    .frame(
                        width: max(1, flightRect.width),
                        height: max(1, flightRect.height)
                    )
                    .clipShape(
                        RoundedRectangle(cornerRadius: max(0, flightRadius), style: .continuous)
                    )
                    .position(x: flightRect.midX, y: flightRect.midY)
                    .opacity(flightOpacity)
                    .allowsHitTesting(false)
                    .zIndex(30)
            }
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { rootSize = geo.size }
                    .onChange(of: geo.size) { _, newValue in rootSize = newValue }
            }
        )
        .animation(MMotion.push, value: screen)
        .background(MColor.app)
        .preferredColorScheme(.dark)
        .task {
            guard !debugOpened else { return }
            debugOpened = true
            guard let first = engine.photos.first else { return }
            switch screen {
            case .develop: openDevelop(first.id)
            case .grade: openGrade(first.id, entry: .direct, returningTo: .home)
            case .home: break
            }
        }
    }

    // MARK: - 导航

    private func openDevelop(_ photoID: String) {
        engine.closeGrade()
        resetFlight()
        grade = nil
        withAnimation(MMotion.push) {
            develop = engine.openDevelop(photoID: photoID)
            screen = .develop
        }
    }

    private func closeDevelop() {
        engine.closeDevelop()
        resetFlight()
        withAnimation(MMotion.push) {
            develop = nil
            screen = .home
        }
    }

    private func goHome() {
        engine.closeGrade()
        engine.closeDevelop()
        resetFlight()
        withAnimation(MMotion.push) {
            grade = nil
            develop = nil
            screen = .home
        }
    }

    private func openGrade(_ photoID: String, entry: MGradeEntry, returningTo target: MScreen) {
        withAnimation(MMotion.push) {
            gradeEntry = entry
            gradeReturn = target
            grade = engine.openGrade(photoID: photoID, entry: entry)
            screen = .grade
        }
    }

    private func closeGrade() {
        engine.closeGrade()
        resetFlight()
        withAnimation(MMotion.push) {
            grade = nil
            screen = gradeReturn
        }
    }

    // MARK: - 照片吸入

    /// 开孔落点：灵动岛 / 刘海 / 平顶顶部边缘。
    private var housingTarget: CGRect {
        let width = max(1, rootSize.width)
        switch MDeviceHousing.resolved(housingSetting) {
        case .island, .auto:
            let islandWidth = width * 0.336
            let islandHeight = islandWidth * 0.318
            return CGRect(
                x: (width - islandWidth) / 2,
                y: width * 0.0178,
                width: islandWidth,
                height: islandHeight
            )
        case .notch:
            let notchWidth = width * 0.432
            let notchHeight = notchWidth * 0.241
            return CGRect(
                x: (width - notchWidth) / 2,
                y: 1,
                width: notchWidth,
                height: notchHeight
            )
        case .none:
            return CGRect(x: (width - 90) / 2, y: 0, width: 90, height: 3)
        }
    }

    private func beginSuck(image: MPlatformImage?, from rect: CGRect, photoID: String) {
        guard flightPhase == .idle else { return }
        guard let image, rect.width > 1, rect.height > 1 else {
            openGrade(photoID, entry: .handoff, returningTo: .develop)
            return
        }

        let target = housingTarget
        flightImage = image
        flightRect = rect
        flightRadius = 3
        flightOpacity = 1
        flightPhase = .sucking
        developPreviewHidden = true

        withAnimation(.spring(response: 0.48, dampingFraction: 0.66)) {
            flightRect = target
            flightRadius = min(target.width, target.height) / 2
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.30) {
            withAnimation(.easeIn(duration: 0.18)) { flightOpacity = 0 }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.54) {
            guard flightPhase == .sucking else { return }
            flightPhase = .idle
            flightRect = target
            flightOpacity = 0
            flightImage = nil
            // 画布保持隐藏，等从调色台返回时再由 resetFlight 恢复，避免横移过程中背后又出现一张。
            openGrade(photoID, entry: .handoff, returningTo: .develop)
        }
    }

    private func resetFlight() {
        flightPhase = .idle
        flightImage = nil
        flightOpacity = 0
        developPreviewHidden = false
    }

    private func showToast(_ text: String) {
        toastToken += 1
        let token = toastToken
        withAnimation(MMotion.state) { toast = text }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.1) {
            guard token == toastToken else { return }
            withAnimation(MMotion.state) { toast = nil }
        }
    }
}
