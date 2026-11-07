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
    @Environment(\.mSafeInsets) private var insets
    private var housing: MHousingKind { MDeviceHousing.resolved(housingSetting) }

    /// 真实可用画布高度：由根视图注入的设备安全区算出，不再写死 852/54/34。
    private var availableHeight: CGFloat { insets.contentHeight }

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
            .padding(.top, insets.top)

            drawer
                .frame(height: drawerHeight + insets.bottom)

            MBackSwipe(action: onBack)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .padding(.top, insets.top)
        }
        .background(MColor.app)
        .sheet(isPresented: $exportOpen) {
            MExportSheet(
                filename: session.filename,
                isExporting: session.isExporting,
                phaseLabel: session.exportLabel,
                phaseProgress: session.isExporting ? session.exportProgress : nil,
                originalLongEdge: session.exportOriginalEdge,
                canExport: session.isLoaded,
                onClose: { exportOpen = false },
                onReturnHome: {
                    exportOpen = false
                    onBack()
                },
                onNote: onToast,
                onExport: { format, edge, done in
                    session.export(format: format, longEdgeIndex: edge) { result in
                        if case .failure = result { onToast("导出失败") }
                        done(result)
                    }
                }
            )
        }
        .overlay(alignment: .top) {
            if housing != .none {
                MHousingAura(
                    housing: housing,
                    isActive: session.isRendering,
                    label: session.isRendering
                        ? (session.phaseLabel.isEmpty ? "显影中" : session.phaseLabel)
                        : ""
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
            previewScaleMenu
        }
        .frame(height: 34)
        .padding(.horizontal, 14)
        .overlay(alignment: .center) {
            MModeCapsule(titles: ["快速", "专业"], mode: $mode)
                .overlay { capsuleProgressRing }
                .overlay(alignment: .bottom) { capsuleProgressText }
                .offset(y: session.isRendering ? 16 : 0)
                .animation(MMotion.drawer, value: session.isRendering)
                .animation(MMotion.quick, value: session.phaseLabel)
        }
        .padding(.top, 10)
    }

    /// 预览渲染比例菜单：1/8、1/4、1/2、1/1，与 Swift 主线的 previewScale 档位一致。
    private var previewScaleMenu: some View {
        Menu {
            ForEach([0.125, 0.25, 0.5, 1.0], id: \.self) { value in
                Button {
                    MHaptic.tick()
                    withAnimation(MMotion.state) { session.setPreviewScale(value) }
                } label: {
                    Text(previewScaleTitle(value))
                }
            }
        } label: {
            HStack(spacing: 3) {
                Text(previewScaleTitle(session.previewScale))
                    .font(.mSans(9, .medium).monospacedDigit())
                Image(systemName: "chevron.down")
                    .font(.system(size: 7, weight: .semibold))
            }
            .foregroundStyle(MColor.text2)
            .padding(.horizontal, 9)
            .frame(height: 28)
            .background(Capsule().fill(MColor.surface2.opacity(0.9)))
            .overlay(Capsule().strokeBorder(MColor.hairline, lineWidth: 1))
        }
        .accessibilityLabel("预览渲染比例")
        .accessibilityValue(previewScaleTitle(session.previewScale))
    }

    private func previewScaleTitle(_ value: Double) -> String {
        switch value {
        case ..<0.2: return "1/8"
        case ..<0.4: return "1/4"
        case ..<0.8: return "1/2"
        default: return "1/1"
        }
    }

    /// 没有刘海 / 灵动岛时，光效改套在「快速 / 专业」胶囊外圈；步骤文字统一落在胶囊下方，
    /// 不再由开孔光效绘制（那会和胶囊重叠）。
    @ViewBuilder private var capsuleProgressRing: some View {
        if housing == .none {
            MGlowSweep(
                shape: Capsule().inset(by: -4),
                isActive: session.isRendering,
                period: 4.2,
                coreWidth: 1.4
            )
        }
    }

    @ViewBuilder private var capsuleProgressText: some View {
        // 有开孔时文字归 MHousingAura 画在开孔下方；无开孔机型没有让位空间，才落在胶囊下方。
        if session.isRendering, housing == .none {
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
            // 预览区不再铺自己的深色底：照片直接落在页面底色上，四周没有额外衬底，
            // 放大时也不会出现一圈「背景层」读成蒙版。
            Group {
                if let image = showOriginal ? session.originalImage : session.previewImage {
                    MImage.swiftUI(image)
                        .resizable()
                        .scaledToFit()
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

            // 拖动期的 LUT 预测帧精度低于精算帧，必须让用户知道当前看到的是过渡画面。
            if session.isPredicted, !showOriginal {
                Text("预测")
                    .font(.mSans(8.5, .medium))
                    .foregroundStyle(MColor.brassHigh.opacity(0.92))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .mGlassSurface(Capsule(), fallbackFill: Color.black.opacity(0.42))
                    .accessibilityLabel("LUT 预测帧，停手后替换为精算帧")
            }

            if zoom > 1 || showOriginal {
                Text(showOriginal ? "原片" : "\(Int(zoom * 100))%")
                    .font(.mSans(8.5, .medium).monospacedDigit())
                    .foregroundStyle(showOriginal ? MColor.text2 : MColor.text4)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .mGlassSurface(Capsule(), fallbackFill: Color.black.opacity(0.42))
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
        .opacity(zoom > 1 ? 0 : 1)
    }

    /// 与预览图 `.scaledToFit` 的落点保持一致（照片现在铺满预览区宽度），取景角只贴着照片。
    private func fittedPreviewRect(in size: CGSize) -> CGRect {
        let availableWidth = max(1, size.width)
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
        } completion: {
            withAnimation(.easeOut(duration: 0.32)) {
                cardOpacity = 0
                imageRevealed = true
            } completion: {
                cardVisible = false
            }
        }
    }

    private func cardStartRect() -> CGRect {
        let width = stageSize.width
        var stageInsets = insets
        stageInsets.size.width = width
        let opening = MDeviceHousing.opening(kind: housing, insets: stageInsets)
        // 预览画布自身已经从安全区顶部开始，所以减去 insets.top 才是画布内坐标。
        return CGRect(
            x: opening.minX,
            y: opening.minY - insets.top,
            width: opening.width,
            height: opening.height
        )
    }

    // MARK: - 抽屉

    private var drawer: some View {
        VStack(spacing: 0) {
            MDrawerChevron(isExpanded: isDrawerExpanded, isVisible: !isLockedTab) {
                toggleDrawer()
            }

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
        let target: CGFloat
        if isLockedTab {
            target = fit
        } else {
            target = min(drawerHeight, fit)
        }
        guard abs(drawerHeight - target) > 1 else { return }
        // 在布局回调里只做赋值，不再启动动画：preference → 动画 → 布局 → preference 会形成反馈环。
        drawerHeight = target
        if DebugLaunch.probeGeometry {
            NSLog("MDrawer content=%.0f viewport=%.0f fit=%.0f min=%.0f locked=%d height=%.0f",
                  panelContentHeight, panelViewportHeight, fit, MMetric.drawerMin,
                  isLockedTab ? 1 : 0, target)
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

    /// 二档判据：内容比「一档时能看到的视口」还高 → 展开有意义 → 显示 chevron。
    /// 以前用「fit 比一档高 120pt」，导致绝大多数调参页都被判成单档，箭头永远不出现。
    private var isLockedTab: Bool {
        guard panelContentHeight > 0 else { return true }
        let collapsedViewport = MMetric.drawerMin - chromeHeight - 4
        return panelContentHeight <= collapsedViewport + 24
    }

    private var minDrawerHeight: CGFloat {
        isLockedTab ? fitDrawerHeight : MMetric.drawerMin
    }

    /// 二档是否已展开（只差 1pt 以内视为同档）。
    private var isDrawerExpanded: Bool {
        drawerHeight > minDrawerHeight + 1
    }

    /// 点击 chevron：在「一档」与「刚好容纳当前页内容」之间切换。
    /// 用带轻微回弹的 spring，而非线性计时；iOS 26 上系统 chevron 的按压反馈由 Button 自带。
    private func toggleDrawer() {
        guard !isLockedTab else { return }
        let target = isDrawerExpanded ? minDrawerHeight : fitDrawerHeight
        withAnimation(.spring(response: 0.42, dampingFraction: 0.78)) {
            drawerHeight = target
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

                    if scanFilmMode {
                        Text(printOnlyQuickNote)
                            .mMeta(7.5, color: MColor.text4)
                            .padding(.top, -2)
                    }
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
                            height: 96,
                            isEnabled: !scanFilmMode
                        )
                    }
                    .frame(height: 96)
                    .padding(.top, 6)

                    HStack(spacing: 6) {
                        Text("冷暖 \(ccText(session.padX))")
                            .font(.mSans(8, .medium).monospacedDigit())
                            .foregroundStyle(abs(session.padX) > 0.5 && !scanFilmMode ? MColor.brass : MColor.text3)
                        Spacer(minLength: 0)
                        Text("品红 \(ccText(session.padY))")
                            .font(.mSans(8, .medium).monospacedDigit())
                            .foregroundStyle(abs(session.padY) > 0.5 && !scanFilmMode ? MColor.brass : MColor.text3)
                    }
                    .padding(.top, 6)

                    if scanFilmMode {
                        Text(printOnlyQuickNote)
                            .mMeta(7.5, color: MColor.text4)
                            .padding(.top, 4)
                    }

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
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 0) {
                    if mode == 0 {
                        quickSectionHead("质感") {
                            resetQuick()
                        }

                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 0) {
                                quickSlider("grain_amount")
                                quickSlider("grain_size")
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
            .onAppear {
                guard DebugLaunch.developPanelBottom, mode == 1 else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                    withAnimation(nil) { proxy.scrollTo("detail-output", anchor: .bottom) }
                }
            }
        }
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
                isEnabled: !(scanFilmMode && printOnlyQuickAxes.contains(id)),
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
            .id(group.id)
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
            case .choice(let options, let fallback):
                let current = session.choiceValue(row.id)
                let currentLabel = options.first(where: { $0.value == current })?.label ?? fallback
                HStack {
                    Text(row.label)
                        .font(.rowLabel)
                        .foregroundStyle(MColor.text2)
                    Spacer()
                    Menu {
                        ForEach(options, id: \.value) { option in
                            Button {
                                MHaptic.tick()
                                session.applyProChoice(row.id, option.value)
                            } label: {
                                Text(option.label)
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(currentLabel)
                                .font(.mSans(10.5, .medium))
                                .foregroundStyle(current == fallback ? MColor.text2 : MColor.brass)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 7, weight: .semibold))
                                .foregroundStyle(MColor.text4)
                        }
                    }
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
                                                y: insets.top + rect.minY,
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
        .padding(.bottom, insets.bottom)
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

    /// 正片扫描模式：管线跳过印相曝光/显影，印相专属快速轴不参与成像。
    private var scanFilmMode: Bool {
        session.proToggles["scan_film"] ?? false
    }

    /// 与参考 `PRINT_ONLY_AXES` 对齐：印相明暗、影调反差（色盘 Y/M 单独处理）。
    private var printOnlyQuickAxes: Set<String> {
        ["print_brightness", "tonal_contrast"]
    }

    private let printOnlyQuickNote = "正片扫描模式：管线跳过印相阶段，本项不参与成像"

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
    /// 0…1 的导出进度；只有在调用方发布进度时才传，否则退回转圈。
    var phaseProgress: Double? = nil
    /// 原图真实长边，用于把「原始」档显示成「原始 4032」，避免用户猜导出尺寸。
    var originalLongEdge: Int = 0
    /// 原片还没读完时不能导出：`session.export` 会以 `.busy` 立刻失败，面板会闪回 idle。
    var canExport: Bool = true
    let onClose: () -> Void
    let onReturnHome: () -> Void
    /// 相册写入是后台静默的，失败时用调用方的 toast 说明「文件已在 App 内」。
    var onNote: (String) -> Void = { _ in }
    let onExport: (Int, Int, @escaping (Result<URL, Error>) -> Void) -> Void

    @State private var format = 0
    /// 默认导出必须是原图全分辨率；2048/4096 只在用户主动选择时才缩小。
    @State private var longEdge = 0
    @State private var phase: MExportPhase = .idle
    /// 由内容实测高度决定 sheet 高度：只保留一档，不再上拉。
    @State private var contentHeight: CGFloat = 420
    @Environment(\.mSafeInsets) private var insets

    private enum MExportPhase {
        case idle
        case exporting
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
        VStack(spacing: 0) {
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
                        .accessibilityAddTraits(format == item.offset ? [.isSelected] : [])
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
                                Text(edgeTitle(item.offset))
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
                            .accessibilityAddTraits(longEdge == item.offset ? [.isSelected] : [])
                        }
                        Spacer()
                    }
                }
                .padding(.horizontal, MMetric.pageMargin)

                actionButton
                    .padding(.horizontal, MMetric.pageMargin)
                    .padding(.top, 16)
                    .padding(.bottom, insets.bottom + 8)
        }
        .background(MColor.surface1)
        .background(
            GeometryReader { proxy in
                Color.clear
                    .onAppear { contentHeight = proxy.size.height }
                    .onChange(of: proxy.size.height) { _, height in contentHeight = height }
            }
        )
        // 内容本身已含底部安全区 padding，这里只留一点上边距，避免面板底部出现一大块空白。
        .presentationDetents([.height(min(640, max(340, contentHeight + 12)))])
        .presentationDragIndicator(.visible)
        .presentationBackground(MColor.surface1)
        .onChange(of: format) { _, _ in resetPhaseAfterOptionChange() }
        .onChange(of: longEdge) { _, _ in resetPhaseAfterOptionChange() }
        // 截图验收：等原片读完再自动开跑导出（原片没读完时 export 会以 .busy 立刻失败）
        .onChange(of: canExport) { _, ready in
            guard ready, DebugLaunch.exportAutoStart, phase == .idle else { return }
            beginExport()
        }
        .task {
            guard canExport, DebugLaunch.exportAutoStart, phase == .idle else { return }
            try? await Task.sleep(nanoseconds: 300_000_000)
            if phase == .idle { beginExport() }
        }
    }

    @ViewBuilder
    private var actionButton: some View {
        switch phase {
        case .idle:
            MBrassPill(
                title: canExport ? "导出 \(formats[format].title)" : "正在读取原片",
                icon: canExport ? "square.and.arrow.up" : nil,
                height: 46,
                fullWidth: true,
                disabled: !canExport
            ) {
                beginExport()
            }
        case .exporting:
            if let phaseProgress {
                MExportProgressRow(label: phaseLabel, progress: phaseProgress, height: 46)
            } else {
                MBrassPill(title: phaseLabel.isEmpty ? "导出中" : phaseLabel,
                           height: 46, fullWidth: true, disabled: true, loading: true) {}
            }
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

    /// 导出完成后再改格式/长边：按钮回到「导出」，避免用户以为已经按新参数导过。
    private func resetPhaseAfterOptionChange() {
        guard phase == .done else { return }
        withAnimation(MMotion.state) { phase = .idle }
    }

    private func edgeTitle(_ index: Int) -> String {
        if index == 0, originalLongEdge > 0 {
            return "原始 \(originalLongEdge)"
        }
        return index >= 0 && index < edges.count ? edges[index] : "原始"
    }

    private func beginExport() {
        guard phase == .idle else { return }
        MHaptic.medium()
        phase = .exporting
        onExport(format, longEdge) { result in
            switch result {
            case .success(let url):
                // 相册写入静默进行：成功不打扰，失败/被拒时必须告诉用户文件还在 App 内。
                PhotoLibraryExport.save(url) { outcome in
                    switch outcome {
                    case .saved:
                        break
                    case .denied:
                        onNote("未授权相册 · 文件已导出到 App 内")
                    case .failed:
                        onNote("相册写入失败 · 文件已导出到 App 内")
                    }
                }
                withAnimation(MMotion.state) { phase = .done }
            case .failure:
                withAnimation(MMotion.state) { phase = .idle }
            }
        }
    }
}
