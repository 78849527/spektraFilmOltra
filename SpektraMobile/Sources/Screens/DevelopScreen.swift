import SwiftUI

struct DevelopScreen: View {
    @ObservedObject var session: MobileDevelopSession
    let onBack: () -> Void
    /// 点击调色时把当前预览图与它在根坐标系里的实际落点交给根视图，用于「吸入」动画。
    let onOpenGrade: (MPlatformImage?, CGRect) -> Void
    /// 吸入动画进行时隐藏原画布，避免照片被吸入后原位还留着一张。
    let previewHidden: Bool
    let onToast: (String) -> Void

    @State private var mode = DebugLaunch.modePro ? 1 : 0
    @State private var page = DebugLaunch.developPage
    @State private var drawerHeight: CGFloat = DebugLaunch.developDrawer
    @State private var dragStart: CGFloat? = nil
    @State private var panelContentHeight: CGFloat = 0
    @State private var panelViewportHeight: CGFloat = 0
    @State private var drawerChrome: CGFloat = 0

    @State private var showOriginal = false
    @State private var pressToken = 0
    @State private var zoom: CGFloat = 1
    @State private var pan: CGSize = .zero
    @State private var lastPan: CGSize = .zero
    @State private var exportOpen = DebugLaunch.exportOpen
    @State private var tabPressStart: Date?
    @State private var stageSize: CGSize = .zero
    // 首帧就绪前先弹出一块白色画布，再显影渐变成照片
    @State private var cardRect: CGRect = .zero
    @State private var cardOpacity: Double = 1
    @State private var cardVisible = false
    @State private var cardStarted = false
    @State private var cardRadius: CGFloat = 2
    @State private var imageRevealed = false

    @Environment(\.mHousing) private var housingSetting
    private var housing: MHousingKind { MDeviceHousing.resolved(housingSetting) }

    private let availableHeight: CGFloat = 852 - MMetric.safeTop - MMetric.safeBottom

    var body: some View {
        ZStack(alignment: .bottom) {
            MColor.app

            VStack(spacing: 0) {
                ZStack(alignment: .top) {
                    previewStage
                        .frame(height: max(96, availableHeight - drawerHeight))
                        .overlay {
                            if cardVisible {
                                MCanvasCard(rect: cardRect, opacity: cardOpacity, radius: cardRadius)
                                    .allowsHitTesting(false)
                            }
                        }
                        .background(
                            GeometryReader { geo in
                                Color.clear
                                    .onAppear { stageSize = geo.size }
                                    .onChange(of: geo.size) { _, newValue in stageSize = newValue }
                            }
                        )
                    floatingChrome
                }
                Spacer(minLength: 0)
            }
            .padding(.top, MMetric.safeTop)

            drawer
                .frame(height: drawerHeight + MMetric.safeBottom)

            MBackSwipe(action: onBack)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .padding(.top, MMetric.safeTop)

            if exportOpen {
                MExportSheet(
                    filename: session.filename,
                    isExporting: session.isExporting,
                    phaseLabel: session.phaseLabel,
                    onClose: { withAnimation(MMotion.drawer) { exportOpen = false } },
                    onReturnHome: {
                        withAnimation(MMotion.drawer) { exportOpen = false }
                        onBack()
                    },
                    onExport: { format, edge, done in
                        session.export(format: format, longEdgeIndex: edge) { result in
                            switch result {
                            case .success:
                                done(true)
                            case .failure:
                                done(false)
                                onToast("导出失败")
                            }
                        }
                    }
                )
            }
        }
        .background(MColor.app)
        .overlay(alignment: .top) {
            if housing != .none {
                MHousingAura(
                    housing: housing,
                    isActive: session.isRendering,
                    label: session.phaseLabel
                )
            }
        }
        .onChange(of: stageSize) { _, _ in popCardIfReady() }
        .onChange(of: session.previewImage != nil) { _, hasImage in
            if hasImage { popCardIfReady() }
        }
    }

    // MARK: - 开孔光效
    //
    // 光效由 MHousingAura 统一绘制：不表达进度，只有沿开孔轮廓游走的漏光与当前步骤文字。

    // MARK: - 顶部悬浮控件

