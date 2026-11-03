import SwiftUI

// MARK: - Canvas

struct PreviewStage: View {
    let photo: PhotoItem
    let filmName: String
    let paperName: String

    var body: some View {
        ZStack {
            SkinColor.canvas

            RadialGradient(
                colors: [Color(hex: 0x2B251D).opacity(0.55), .clear],
                center: UnitPoint(x: 0.5, y: 0.44),
                startRadius: 8,
                endRadius: 460
            )

            LinearGradient(
                colors: [Color.white.opacity(0.018), .clear],
                startPoint: .top,
                endPoint: UnitPoint(x: 0.5, y: 0.3)
            )

            GeometryReader { geo in
                let fit = SkinPrintFit.fit(geo.size, aspect: photo.aspectRatio)
                let matte: CGFloat = 22

                ZStack {
                    Rectangle()
                        .fill(Color(hex: 0xF1EDE3))
                        .frame(width: fit.width + matte * 2, height: fit.height + matte * 2)
                        .overlay(
                            Rectangle()
                                .strokeBorder(Color.black.opacity(0.18), lineWidth: 1)
                        )
                        .shadow(color: .black.opacity(0.48), radius: 22, y: 16)

                    Image(skinAsset: photo.asset)
                        .resizable()
                        .scaledToFill()
                        .frame(width: fit.width, height: fit.height)
                        .clipped()
                }
                .position(x: geo.size.width / 2, y: geo.size.height / 2)
            }

            VStack(spacing: 0) {
                HStack {
                    Text("照片")
                        .font(.skin(10.5))
                        .foregroundStyle(SkinColor.text2)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 11, style: .continuous)
                                .fill(SkinColor.surface1.opacity(0.92))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 11, style: .continuous)
                                .strokeBorder(SkinColor.hairlineStrong, lineWidth: 1)
                        )

                    Spacer(minLength: 0)
                }

                Spacer(minLength: 0)

                HStack(alignment: .bottom, spacing: 16) {
                    Text("\(photo.filename) · \(photo.dimensions) · \(filmName) · \(paperName)")
                        .font(.skin(10.5).monospacedDigit())
                        .foregroundStyle(SkinColor.text3)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    PreviewToolbar()
                }
            }
            .padding(14)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct PreviewToolbar: View {
    @State private var compare = false

    var body: some View {
        HStack(spacing: 2) {
            ToolbarTextButton(title: "1/2", chevron: true)
            divider
            ToolbarTextButton(
                title: "对比",
                icon: "rectangle.split.2x1",
                active: compare
            ) {
                withAnimation(SkinMotion.state) { compare.toggle() }
            }
            ToolbarTextButton(title: "渲染")

            SkinVerticalHairline(color: SkinColor.hairlineStrong, height: 14)
                .padding(.horizontal, 3)

            SkinIconButton("rotate.left", size: 12, frame: 26)
            SkinIconButton("rotate.right", size: 12, frame: 26)
            SkinIconButton("arrow.up.left.and.arrow.down.right", size: 12, frame: 26)

            ToolbarTextButton(title: "100%", chevron: true)
        }
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(SkinColor.surface1.opacity(0.94))
                .shadow(color: .black.opacity(0.36), radius: 16, y: 7)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .strokeBorder(SkinColor.hairlineStrong, lineWidth: 1)
        )
    }

    private var divider: some View {
        SkinVerticalHairline(color: SkinColor.hairlineStrong, height: 14)
            .padding(.horizontal, 3)
    }
}

private struct ToolbarTextButton: View {
    let title: String
    var icon: String?
    var chevron: Bool = false
    var active: Bool = false
    var action: () -> Void = {}

    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 11.5, weight: .medium))
                }
                Text(title)
                    .font(.skin(10.5, .medium))
                if chevron {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 7, weight: .medium))
                        .opacity(0.7)
                }
            }
            .foregroundStyle(active ? SkinColor.accent : (hovered ? SkinColor.text1 : SkinColor.text2))
            .padding(.horizontal, 7)
            .frame(height: 26)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(active ? SkinColor.accent.opacity(0.10) : (hovered ? SkinColor.wash : .clear))
            )
            .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .animation(SkinMotion.hover, value: hovered)
    }
}

// MARK: - Filmstrip

struct Filmstrip: View {
    let items: [PhotoItem]
    let currentID: String
    let actions: SkinActions

    var body: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 6) {
                ForEach(items) { item in
                    FilmThumbnail(
                        photo: item,
                        selected: item.id == currentID
                    ) {
                        actions.selectStripPhoto(item.id)
                    }
                }

                AddThumbnail()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 9)
        }
        .scrollIndicators(.hidden)
        .frame(height: SkinMetric.filmstripHeight)
        .background(SkinColor.app)
        .overlay(alignment: .top) {
            SkinHairline()
        }
    }
}

private struct FilmThumbnail: View {
    let photo: PhotoItem
    let selected: Bool
    let action: () -> Void

    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            ZStack {
                Image(skinAsset: photo.asset)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 84, height: 63)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(
                                selected ? SkinColor.accent.opacity(0.95) : (hovered ? SkinColor.hairlineStrong : SkinColor.hairline),
                                lineWidth: selected ? 1.5 : 1
                            )
                    )
            }
            .frame(width: 92, height: 69)
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(selected ? SkinColor.surface2 : (hovered ? SkinColor.surface1 : .clear))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .strokeBorder(selected ? SkinColor.accent.opacity(0.7) : .clear, lineWidth: 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .animation(SkinMotion.hover, value: hovered)
        .help(photo.filename)
    }
}

private struct AddThumbnail: View {
    @State private var hovered = false

    var body: some View {
        Button {} label: {
            Image(systemName: "plus")
                .font(.system(size: 20, weight: .light))
                .foregroundStyle(hovered ? SkinColor.accent : SkinColor.text3)
                .frame(width: 92, height: 69)
                .background(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(hovered ? SkinColor.accent.opacity(0.07) : .clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .strokeBorder(
                            hovered ? SkinColor.accent.opacity(0.5) : SkinColor.hairlineStrong,
                            lineWidth: 1
                        )
                )
                .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .animation(SkinMotion.hover, value: hovered)
        .help("导入照片")
    }
}
