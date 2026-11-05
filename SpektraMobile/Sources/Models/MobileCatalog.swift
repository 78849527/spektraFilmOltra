import Foundation

/// 移动端展示目录：胶片 / 相纸取自 Swift 核心的 28 份配置，
/// 快速与专业页只用真实字段，id 与桌面 `EngineHost` 的映射表保持一致。
enum MobileCatalog {
    // MARK: - 胶片

    static let films: [MFilm] = [
        film("kodak_ektar_100", "柯达 Ektar 100", "柯达", "彩色负片", hue: 0.06, tone: .negative),
        film("kodak_portra_160", "柯达 Portra 160", "柯达", "彩色负片", hue: 0.04, tone: .negative),
        film("kodak_portra_400", "柯达 Portra 400", "柯达", "彩色负片", hue: 0.05, tone: .negative),
        film("kodak_portra_800", "柯达 Portra 800", "柯达", "彩色负片", hue: 0.03, tone: .negative),
        film("kodak_portra_800_push1", "柯达 Portra 800 推一档", "柯达", "彩色负片", hue: 0.02, tone: .negative),
        film("kodak_portra_800_push2", "柯达 Portra 800 推两档", "柯达", "彩色负片", hue: 0.02, tone: .negative),
        film("kodak_gold_200", "柯达 Gold 200", "柯达", "彩色负片", hue: 0.09, tone: .negative),
        film("kodak_ultramax_400", "柯达 UltraMax 400", "柯达", "彩色负片", hue: 0.08, tone: .negative),
        film("kodak_vision3_50d", "柯达 Vision3 50D", "柯达", "电影负片", hue: 0.11, tone: .cinema),
        film("kodak_vision3_250d", "柯达 Vision3 250D", "柯达", "电影负片", hue: 0.10, tone: .cinema),
        film("kodak_verita_200d", "柯达 Verita 200D", "柯达", "彩色负片", hue: 0.07, tone: .negative),
        film("kodak_vision3_200t", "柯达 Vision3 200T", "柯达", "电影负片", hue: 0.12, tone: .cinema),
        film("kodak_vision3_500t", "柯达 Vision3 500T", "柯达", "电影负片", hue: 0.13, tone: .cinema),
        film("fujifilm_pro_400h", "富士 Pro 400H", "富士", "彩色负片", hue: 0.43, tone: .negative),
        film("fujifilm_c200", "富士 C200", "富士", "彩色负片", hue: 0.45, tone: .negative),
        film("fujifilm_xtra_400", "富士 X-Tra 400", "富士", "彩色负片", hue: 0.44, tone: .negative),
        film("kodak_ektachrome_100", "柯达 Ektachrome 100", "柯达", "彩色反转片", hue: 0.55, tone: .reversal),
        film("kodak_kodachrome_64", "柯达 Kodachrome 64", "柯达", "彩色反转片", hue: 0.58, tone: .reversal),
        film("fujifilm_velvia_100", "富士 Velvia 100", "富士", "彩色反转片", hue: 0.92, tone: .reversal),
        film("fujifilm_provia_100f", "富士 Provia 100F", "富士", "彩色反转片", hue: 0.50, tone: .reversal),
    ]

    // MARK: - 相纸

    static let papers: [MPaper] = [
        paper("kodak_ultra_endura", "柯达 Ultra Endura", "柯达", warmth: 0.22, note: "浓郁 · 高反差"),
        paper("kodak_endura_premier", "柯达 Endura Premier", "柯达", warmth: 0.18, note: "专业 · 均衡"),
        paper("kodak_ektacolor_edge", "柯达 Ektacolor Edge", "柯达", warmth: 0.28, note: "暖黄 · 商业"),
        paper("kodak_supra_endura", "柯达 Supra Endura", "柯达", warmth: 0.10, note: "中性 · 高饱和"),
        paper("kodak_portra_endura", "柯达 Portra Endura", "柯达", warmth: 0.16, note: "暖调 · 肤色"),
        paper("fujifilm_crystal_archive_typeii", "富士 Crystal Archive Type II", "富士", warmth: 0.04, note: "冷调 · 干净"),
        paper("kodak_2383", "柯达 2383 电影印片", "柯达", warmth: 0.11, note: "电影 · 标准"),
        paper("kodak_2393", "柯达 2393 电影印片", "柯达", warmth: 0.12, note: "电影 · 高光"),
    ]

    // MARK: - 快速页

    static let quickGroups: [MQuickGroup] = [
        MQuickGroup(id: "light", title: "光调", axes: [
            MQuickAxis(id: "camera_exposure", label: "拍摄曝光", group: "光调",
                       range: -3...3, step: 0.1, decimals: 1, suffix: " EV", base: 0, value: 0),
            MQuickAxis(id: "print_brightness", label: "印相明暗", group: "光调",
                       range: -2...2, step: 0.05, decimals: 2, suffix: "", base: 0, value: 0),
            MQuickAxis(id: "tonal_contrast", label: "影调反差", group: "光调",
                       range: -100...100, step: 1, decimals: 0, suffix: "", base: 0, value: 0),
        ]),
        MQuickGroup(id: "color", title: "色彩", axes: [
            MQuickAxis(id: "color_density", label: "色彩浓度", group: "色彩",
                       range: -100...100, step: 1, decimals: 0, suffix: "", base: 0, value: 0),
            MQuickAxis(id: "temperature", label: "印相冷暖", group: "色彩",
                       range: -100...100, step: 1, decimals: 0, suffix: " CC", base: 0, value: 0),
        ]),
        MQuickGroup(id: "texture", title: "质感", axes: [
            MQuickAxis(id: "grain_amount", label: "颗粒强度", group: "质感",
                       range: -100...100, step: 1, decimals: 0, suffix: "", base: 0, value: 0),
            MQuickAxis(id: "scanner_clarity", label: "扫描清晰度", group: "质感",
                       range: -100...100, step: 1, decimals: 0, suffix: "", base: 0, value: 0),
        ]),
    ]

