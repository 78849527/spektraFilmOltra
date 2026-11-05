import SwiftUI
import UniformTypeIdentifiers

struct HomeScreen: View {
    @ObservedObject var engine: MobileEngine
    let onOpenDevelop: (MPhoto) -> Void
    let onOpenGrade: (MPhoto) -> Void
    let onToast: (String) -> Void

    @State private var filter: HomeFilter = .all
    @State private var sortMode: HomeSort = .recent
    @State private var actionPhoto: MPhoto?
    @State private var showImporter = false
    @State private var didDebugOpen = false
    @State private var searchOpen = false
    @State private var query = ""
    @FocusState private var searchFocused: Bool

    var body: some View {
        ZStack(alignment: .bottom) {
            VStack(spacing: 0) {
                header

                ScrollView(.vertical) {
                    VStack(alignment: .leading, spacing: 0) {
                        filterRow
                        sectionHead
                        photoGrid
                    }
                    .padding(.bottom, 106)
                }
                .scrollIndicators(.never)
            }

            bottomBar

            if let photo = actionPhoto {
                photoActions(for: photo)
            }
        }
        .background(MColor.app)
        .fileImporter(
            isPresented: $showImporter,
            allowedContentTypes: [.item],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                let report = engine.importPhotos(urls)
                if report.imported > 0 {
                    onToast("已导入 \(report.imported) 张")
                } else if report.rejected > 0 {
                    onToast("仅支持 RAW 文件")
                }
            case .failure:
                onToast("导入失败")
            }
        }
        .task {
            guard !didDebugOpen else { return }
            didDebugOpen = true
            if DebugLaunch.showSheet, let first = engine.photos.first {
                actionPhoto = first
            }
        }
    }

    // MARK: - 顶部

    private var header: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 10) {
                if searchOpen {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(MColor.text3)

                        TextField("搜索", text: $query)
                            .textFieldStyle(.plain)
                            .font(.mSans(12))
                            .foregroundStyle(MColor.text1)
                            .tint(MColor.brass)
                            .focused($searchFocused)

                        Button {
                            MHaptic.tick()
                            withAnimation(MMotion.state) {
                                query = ""
                                searchOpen = false
                            }
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(MColor.text3)
                                .frame(width: 24, height: 24)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 38)
                    .frame(maxWidth: .infinity)
                    .background(Capsule().fill(MColor.surface1))
                    .overlay(Capsule().strokeBorder(MColor.hairline, lineWidth: 1))
                } else {
                    Text("照片库")
                        .font(.pageTitle)
                        .tracking(0.3)
                        .foregroundStyle(MColor.text1)

                    Spacer(minLength: 0)

                    MCircleIconButton(icon: "magnifyingglass", size: 15) {
                        withAnimation(MMotion.state) {
                            searchOpen = true
                        }
                        searchFocused = true
                    }

                    Menu {
                        Button("最近导入") { sortMode = .recent }
                        Button("文件名") { sortMode = .filename }
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(MColor.text2)
                            .frame(width: 40, height: 40)
                            .background(Circle().fill(MColor.surface1))
                            .overlay(Circle().strokeBorder(MColor.hairline, lineWidth: 1))
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()
                }
            }

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("\(visiblePhotos.count) 张照片 · \(gradedCount) 张已调色")
                    .mMeta(10, color: MColor.text3)

                Spacer(minLength: 0)

                HStack(spacing: 5) {
                    Circle()
                        .fill(MColor.brass)
                        .frame(width: 4, height: 4)
                    Text("SPEKTRAFILM")
                        .font(.mSans(8, .semibold))
                        .tracking(2.0)
                        .foregroundStyle(MColor.text4)
                }
            }
            .padding(.top, 4)
        }
        .padding(.horizontal, MMetric.pageMargin)
        .padding(.top, MMetric.safeTop + 8)
        .padding(.bottom, 12)
    }

    // MARK: - 筛选

    private var filterRow: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 7) {
                ForEach(HomeFilter.allCases) { item in
                    MFilterChip(
                        title: item.title,
                        tone: item.tone,
                        selected: filter == item
                    ) {
                        withAnimation(MMotion.state) { filter = item }
                    }
                }

                MVerticalHairline(height: 16)
                    .padding(.horizontal, 3)

                ForEach(MColorLabel.allCases) { label in
                    MColorDotFilter(
                        label: label,
                        selected: filter == .label(label)
                    ) {
                        toggleLabel(label)
                    }
                }
            }
            .padding(.horizontal, MMetric.pageMargin)
        }
        .scrollIndicators(.never)
    }

    private func toggleLabel(_ label: MColorLabel) {
        MHaptic.tick()
        withAnimation(MMotion.state) {
            filter = filter == .label(label) ? .all : .label(label)
        }
    }

    private var sectionHead: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(filter.title)
                .font(.mSans(11, .semibold))
                .foregroundStyle(MColor.text2)

            Text("\(visiblePhotos.count)")
                .mMeta(9.5, color: MColor.text4)

            Spacer(minLength: 0)

            Button {
                MHaptic.tick()
                withAnimation(MMotion.state) {
                    sortMode = sortMode == .recent ? .filename : .recent
                }
            } label: {
                HStack(spacing: 3) {
                    Text(sortMode.title)
                        .font(.mSans(10, .medium))
                        .foregroundStyle(MColor.text3)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 7, weight: .semibold))
                        .foregroundStyle(MColor.text4)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, MMetric.pageMargin)
        .padding(.top, 16)
        .padding(.bottom, 10)
    }

    // MARK: - 网格

    private var photoGrid: some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
            ],
            alignment: .leading,
            spacing: 18
        ) {
            ForEach(Array(visiblePhotos.enumerated()), id: \.element.id) { item in
                MPhotoCard(
                    photo: item.element,
                    index: item.offset + 1,
                    onOpen: { onOpenDevelop(item.element) },
                    onLongPress: {
                        MHaptic.medium()
                        withAnimation(MMotion.drawer) { actionPhoto = item.element }
                    }
                )
            }
        }
        .padding(.horizontal, MMetric.pageMargin)
    }

    // MARK: - 底部

    private var bottomBar: some View {
        HStack(spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "square.grid.2x2")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(MColor.text3)
                Text("全部 · \(visiblePhotos.count)")
                    .font(.mSans(10, .medium))
                    .foregroundStyle(MColor.text3)
            }
            .padding(.horizontal, 12)
            .frame(height: 42)
            .background(Capsule().fill(MColor.surface1.opacity(0.92)))
            .overlay(Capsule().strokeBorder(MColor.hairline, lineWidth: 1))

            Spacer(minLength: 0)

            MCircleIconButton(icon: "arrow.up.arrow.down", size: 13, frame: 42) {
                MHaptic.tick()
                withAnimation(MMotion.state) {
                    sortMode = sortMode == .recent ? .filename : .recent
                }
            }

            Button {
                MHaptic.medium()
                showImporter = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .semibold))
                    Text("导入")
                        .font(.mSans(12, .semibold))
                }
                .foregroundStyle(MColor.brassInk)
                .padding(.horizontal, 18)
                .frame(height: 46)
                .background(Capsule().fill(MColor.brass))
                .contentShape(Capsule())
            }
            .buttonStyle(MPressStyle(scale: 0.94))
        }
        .padding(.horizontal, MMetric.pageMargin)
        .padding(.top, 10)
        .padding(.bottom, MMetric.safeBottom)
        .background(
            LinearGradient(
                colors: [MColor.app.opacity(0), MColor.app.opacity(0.94), MColor.app],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)
        )
    }

    // MARK: - 长按菜单

    private func photoActions(for photo: MPhoto) -> some View {
        ZStack(alignment: .bottom) {
            MColor.scrim
                .ignoresSafeArea()
                .transition(.opacity)
                .onTapGesture {
                    withAnimation(MMotion.drawer) { actionPhoto = nil }
                }

            VStack(spacing: 0) {
                MGrabber()

                HStack(spacing: 11) {
                    thumbnail(photo, width: 58, height: 46)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(photo.filename)
                            .font(.mSans(12, .semibold))
                            .foregroundStyle(MColor.text1)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text("\(photo.film) · \(photo.dimensions)")
                            .mMeta(9.5, color: MColor.text3)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 0)

                    Button {
                        withAnimation(MMotion.drawer) { actionPhoto = nil }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(MColor.text3)
                            .frame(width: 32, height: 32)
                            .background(Circle().fill(MColor.surface2))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 20)
                .padding(.top, 2)
                .padding(.bottom, 12)

                MHairline()

                actionRow(
                    icon: "slider.horizontal.3",
                    title: "直接调色",
                    brass: true
                ) {
                    withAnimation(MMotion.drawer) { actionPhoto = nil }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
                        onOpenGrade(photo)
                    }
                }

                actionRow(
                    icon: "film",
                    title: "进入显影台"
                ) {
                    withAnimation(MMotion.drawer) { actionPhoto = nil }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
                        onOpenDevelop(photo)
                    }
                }

                MHairline().padding(.leading, 20)

                favoriteRow(photo)
                labelRow(photo)

                MHairline().padding(.leading, 20)

                actionRow(icon: "trash", title: "从库中移除", danger: true) {
                    withAnimation(MMotion.drawer) {
                        actionPhoto = nil
                        engine.remove(photoID: photo.id)
                    }
                    onToast("已从照片库移除")
                }

                Button {
                    withAnimation(MMotion.drawer) { actionPhoto = nil }
                } label: {
                    Text("取消")
                        .font(.mSans(12.5, .medium))
                        .foregroundStyle(MColor.text2)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.bottom, MMetric.safeBottom + 4)
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

    private func actionRow(
        icon: String,
        title: String,
        brass: Bool = false,
        danger: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button {
            MHaptic.light()
            action()
        } label: {
            HStack(spacing: 13) {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(brass ? MColor.brass : (danger ? MColor.danger : MColor.text3))
                    .frame(width: 26)

                Text(title)
                    .font(.mSans(12.5, .medium))
                    .foregroundStyle(danger ? MColor.danger : MColor.text1)

                Spacer(minLength: 0)

                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(MColor.text4)
            }
            .padding(.horizontal, 20)
            .frame(height: 50)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func favoriteRow(_ photo: MPhoto) -> some View {
        Button {
            MHaptic.tick()
            withAnimation(MMotion.state) {
                engine.setFavorite(photoID: photo.id, value: !photo.favorite)
                actionPhoto = engine.photos.first { $0.id == photo.id }
            }
        } label: {
            HStack(spacing: 13) {
                Image(systemName: photo.favorite ? "star.fill" : "star")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(photo.favorite ? MColor.brass : MColor.text3)
                    .frame(width: 26)
                Text(photo.favorite ? "取消收藏" : "加入收藏")
                    .font(.mSans(12.5, .medium))
                    .foregroundStyle(MColor.text1)
                Spacer()
            }
            .padding(.horizontal, 20)
            .frame(height: 50)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func labelRow(_ photo: MPhoto) -> some View {
        HStack(spacing: 13) {
            Image(systemName: "tag")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(MColor.text3)
                .frame(width: 26)

            Text("颜色标签")
                .font(.mSans(12.5, .medium))
                .foregroundStyle(MColor.text1)

            Spacer()

            HStack(spacing: 9) {
                ForEach(MColorLabel.allCases) { label in
                    Button {
                        MHaptic.tick()
                        withAnimation(MMotion.state) {
                            let newLabel: MColorLabel? = photo.color == label ? nil : label
                            engine.setColorLabel(photoID: photo.id, label: newLabel)
                            actionPhoto = engine.photos.first { $0.id == photo.id }
                        }
                    } label: {
                        Circle()
                            .fill(MColor.labelTone(label))
                            .frame(width: 14, height: 14)
                            .overlay(
                                Circle()
                                    .strokeBorder(MColor.text1, lineWidth: photo.color == label ? 1.5 : 0)
                                    .padding(-3)
                            )
                            .frame(width: 30, height: 30)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 20)
        .frame(height: 50)
    }

    // MARK: - 数据

    private var visiblePhotos: [MPhoto] {
        var filtered = engine.photos.filter { photo in
            switch filter {
            case .all: return true
            case .favorite: return photo.favorite
            case .graded: return photo.isGraded
            case .raw: return photo.isRaw
            case .label(let label): return photo.color == label
            }
        }
        let keyword = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !keyword.isEmpty {
            filtered = filtered.filter { photo in
                photo.filename.lowercased().contains(keyword)
                    || photo.film.lowercased().contains(keyword)
                    || photo.paper.lowercased().contains(keyword)
            }
        }
        switch sortMode {
        case .recent:
            return filtered
        case .filename:
            return filtered.sorted {
                $0.filename.localizedStandardCompare($1.filename) == .orderedAscending
            }
        }
    }

    private var gradedCount: Int {
        engine.photos.filter(\.isGraded).count
    }

    private func thumbnail(_ photo: MPhoto, width: CGFloat, height: CGFloat) -> some View {
        ZStack {
            Rectangle().fill(MColor.surface2)
            if let image = MPhotoImage.load(photo) {
                image.resizable().scaledToFill()
            }
        }
        .frame(width: width, height: height)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(MColor.hairline, lineWidth: 1)
        )
    }
}

// MARK: - 照片卡

private struct MPhotoCard: View {
    let photo: MPhoto
    let index: Int
    let onOpen: () -> Void
    let onLongPress: () -> Void

    @State private var longPressFired = false
    @State private var pressed = false

    var body: some View {
        Button {
            if longPressFired {
                longPressFired = false
                return
            }
            MHaptic.light()
            onOpen()
        } label: {
            imageStage
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .buttonStyle(MPressStyle(scale: 0.97))
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.44)
                .onEnded { _ in
                    longPressFired = true
                    onLongPress()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        longPressFired = false
                    }
                }
        )
    }

    private var imageStage: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                Rectangle().fill(MColor.surface2)

                if let image = MPhotoImage.load(photo) {
                    image
                        .resizable()
                        .scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                }

                LinearGradient(
                    colors: [Color.black.opacity(0.22), .clear, Color.black.opacity(0.38)],
                    startPoint: .top,
                    endPoint: .bottom
                )

                HStack(alignment: .top) {
                    if photo.isRaw {
                        Text("RAW")
                            .font(.mSans(7.5, .semibold))
                            .tracking(0.8)
                            .foregroundStyle(MColor.text1.opacity(0.9))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(
                                RoundedRectangle(cornerRadius: 3.5, style: .continuous)
                                    .fill(Color.black.opacity(0.52))
                            )
                    }

                    Spacer(minLength: 0)

                    Text(String(format: "%02d", index))
                        .font(.mSans(8, .medium).monospacedDigit())
                        .foregroundStyle(Color.white.opacity(0.62))
                }
                .padding(8)

                HStack(spacing: 4) {
                    if photo.isGraded {
                        HStack(spacing: 3) {
                            Circle().fill(MColor.brass).frame(width: 3, height: 3)
                            Text("已调色")
                                .font(.mSans(7.5, .medium))
                                .foregroundStyle(MColor.brass)
                        }
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 3.5, style: .continuous)
                                .fill(Color.black.opacity(0.55))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 3.5, style: .continuous)
                                .strokeBorder(MColor.brass.opacity(0.35), lineWidth: 1)
                        )
                    }
                    Spacer()
                    if photo.favorite {
                        Image(systemName: "star.fill")
                            .font(.system(size: 8, weight: .medium))
                            .foregroundStyle(MColor.brass)
                            .shadow(color: .black.opacity(0.5), radius: 2)
                    }
                    if let color = photo.color {
                        Circle()
                            .fill(MColor.labelTone(color))
                            .frame(width: 6, height: 6)
                            .shadow(color: .black.opacity(0.4), radius: 2)
                    }
                }
                .padding(8)
                .frame(maxHeight: .infinity, alignment: .bottom)
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .frame(height: 128)
        .clipShape(RoundedRectangle(cornerRadius: MRadius.card, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: MRadius.card, style: .continuous)
                .strokeBorder(MColor.hairline, lineWidth: 1)
        )
    }
}

// MARK: - 筛选 / 排序

enum HomeFilter: Identifiable, Hashable, CaseIterable {
    case all, favorite, graded, raw, label(MColorLabel)

    var id: String { title }

    static var allCases: [HomeFilter] {
        [.all, .favorite, .graded, .raw]
    }

    var title: String {
        switch self {
        case .all: return "全部"
        case .favorite: return "收藏"
        case .graded: return "已调色"
        case .raw: return "RAW"
        case .label(let label): return label.title
        }
    }

    var tone: MColorLabel? {
        if case .label(let label) = self { return label }
        return nil
    }
}

enum HomeSort {
    case recent, filename

    var title: String {
        switch self {
        case .recent: return "最近"
        case .filename: return "文件名"
        }
    }
}

private struct MColorDotFilter: View {
    let label: MColorLabel
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button {
            action()
        } label: {
            Circle()
                .fill(MColor.labelTone(label))
                .frame(width: 9, height: 9)
                .frame(width: 28, height: 30)
                .background(
                    Circle().fill(selected ? MColor.surface3 : Color.clear)
                )
                .overlay(
                    Circle().strokeBorder(
                        selected ? MColor.labelTone(label).opacity(0.5) : Color.clear,
                        lineWidth: 1
                    )
                )
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }
}