    private var floatingChrome: some View {
        HStack(spacing: 8) {
            MCircleIconButton(icon: "chevron.left", size: 13, frame: 34) {
                onBack()
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .overlay(alignment: .center) {
            MModeCapsule(titles: ["快速", "专业"], mode: $mode)
                .overlay { capsuleProgressRing }
                .overlay(alignment: .bottom) { capsuleProgressText }
                .offset(y: session.isRendering ? 16 : 0)
                .animation(MMotion.drawer, value: session.isRendering)
                .animation(MMotion.quick, value: session.phaseLabel)
        }
    }

    /// 没有刘海 / 灵动岛时，光效改套在「快速 / 专业」胶囊外圈，步骤文字落在胶囊下方。
    @ViewBuilder private var capsuleProgressRing: some View {
        if housing == .none {
            MGlowSweep(
                shape: Capsule().inset(by: -4),
                isActive: session.isRendering,
                period: 2.4,
                segment: 0.36,
                coreWidth: 1.4
            )
        }
    }

    @ViewBuilder private var capsuleProgressText: some View {
        if housing == .none, session.isRendering {
            Text(session.phaseLabel.isEmpty ? "显影中" : session.phaseLabel)
                .font(.mSans(9, .medium))
                .foregroundStyle(MColor.brassHigh.opacity(0.92))
                .shadow(color: .black.opacity(0.6), radius: 2)
                .offset(y: 24)
                .allowsHitTesting(false)
        }
    }

    // MARK: - 预览

    private var previewStage: some View {
        ZStack {
            MColor.canvas

            RadialGradient(
                colors: [Color.white.opacity(0.035), .clear],
                center: .center,
                startRadius: 20,
                endRadius: 300
            )
            .allowsHitTesting(false)

            Group {
                if let image = showOriginal ? session.originalImage : session.previewImage {
                    MImage.swiftUI(image)
                        .resizable()
                        .scaledToFit()
                        .padding(.horizontal, 14)
                        .scaleEffect(zoom)
                        .offset(pan)
                        .animation(MMotion.state, value: showOriginal)
                        .animation(MMotion.drawer, value: zoom)
                } else {
                    Image(systemName: "photo")
                        .font(.system(size: 30, weight: .light))
                        .foregroundStyle(MColor.text4)
                }
            }
            .clipped()
            .opacity(imageRevealed && !previewHidden ? 1 : 0)
            .contentShape(Rectangle())
            .onTapGesture(count: 2) {
                MHaptic.light()
                withAnimation(MMotion.drawer) {
                    if zoom > 1 {
                        zoom = 1
                        pan = .zero
                        lastPan = .zero
                    } else {
                        zoom = 2.2
                    }
                }
            }
            .gesture(
                MagnificationGesture()
                    .onChanged { value in
                        zoom = min(4, max(1, value))
                    }
                    .onEnded { value in
                        zoom = min(4, max(1, value))
                        if zoom <= 1 { pan = .zero }
                    }
            )
            .simultaneousGesture(
                DragGesture()
                    .onChanged { gesture in
                        guard zoom > 1 else { return }
                        pan = CGSize(
                            width: lastPan.width + gesture.translation.width,
                            height: lastPan.height + gesture.translation.height
                        )
                    }
                    .onEnded { _ in
                        lastPan = pan
                    }
            )
            .onLongPressGesture(minimumDuration: 0.28, maximumDistance: 18, pressing: { pressing in
                if pressing {
                    pressToken += 1
                    let token = pressToken
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        guard token == pressToken else { return }
                        MHaptic.light()
                        withAnimation(MMotion.quick) { showOriginal = true }
                    }
                } else {
                    pressToken += 1
                    withAnimation(MMotion.quick) { showOriginal = false }
                }
            }, perform: {})

            cropMarks
                .zIndex(2)

            VStack(spacing: 0) {
                LinearGradient(
                    colors: [Color.black.opacity(0.36), Color.clear],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 94)
                .allowsHitTesting(false)

                Spacer(minLength: 0)

                LinearGradient(
                    colors: [Color.clear, Color.black.opacity(0.60)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 80)
                .allowsHitTesting(false)
            }
            .allowsHitTesting(false)

            VStack {
                Spacer(minLength: 0)
                previewMeta
                    .padding(.horizontal, 14)
                    .padding(.bottom, 10)
            }
        }
        .overlay(alignment: .bottom) {
            MHairline(color: MColor.hairlineFaint)
        }
    }

    private var previewMeta: some View {
        HStack(alignment: .bottom, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Circle()
                        .fill(showOriginal ? MColor.text3 : MColor.brass)
                        .frame(width: 4, height: 4)

                    Text(session.filename)
                        .font(.mSans(9.5, .medium))
                        .foregroundStyle(MColor.text2)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Text("\(currentFilm.name) · \(currentPaper.name)")
                    .font(.mSans(8.5, .medium))
                    .foregroundStyle(MColor.text3)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            if zoom > 1 || showOriginal {
                Text(showOriginal ? "原片" : "\(Int(zoom * 100))%")
                    .font(.mSans(8.5, .medium).monospacedDigit())
                    .foregroundStyle(showOriginal ? MColor.text2 : MColor.text4)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(Color.black.opacity(0.42)))
            }
        }
    }

    private var cropMarks: some View {
        GeometryReader { geo in
            let rect = fittedPreviewRect(in: geo.size)
            Canvas { context, _ in
                let inset: CGFloat = 7
                let length: CGFloat = 10
                let color = MColor.brass.opacity(0.22)
                let corners: [(CGPoint, CGSize)] = [
                    (CGPoint(x: rect.minX + inset, y: rect.minY + inset),
                     CGSize(width: length, height: length)),
                    (CGPoint(x: rect.maxX - inset, y: rect.minY + inset),
                     CGSize(width: -length, height: length)),
                    (CGPoint(x: rect.minX + inset, y: rect.maxY - inset),
                     CGSize(width: length, height: -length)),
                    (CGPoint(x: rect.maxX - inset, y: rect.maxY - inset),
                     CGSize(width: -length, height: -length)),
                ]
                for (origin, delta) in corners {
                    var path = Path()
                    path.move(to: CGPoint(x: origin.x + delta.width, y: origin.y))
                    path.addLine(to: origin)
                    path.addLine(to: CGPoint(x: origin.x, y: origin.y + delta.height))
                    context.stroke(path, with: .color(color), lineWidth: 0.8)
                }
            }
        }
        .allowsHitTesting(false)
        .scaleEffect(zoom)
        .offset(pan)
    }

    /// 与预览图 `.scaledToFit` + 左右 14pt 内边距的落点保持一致，取景角只贴着照片。
    private func fittedPreviewRect(in size: CGSize) -> CGRect {
        let horizontalInset: CGFloat = 14
        let availableWidth = max(1, size.width - horizontalInset * 2)
        let availableHeight = max(1, size.height)
        let aspect = max(0.1, session.previewAspect)
        var width = availableWidth
        var height = width / aspect
        if height > availableHeight {
            height = availableHeight
            width = height * aspect
        }
        return CGRect(
            x: (size.width - width) / 2,
            y: (size.height - height) / 2,
            width: width, height: height
        )
    }

    // MARK: - 预览就绪：白色画布弹出并显影成照片

    private func popCardIfReady() {
        guard !cardStarted,
              session.previewImage != nil,
              stageSize.width > 1,
              stageSize.height > 1 else { return }
        cardStarted = true
        let start = cardStartRect()
        cardRect = start
        cardRadius = min(start.width, start.height) / 2
        cardVisible = true
        cardOpacity = 1
        imageRevealed = false
        withAnimation(.spring(response: 0.45, dampingFraction: 0.7)) {
            cardRect = fittedPreviewRect(in: stageSize)
            cardRadius = 2
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
            withAnimation(.easeOut(duration: 0.32)) {
                cardOpacity = 0
                imageRevealed = true
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.82) {
            cardVisible = false
        }
    }

    private func cardStartRect() -> CGRect {
        let width = stageSize.width
        switch housing {
        case .notch:
            let notchWidth = width * 0.432
            let notchHeight = notchWidth * 0.241
            return CGRect(
                x: (width - notchWidth) / 2,
                y: 1 - MMetric.safeTop,
                width: notchWidth,
                height: notchHeight
            )
        case .none:
            return CGRect(x: (width - 90) / 2, y: -MMetric.safeTop, width: 90, height: 3)
        default:
            let islandWidth = width * 0.336
            let islandHeight = islandWidth * 0.318
            return CGRect(
                x: (width - islandWidth) / 2,
                y: width * 0.0178 - MMetric.safeTop,
                width: islandWidth,
                height: islandHeight
            )
        }
    }

    // MARK: - 抽屉

    private var drawer: some View {
        VStack(spacing: 0) {
            MGrabber(compact: true)
                .contentShape(Rectangle())
                .gesture(drawerDrag)
                .accessibilityElement()
                .accessibilityLabel("抽屉把手")

            ZStack {
                pageContent
                    .id("\(page)-\(mode)")
                    .transition(
                        .asymmetric(
                            insertion: .move(edge: .trailing),
                            removal: .move(edge: .leading)
                        )
                    )
            }
            .clipped()
            .background(
                GeometryReader { proxy in
                    Color.clear
                        .onChange(of: proxy.size.height, initial: true) { _, height in
                            panelViewportHeight = height
                            if drawerChrome == 0, height > 0 {
                                drawerChrome = max(0, drawerHeight - height)
                            }
                        }
                }
            )
            .animation(MMotion.state, value: page)
            .animation(MMotion.state, value: mode)
            .frame(maxHeight: .infinity)

            tabBar
        }
        .background(
            UnevenRoundedRectangle(
                topLeadingRadius: MRadius.sheet,
                bottomLeadingRadius: 0,
                bottomTrailingRadius: 0,
                topTrailingRadius: MRadius.sheet,
                style: .continuous
            )
            .fill(MColor.surface1)
        )
        .overlay(alignment: .top) {
            UnevenRoundedRectangle(
                topLeadingRadius: MRadius.sheet,
                bottomLeadingRadius: 0,
                bottomTrailingRadius: 0,
                topTrailingRadius: MRadius.sheet,
                style: .continuous
            )
            .strokeBorder(MColor.hairlineStrong, lineWidth: 1)
            .allowsHitTesting(false)
        }
        .shadow(color: .black.opacity(0.55), radius: 20, y: -6)
        .overlay(alignment: .topTrailing) {
            MCircleIconButton(icon: "arrow.uturn.backward", size: 10, frame: 28) {
                session.undo()
            }
            .opacity(session.canUndo ? 1 : 0.38)
            .allowsHitTesting(session.canUndo)
            .offset(x: -10, y: -36)
        }
        .onPreferenceChange(MPanelHeightKey.self) { height in
            panelContentHeight = height
            syncDrawerToContent()
        }
        .onChange(of: panelViewportHeight) { _, _ in
            syncDrawerToContent()
        }
    }

    /// 内容高度变化后：短页锁成单档（并贴合内容），长页只负责收掉多余留白。
    private func syncDrawerToContent() {
        guard panelViewportHeight > 0, panelContentHeight > 0 else { return }
        let fit = fitHeight(for: panelContentHeight)
        if isLockedTab {
            if abs(drawerHeight - fit) > 1 {
                withAnimation(MMotion.drawer) { drawerHeight = fit }
            }
        } else if drawerHeight > fit {
            withAnimation(MMotion.drawer) { drawerHeight = fit }
        }
    }

    /// 抽屉的固定装饰高度：把手 + 分页 + 底栏 + 安全区。与内容高度无关。
    private var chromeHeight: CGFloat { drawerChrome }

    /// 当前 tab 全部内容所需的抽屉高度，封顶三档。
    private func fitHeight(for content: CGFloat) -> CGFloat {
        guard content > 0, panelViewportHeight > 0 else { return MMetric.drawerMin }
        let needed = content + chromeHeight + 4
        if needed <= MMetric.drawerMin + 14 { return MMetric.drawerMin }
        return min(MMetric.drawerMax, needed)
    }

    private var fitDrawerHeight: CGFloat { fitHeight(for: panelContentHeight) }

    /// 内容只比一档多出一点点，展开也没有更多东西可看：只保留一个档位。
    private var isLockedTab: Bool {
        guard panelContentHeight > 0, panelViewportHeight > 0 else { return false }
        return fitDrawerHeight - MMetric.drawerMin <= 120
    }

    private var minDrawerHeight: CGFloat {
        isLockedTab ? fitDrawerHeight : MMetric.drawerMin
    }

    private var drawerDrag: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { gesture in
                if dragStart == nil { dragStart = drawerHeight }
                let base = dragStart ?? drawerHeight
                drawerHeight = min(fitDrawerHeight, max(minDrawerHeight, base - gesture.translation.height))
            }
            .onEnded { gesture in
                let base = dragStart ?? drawerHeight
                let projected = base - gesture.predictedEndTranslation.height
                let fit = fitDrawerHeight
                let detents: [CGFloat] = isLockedTab
                    ? [fit]
                    : [MMetric.drawerMin, fit]
                let target = detents.min { abs($0 - projected) < abs($1 - projected) } ?? MMetric.drawerMin
                withAnimation(MMotion.drawer) { drawerHeight = target }
                dragStart = nil
            }
    }

    // MARK: - 分页

    @ViewBuilder private var pageContent: some View {
        switch page {
        case 0:
            filmPage
        case 1:
            tonePage
        case 2:
            colorPage
        default:
            detailPage
        }
    }

    // MARK: - 胶片页

    private var filmPage: some View {
        ScrollView(.vertical) {
            VStack(spacing: 14) {
                filmRail
                paperRail
                if mode == 1 {
                    proGroupsView(2)
                        .padding(.top, 4)
                }
            }
            .padding(.horizontal, MMetric.pageMargin)
            .padding(.vertical, 6)
            .background(MPanelHeightReporter())
        }
        .scrollIndicators(.never)
    }

    private var filmRail: some View {
        VStack(alignment: .leading, spacing: 8) {
            railTitle("胶片")

            MHScrollRail(itemCount: MobileCatalog.films.count, itemHeight: 52) {
                ForEach(MobileCatalog.films) { film in
                    MFilmRailItem(film: film, selected: film.id == session.filmID) {
                        MHaptic.tick()
                        withAnimation(MMotion.state) { session.setFilm(film.id) }
                    }
                }
            }
            .frame(height: 52)
        }
    }

    private var paperRail: some View {
        VStack(alignment: .leading, spacing: 8) {
            railTitle("相纸")

            MHScrollRail(itemCount: MobileCatalog.papers.count, itemHeight: 52) {
                ForEach(MobileCatalog.papers) { paper in
                    MPaperRailItem(paper: paper, selected: paper.id == session.paperID) {
                        MHaptic.tick()
                        withAnimation(MMotion.state) { session.setPaper(paper.id) }
                    }
                }
            }
            .frame(height: 52)
        }
    }

    private func railTitle(_ title: String) -> some View {
        Text(title)
            .mLabel(7.5, color: MColor.text4)
            .padding(.leading, 1)
    }

    // MARK: - 光调页

    private var tonePage: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 0) {
                if mode == 0 {
                    quickSectionHead(
                        "光调",
                        trailing: lightDirtyCount > 0 ? "\(lightDirtyCount) 项已调" : "基线"
                    ) {
                        resetQuick()
                    }
                    .padding(.top, 2)

                    quickSlider("camera_exposure")
                    quickSlider("print_brightness")
                    quickSlider("tonal_contrast")
                } else {
                    proGroupsView(0)
                        .padding(.top, 2)

                    resetButton("重置专业参数", action: resetPro)
                        .padding(.top, 16)
                }
            }
            .padding(.horizontal, MMetric.pageMargin)
            .padding(.bottom, 16)
            .background(MPanelHeightReporter())
        }
        .scrollIndicators(.never)
    }

    // MARK: - 色彩页

    private var colorPage: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 0) {
                if mode == 0 {
                    quickSectionHead("色彩") {
                        resetQuick()
                    }

                    quickSlider("color_density")

                    HStack(spacing: 4) {
                        Text("印相色彩").mLabel(8, color: MColor.text4)
                        Spacer(minLength: 0)
                        Text("Y / M").mMeta(7.5, color: MColor.text4)
                    }
                    .padding(.top, 8)

                    GeometryReader { geo in
                        MColorPad(
                            x: padXBinding,
                            y: padYBinding,
                            width: max(1, geo.size.width),
                            height: 96
                        )
                    }
                    .frame(height: 96)
                    .padding(.top, 6)

                    HStack(spacing: 6) {
                        Text("冷暖 \(ccText(session.padX))")
                            .font(.mSans(8, .medium).monospacedDigit())
                            .foregroundStyle(abs(session.padX) > 0.5 ? MColor.brass : MColor.text3)
                        Spacer(minLength: 0)
                        Text("品红 \(ccText(session.padY))")
                            .font(.mSans(8, .medium).monospacedDigit())
                            .foregroundStyle(abs(session.padY) > 0.5 ? MColor.brass : MColor.text3)
                    }
                    .padding(.top, 6)

                } else {
                    proGroupsView(1)
                        .padding(.top, 2)

                    resetButton("重置专业参数", action: resetPro)
                        .padding(.top, 16)
                }
            }
            .padding(.horizontal, MMetric.pageMargin)
            .padding(.bottom, 16)
            .background(MPanelHeightReporter())
        }
        .scrollIndicators(.never)
    }

    // MARK: - 细节页

    private var detailPage: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 0) {
                if mode == 0 {
                    quickSectionHead("质感") {
                        resetQuick()
                    }

                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 0) {
                            quickSlider("grain_amount")
                            quickSlider("scanner_clarity")
                            Spacer(minLength: 0)
                        }
                        .frame(maxWidth: .infinity)

                        MGrainSample(intensity: grainIntensity)
                            .frame(width: 88, height: 88)
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                    .padding(.top, 2)

                } else {
                    proGroupsView(3)
                        .padding(.top, 2)

                    resetButton("重置专业参数", action: resetPro)
                        .padding(.top, 16)
                }
            }
            .padding(.horizontal, MMetric.pageMargin)
            .padding(.bottom, 16)
            .background(MPanelHeightReporter())
        }
        .scrollIndicators(.never)
    }

    // MARK: - 通用小组件

    @ViewBuilder private func quickSlider(_ id: String) -> some View {
        if let axis = allQuickAxes.first(where: { $0.id == id }) {
            MParamSlider(
                label: axis.label,
                value: binding(for: axis),
                base: axis.base,
                range: axis.range,
                step: axis.step,
                decimals: axis.decimals,
                suffix: axis.suffix,
                compact: true
            )
        }
    }

    @ViewBuilder private func proGroupsView(_ pageIndex: Int) -> some View {
        ForEach(MobileCatalog.proPages[pageIndex].groups) { group in
            VStack(alignment: .leading, spacing: 0) {
                Text(group.title)
                    .mLabel(8, color: MColor.text4)
                    .padding(.top, 12)
                    .padding(.bottom, 1)

                ForEach(group.rows) { row in
                    proRow(row)
                }
            }
        }
    }

    private func proRow(_ row: MProRow) -> some View {
        Group {
            switch row.control {
            case .slider(_, let base, let range, let step, let decimals, let suffix):
                MParamSlider(
                    label: row.label,
                    value: Binding(
                        get: { session.proValues[row.id] ?? base },
                        set: { session.applyPro(row.id, $0) }
                    ),
                    base: session.proBaseline(row.id),
                    range: range,
                    step: step,
                    decimals: decimals,
                    suffix: suffix,
                    compact: true
                )
            case .toggle(let isOn):
                MToggleRow(
                    label: row.label,
                    isOn: Binding(
                        get: { session.proToggles[row.id] ?? isOn },
                        set: { session.applyProToggle(row.id, $0) }
                    ),
                    compact: true
                )
            case .choice(let text):
                HStack {
                    Text(row.label)
                        .font(.rowLabel)
                        .foregroundStyle(MColor.text2)
                    Spacer()
                    Text(text)
                        .font(.mSans(10.5, .medium))
                        .foregroundStyle(MColor.text2)
                }
                .frame(height: 50)
            }
        }
    }

    private func quickSectionHead(
        _ title: String,
        trailing: String? = nil,
        reset: @escaping () -> Void
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title).mLabel(8.5, color: MColor.text3)
            Spacer(minLength: 8)
            if let trailing {
                Text(trailing).mMeta(8, color: MColor.text4)
            }

            Button {
                MHaptic.tick()
                withAnimation(MMotion.state) { reset() }
            } label: {
                Image(systemName: "arrow.counterclockwise")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(MColor.text3)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }

    private func resetButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button {
            MHaptic.medium()
            withAnimation(MMotion.state) { action() }
        } label: {
            Text(title)
                .font(.mSans(10, .medium))
                .foregroundStyle(MColor.text2)
                .frame(maxWidth: .infinity)
                .frame(height: 32)
                .background(
                    RoundedRectangle(cornerRadius: MRadius.control, style: .continuous)
                        .fill(MColor.surface2)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: MRadius.control, style: .continuous)
                        .strokeBorder(MColor.hairline, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .padding(.top, 10)
    }

    // MARK: - 底部页签

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(Array(pageItems.enumerated()), id: \.offset) { item in
                if item.offset == 4 {
                    tabLabel(item.element, index: item.offset)
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { _ in
                                    if tabPressStart == nil { tabPressStart = Date() }
                                }
                                .onEnded { _ in
                                    let duration = tabPressStart.map {
                                        Date().timeIntervalSince($0)
                                    } ?? 0
                                    tabPressStart = nil
                                    MHaptic.tick()
                                    if duration >= 0.45 {
                                        MHaptic.medium()
                                        withAnimation(MMotion.pill) { exportOpen = true }
                                    } else {
                                        let rect = fittedPreviewRect(in: stageSize)
                                        onOpenGrade(
                                            showOriginal ? session.originalImage : session.previewImage,
                                            CGRect(
                                                x: rect.minX,
                                                y: MMetric.safeTop + rect.minY,
                                                width: rect.width,
                                                height: rect.height
                                            )
                                        )
                                    }
                                }
                        )
                } else {
                    Button {
                        MHaptic.tick()
                        withAnimation(MMotion.state) { page = item.offset }
                    } label: {
                        tabLabel(item.element, index: item.offset)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.bottom, MMetric.safeBottom)
        .background(MColor.surface1)
        .overlay(alignment: .top) { MHairline() }
    }

    private func tabLabel(_ item: (title: String, icon: String), index: Int) -> some View {
        VStack(spacing: 3) {
            ZStack {
                if page == index, index < 4 {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(MColor.brassWash)
                        .frame(width: 34, height: 22)
                }
                Image(systemName: item.icon)
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundStyle(tabTone(index))
            }
            .frame(height: 22)

            Text(item.title)
                .font(.mSans(8.5, tabWeight(index)))
                .foregroundStyle(tabTone(index))
        }
        .frame(maxWidth: .infinity)
        .frame(height: 46)
        .contentShape(Rectangle())
    }

    private func tabTone(_ index: Int) -> Color {
        if index == 4 { return MColor.brass }
        return page == index ? MColor.brass : (index < 4 ? MColor.text3 : MColor.text4)
    }

    private func tabWeight(_ index: Int) -> Font.Weight {
        if index == 4 { return .medium }
        return page == index ? .semibold : .medium
    }

    private var pageItems: [(title: String, icon: String)] {
        [
            ("胶片", "film"),
            ("光调", "sun.max"),
            ("色彩", "drop"),
            ("细节", "camera.filters"),
            ("调色", "slider.horizontal.3"),
        ]
    }

    // MARK: - 状态与绑定

    private var allQuickAxes: [MQuickAxis] {
        MobileCatalog.quickGroups.flatMap(\.axes)
    }

    private var currentFilm: MFilm {
        MobileCatalog.film(id: session.filmID) ?? MobileCatalog.films[0]
    }

    private var currentPaper: MPaper {
        MobileCatalog.paper(id: session.paperID) ?? MobileCatalog.papers[0]
    }

    private var lightDirtyCount: Int {
        dirtyCount(in: "光调")
    }

    private func dirtyCount(in group: String) -> Int {
        allQuickAxes.filter { axis in
            axis.group == group
                && abs((session.quickValues[axis.id] ?? axis.base) - axis.base) > 1e-9
        }.count
    }

    private var padXBinding: Binding<Double> {
        Binding(
            get: { session.padX },
            set: { session.applyPad(x: $0, y: session.padY) }
        )
    }

    private var padYBinding: Binding<Double> {
        Binding(
            get: { session.padY },
            set: { session.applyPad(x: session.padX, y: $0) }
        )
    }

    private var grainIntensity: Double {
        let value = session.quickValues["grain_amount"] ?? 0
        return min(1, max(0.04, (value + 100) / 200))
    }

    private func ccText(_ value: Double) -> String {
        let cc = value * 0.6
        if abs(cc) < 0.05 { return "0 CC" }
        let text = String(format: "%.1f", cc).replacingOccurrences(of: ".0", with: "")
        return (cc > 0 ? "+\(text)" : text) + " CC"
    }

    private func binding(for axis: MQuickAxis) -> Binding<Double> {
        Binding(
            get: { session.quickValues[axis.id] ?? axis.base },
            set: { session.applyQuick(axis.id, $0) }
        )
    }

    private func resetQuick() {
        session.resetQuick()
    }

    private func resetPro() {
        session.resetPro()
    }
}