    // MARK: - 专业页

    static let proPages: [MProPage] = [
        MProPage(id: "tone", title: "光调", groups: [
            MProGroup(id: "tone-camera", title: "拍摄", rows: [
                slider("exposure_compensation_ev", "曝光补偿", 0, -5...5, 0.1, 1, " EV"),
                toggle("auto_exposure", "自动曝光", true),
            ]),
            MProGroup(id: "tone-print", title: "印相", rows: [
                slider("print_exposure", "印相曝光", 1, 0.125...8, 0.01, 2, "×"),
                slider("gamma_factor", "影调反差", 1, 0.55...1.8, 0.01, 2, "×"),
                slider("developer_exhaustion", "高光柔和", 0, 0...100, 1, 0, ""),
                slider("gamma_factor_fast", "快层反差", 1, 0.5...1.8, 0.01, 2, "×"),
            ]),
        ]),
        MProPage(id: "color", title: "色彩", groups: [
            MProGroup(id: "color-balance", title: "印相滤色", rows: [
                slider("print_y_filter_shift", "Y 偏移", 0, -60...60, 1, 0, " CC"),
                slider("print_m_filter_shift", "M 偏移", 0, -60...60, 1, 0, " CC"),
            ]),
            MProGroup(id: "color-couplers", title: "染料与色域", rows: [
                slider("inhibition_interlayer", "层间抑制", 1, 0.5...1.5, 0.01, 2, ""),
                slider("coupler_amount", "成色剂强度", 1, 0...2, 0.01, 2, ""),
            ]),
        ]),
        MProPage(id: "film", title: "胶片", groups: [
            MProGroup(id: "film-format", title: "片基", rows: [
                slider("film_format_mm", "胶片格式", 35, 8...120, 1, 0, " mm"),
                slider("diffusion_size_um", "染料扩散", 20, 0...100, 1, 0, ""),
            ]),
            MProGroup(id: "film-render", title: "光学", rows: [
                slider("halation_amount", "光晕强度", 1, 0...3, 0.01, 2, ""),
                slider("preflash_exposure", "预闪曝光", 0, 0...0.3, 0.01, 2, ""),
            ]),
        ]),
        MProPage(id: "detail", title: "细节", groups: [
            MProGroup(id: "detail-scan", title: "扫描", rows: [
                slider("scanner_unsharp_amount", "扫描锐化", 0.7, 0...2, 0.01, 2, ""),
                slider("scanner_unsharp_sigma", "锐化半径", 0.7, 0...3, 0.01, 2, " px"),
            ]),
            MProGroup(id: "detail-lens", title: "镜头", rows: [
                slider("scanner_lens_blur", "镜头模糊", 0, 0...2, 0.01, 2, ""),
                slider("particle_area_um2", "颗粒尺寸", 0.2, 0.03...1.2, 0.01, 2, " µm"),
            ]),
        ]),
    ]

    // MARK: - 查询

    static func film(id: String) -> MFilm? { films.first { $0.id == id } }
    static func paper(id: String) -> MPaper? { papers.first { $0.id == id } }

    static func filmName(_ stock: String) -> String { film(id: stock)?.name ?? stock }
    static func paperName(_ stock: String) -> String { paper(id: stock)?.name ?? stock }

    static func proRow(_ id: String) -> MProRow? {
        for page in proPages {
            for group in page.groups {
                if let row = group.rows.first(where: { $0.id == id }) { return row }
            }
        }
        return nil
    }

    // MARK: - 构造

    private enum FilmTone { case negative, cinema, reversal }

    private static func film(
        _ id: String, _ name: String, _ brand: String, _ kind: String,
        hue: Double, tone: FilmTone
    ) -> MFilm {
        let saturation: Double
        let brightness: Double
        switch tone {
        case .negative: saturation = 0.42; brightness = 0.56
        case .cinema: saturation = 0.26; brightness = 0.36
        case .reversal: saturation = 0.50; brightness = 0.50
        }
        return MFilm(id: id, name: name, brand: brand, kind: kind,
                     hue: hue, saturation: saturation, brightness: brightness)
    }

    private static func paper(
        _ id: String, _ name: String, _ brand: String,
        warmth: Double, note: String
    ) -> MPaper {
        MPaper(id: id, name: name, brand: brand, warmth: warmth, note: note)
    }

    private static func slider(
        _ id: String, _ label: String, _ base: Double,
        _ range: ClosedRange<Double>, _ step: Double, _ decimals: Int, _ suffix: String
    ) -> MProRow {
        MProRow(id: id, label: label,
                control: .slider(value: base, base: base, range: range,
                                 step: step, decimals: decimals, suffix: suffix))
    }

    private static func toggle(_ id: String, _ label: String, _ on: Bool) -> MProRow {
        MProRow(id: id, label: label, control: .toggle(isOn: on))
    }
}
