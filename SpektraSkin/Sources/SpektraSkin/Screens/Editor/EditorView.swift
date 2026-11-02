import SwiftUI

struct EditorView: View {
    let snapshot: EditorSnapshot
    let presets: PresetCatalog
    let actions: SkinActions

    var body: some View {
        VStack(spacing: 0) {
            EditorTopBar(snapshot: snapshot, actions: actions)

            HStack(spacing: 0) {
                PresetRail(
                    presets: presets,
                    currentFilmID: snapshot.currentFilmID,
                    currentPaperID: snapshot.currentPaperID,
                    actions: actions
                )
                .frame(width: SkinMetric.sideRailWidth)

                SkinVerticalHairline()

                VStack(spacing: 0) {
                    PreviewStage(
                        photo: snapshot.photo,
                        filmName: snapshot.filmName,
                        paperName: snapshot.paperName
                    )
                    Filmstrip(
                        items: snapshot.filmstrip,
                        currentID: snapshot.photo.id,
                        actions: actions
                    )
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                SkinVerticalHairline()

                InspectorView(snapshot: snapshot, actions: actions)
                    .frame(width: SkinMetric.inspectorWidth)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(SkinColor.app)
    }
}

// MARK: - Top bar

private struct EditorTopBar: View {
    let snapshot: EditorSnapshot
    let actions: SkinActions

    @State private var favorite: Bool

    init(snapshot: EditorSnapshot, actions: SkinActions) {
        self.snapshot = snapshot
        self.actions = actions
        _favorite = State(initialValue: snapshot.photo.favorite)
    }

    var body: some View {
        HStack(spacing: 10) {
            SkinButton("照片库", icon: "chevron.left", kind: .secondary, height: 28) {
                actions.backToLibrary()
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(snapshot.photo.filename)
                    .font(.skin(13.5, .medium))
                    .foregroundStyle(SkinColor.text1)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Text("\(snapshot.photo.dimensions) · \(snapshot.filmName) · \(snapshot.paperName)")
                    .font(.skin(10.5).monospacedDigit())
                    .foregroundStyle(SkinColor.text3)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            SkinIconButton(
                favorite ? "star.fill" : "star",
                size: 14,
                frame: 28,
                active: favorite
            ) {
                withAnimation(SkinMotion.state) { favorite.toggle() }
            }
            .help("收藏这张照片")

            HStack(spacing: 7) {
                if snapshot.photo.isGraded {
                    Circle()
                        .fill(SkinColor.accent)
                        .frame(width: 5, height: 5)
                }

                GradeSplitButton(actions: actions)
            }
        }
        .padding(.horizontal, 16)
        .frame(height: SkinMetric.topBarHeight)
        .background(SkinColor.app)
        .overlay(alignment: .bottom) {
            SkinHairline()
        }
    }
}

private struct GradeSplitButton: View {
    let actions: SkinActions

    @State private var hovered = false

    var body: some View {
        HStack(spacing: 0) {
            Button(action: actions.openGrade) {
                HStack(spacing: 6) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 11.5, weight: .semibold))
                    Text("调色")
                        .font(.skin(12, .semibold))
                }
                .foregroundStyle(SkinColor.accentOn)
                .padding(.horizontal, 13)
                .frame(height: 28)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Rectangle()
                .fill(SkinColor.accentOn.opacity(0.16))
                .frame(width: 1, height: 15)

            Button(action: actions.exportOptions) {
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(SkinColor.accentOn.opacity(0.82))
                    .frame(width: 24, height: 28)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
        .background(
            RoundedRectangle(cornerRadius: SkinRadius.control, style: .continuous)
                .fill(hovered ? SkinColor.accentHover : SkinColor.accent)
        )
        .clipShape(RoundedRectangle(cornerRadius: SkinRadius.control, style: .continuous))
        .onHover { hovered = $0 }
        .animation(SkinMotion.hover, value: hovered)
    }
}