// MARK: - 导出面板

struct MExportSheet: View {
    let filename: String
    let isExporting: Bool
    let phaseLabel: String
    let onClose: () -> Void
    let onReturnHome: () -> Void
    let onExport: (Int, Int, @escaping (Bool) -> Void) -> Void

    @State private var format = 0
    @State private var longEdge = 1
    @State private var phase: MExportPhase = .idle

    private enum MExportPhase {
        case idle
        case exporting
        case success
        case done
    }

    private let formats: [(title: String, meta: String)] = [
        ("TIFF 16-bit", "sRGB · 可逆"),
        ("TIFF 16-bit", "ProPhoto 线性"),
        ("EXR half", "ACES 线性"),
        ("JPEG 95%", "快速分享"),
    ]
    private let edges = ["原始", "2048", "4096"]

    var body: some View {
        ZStack(alignment: .bottom) {
            MColor.scrim
                .ignoresSafeArea()
                .transition(.opacity)
                .onTapGesture(perform: onClose)

            VStack(spacing: 0) {
                MGrabber()

                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("导出")
                            .font(.mSerif(20))
                            .foregroundStyle(MColor.text1)
                        Text("\(filename) · 显影结果")
                            .mMeta(9, color: MColor.text3)
                    }
                    Spacer()
                    MCircleIconButton(icon: "xmark", size: 11, frame: 34, action: onClose)
                }
                .padding(.horizontal, MMetric.pageMargin)
                .padding(.bottom, 12)

                MHairline()

                VStack(alignment: .leading, spacing: 0) {
                    MSectionHead(title: "格式", trailing: "1 张")
                        .padding(.top, 14)
                        .padding(.bottom, 6)

                    ForEach(Array(formats.enumerated()), id: \.offset) { item in
                        Button {
                            MHaptic.tick()
                            withAnimation(MMotion.state) { format = item.offset }
                        } label: {
                            HStack(spacing: 10) {
                                Circle()
                                    .strokeBorder(
                                        format == item.offset ? MColor.brass : MColor.text4.opacity(0.6),
                                        lineWidth: 1
                                    )
                                    .frame(width: 14, height: 14)
                                    .overlay(
                                        Circle()
                                            .fill(MColor.brass)
                                            .frame(width: 6, height: 6)
                                            .opacity(format == item.offset ? 1 : 0)
                                    )
                                Text(item.element.title)
                                    .font(.mSans(12, .medium))
                                    .foregroundStyle(MColor.text1)
                                Spacer()
                                Text(item.element.meta)
                                    .mMeta(9, color: MColor.text3)
                            }
                            .frame(height: 44)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }

                    MSectionHead(title: "长边", trailing: "像素")
                        .padding(.top, 12)
                        .padding(.bottom, 7)

                    HStack(spacing: 7) {
                        ForEach(Array(edges.enumerated()), id: \.offset) { item in
                            Button {
                                MHaptic.tick()
                                withAnimation(MMotion.state) { longEdge = item.offset }
                            } label: {
                                Text(item.element)
                                    .font(.mSans(10.5, .medium).monospacedDigit())
                                    .foregroundStyle(longEdge == item.offset ? MColor.brass : MColor.text3)
                                    .padding(.horizontal, 14)
                                    .frame(height: 30)
                                    .background(
                                        Capsule().fill(longEdge == item.offset ? MColor.brassWash : MColor.surface2)
                                    )
                                    .overlay(
                                        Capsule().strokeBorder(
                                            longEdge == item.offset ? MColor.brass.opacity(0.35) : MColor.hairlineFaint,
                                            lineWidth: 1
                                        )
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                    }
                }
                .padding(.horizontal, MMetric.pageMargin)

                actionButton
                    .padding(.horizontal, MMetric.pageMargin)
                    .padding(.top, 16)
                    .padding(.bottom, MMetric.safeBottom + 8)
            }
            .background(MColor.surface1)
            .clipShape(
                UnevenRoundedRectangle(
                    topLeadingRadius: MRadius.sheet,
                    bottomLeadingRadius: 0,
                    bottomTrailingRadius: 0,
                    topTrailingRadius: MRadius.sheet,
                    style: .continuous
                )
            )
            .overlay(alignment: .top) {
                UnevenRoundedRectangle(
                    topLeadingRadius: MRadius.sheet,
                    bottomLeadingRadius: 0,
                    bottomTrailingRadius: 0,
                    topTrailingRadius: MRadius.sheet,
                    style: .continuous
                )
                .strokeBorder(MColor.hairlineStrong, lineWidth: 1)
            }
            .transition(.move(edge: .bottom))
        }
        .ignoresSafeArea()
    }

    @ViewBuilder
    private var actionButton: some View {
        switch phase {
        case .idle:
            MBrassPill(
                title: "导出 \(formats[format].title)",
                icon: "square.and.arrow.up",
                height: 46,
                fullWidth: true
            ) {
                beginExport()
            }
        case .exporting:
            MBrassPill(
                title: phaseLabel.isEmpty ? "导出中" : phaseLabel,
                height: 46,
                fullWidth: true,
                disabled: true,
                loading: true
            ) {}
        case .success:
            MBrassPill(
                title: "导出成功",
                icon: "checkmark",
                height: 46,
                fullWidth: true,
                disabled: true
            ) {}
        case .done:
            MBrassPill(
                title: "返回主页",
                icon: "house",
                height: 46,
                fullWidth: true
            ) {
                onReturnHome()
            }
        }
    }

    private func beginExport() {
        guard phase == .idle else { return }
        MHaptic.medium()
        phase = .exporting
        onExport(format, longEdge) { ok in
            if ok {
                phase = .success
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                    if phase == .success {
                        withAnimation(MMotion.state) { phase = .done }
                    }
                }
            } else {
                withAnimation(MMotion.state) { phase = .idle }
            }
        }
    }
}
