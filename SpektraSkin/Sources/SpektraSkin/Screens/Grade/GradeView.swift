import SwiftUI

struct GradeView: View {
    let snapshot: GradeSnapshot
    let actions: SkinActions

    var body: some View {
        VStack(spacing: 0) {
            topBar

            HStack(spacing: 0) {
                placeholderPanel(
                    title: "LUT / 预设",
                    emptyTitle: "暂无 LUT",
                    rows: ["胶片曲线", "相机配置", "创意 LUT"]
                )
                .frame(width: 240)

                SkinVerticalHairline()

                stage
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                SkinVerticalHairline()

                placeholderPanel(
                    title: "调色参数",
                    emptyTitle: "尚未接入",
                    rows: ["曝光", "对比度", "曲线", "色彩混合", "颜色分级", "细节"]
                )
                .frame(width: 300)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(SkinColor.app)
    }

    private var topBar: some View {
        HStack(spacing: 10) {
            SkinButton("显影台", icon: "chevron.left", kind: .secondary, height: 28) {
                actions.backToEditor()
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(snapshot.photo.filename)
                    .font(.skin(13.5, .medium))
                    .foregroundStyle(SkinColor.text1)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Text(snapshot.handoffMeta)
                    .font(.skin(10.5).monospacedDigit())
                    .foregroundStyle(SkinColor.text3)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text("调色台")
                .font(.skin(10.5, .medium))
                .foregroundStyle(SkinColor.accent)
                .padding(.horizontal, 7)
                .padding(.vertical, 2)
                .background(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(SkinColor.accent.opacity(0.10))
                )

            SkinButton("导出", icon: "square.and.arrow.up", kind: .primary, height: 28, disabled: true) {}
        }
        .padding(.horizontal, 16)
        .frame(height: SkinMetric.topBarHeight)
        .background(SkinColor.app)
        .overlay(alignment: .bottom) {
            SkinHairline()
        }
    }

    private var stage: some View {
        ZStack {
            SkinColor.canvas

            RadialGradient(
                colors: [Color(hex: 0x2A241C).opacity(0.45), .clear],
                center: UnitPoint(x: 0.5, y: 0.46),
                startRadius: 8,
                endRadius: 420
            )

            GeometryReader { geo in
                let fit = SkinPrintFit.fit(
                    geo.size,
                    horizontalInset: 110,
                    verticalInset: 100,
                    aspect: snapshot.photo.aspectRatio
                )

                if let preview = snapshot.previewImage {
                    Image(nsImage: preview)
                        .resizable()
                        .scaledToFill()
                        .frame(width: fit.width, height: fit.height)
                        .clipped()
                        .shadow(color: .black.opacity(0.5), radius: 26, y: 18)
                        .position(x: geo.size.width / 2, y: geo.size.height / 2)
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "slider.horizontal.3")
                            .font(.system(size: 30, weight: .light))
                            .foregroundStyle(SkinColor.text4)
                        Text("调色台尚未接入")
                            .font(.skin(11))
                            .foregroundStyle(SkinColor.text3)
                    }
                    .frame(width: fit.width, height: fit.height)
                    .background(SkinColor.surface2)
                    .position(x: geo.size.width / 2, y: geo.size.height / 2)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func placeholderPanel(title: String, emptyTitle: String, rows: [String]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(.skin(12, .semibold))
                .tracking(0.3)
                .foregroundStyle(SkinColor.text2)
                .padding(.bottom, 3)

            Text(emptyTitle)
                .font(.skin(10.5))
                .foregroundStyle(SkinColor.text4)
                .padding(.bottom, 14)

            VStack(spacing: 2) {
                ForEach(rows, id: \.self) { row in
                    HStack {
                        Text(row)
                            .font(.skin(11.5))
                            .foregroundStyle(SkinColor.text3.opacity(0.55))
                        Spacer()
                        Text("—")
                            .font(.skin(11).monospacedDigit())
                            .foregroundStyle(SkinColor.text4.opacity(0.7))
                    }
                    .frame(height: 38)
                }
            }
            .opacity(0.8)

            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(SkinColor.surface1)
    }
}
