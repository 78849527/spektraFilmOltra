import { useState } from 'react'
import { readPath } from '../state'
import type { Bootstrap, ProfileEntry, StateTree } from '../types'
import { Disclosure, FieldRow, Select, SwitchRow, Toggle, ValueRow } from './Controls'

function numberAt(state: StateTree, path: string, fallback = 0): number {
  const value = readPath(state, path)
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function boolAt(state: StateTree, path: string, fallback = false): boolean {
  const value = readPath(state, path)
  return typeof value === 'boolean' ? value : fallback
}

function stringAt(state: StateTree, path: string, fallback = ''): string {
  const value = readPath(state, path)
  return typeof value === 'string' ? value : fallback
}

function profileOptions(entries: ProfileEntry[]): Array<{ value: string; label: string }> {
  return entries.map((entry) => ({ value: entry.id, label: entry.display_name }))
}

export function ProPanel({
  state,
  bootstrap,
  onPath,
  onSelectProfile,
  borderOn,
  onBorderChange,
}: {
  state: StateTree
  bootstrap: Bootstrap
  onPath: (path: string, value: unknown) => void
  onSelectProfile: (kind: 'film' | 'paper', id: string) => void
  borderOn: boolean
  onBorderChange: (value: boolean) => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({
    film: true,
    input: false,
    camera: true,
    print: true,
    grain: false,
    halation: false,
    glare: false,
    diffusion: false,
    scanner: false,
    output: true,
    display: false,
  })

  const toggle = (key: string) => setOpen((current) => ({ ...current, [key]: !current[key] }))

  function slider(
    key: string,
    path: string,
    label: string,
    min: number,
    max: number,
    step: number,
    decimals = 0,
    suffix = '',
  ) {
    return (
      <ValueRow
        key={`${key}-${path}`}
        label={label}
        value={numberAt(state, path)}
        min={min}
        max={max}
        step={step}
        decimals={decimals}
        suffix={suffix}
        onChange={(value) => onPath(path, value)}
        onReset={() => onPath(path, 0)}
      />
    )
  }

  const colorSpaces = bootstrap.options.color_spaces.map((value) => ({ value, label: value }))

  return (
    <div>
      <Disclosure title="胶片与相纸" open={open.film} onToggle={() => toggle('film')}>
        <FieldRow label="胶片">
          <Select
            value={stringAt(state, 'simulation.film_stock')}
            options={profileOptions(bootstrap.films)}
            onChange={(value) => onSelectProfile('film', value)}
          />
        </FieldRow>
        <FieldRow label="相纸">
          <Select
            value={stringAt(state, 'simulation.print_paper')}
            options={profileOptions(bootstrap.papers)}
            onChange={(value) => onSelectProfile('paper', value)}
          />
        </FieldRow>
      </Disclosure>

      <Disclosure title="输入" open={open.input} onToggle={() => toggle('input')}>
        <FieldRow label="输入色彩空间">
          <Select
            value={stringAt(state, 'input_image.input_color_space', 'sRGB')}
            options={colorSpaces}
            onChange={(value) => onPath('input_image.input_color_space', value)}
          />
        </FieldRow>
        <FieldRow label="输入 CCTF 解码">
          <Toggle
            checked={boolAt(state, 'input_image.input_cctf_decoding', true)}
            onChange={(value) => onPath('input_image.input_cctf_decoding', value)}
          />
        </FieldRow>
        <FieldRow label="光谱上采样">
          <Select
            value={stringAt(state, 'input_image.rgb_to_raw_method', 'hanatos2025')}
            options={bootstrap.options.rgb_to_raw_methods.map((value) => ({ value, label: value }))}
            onChange={(value) => onPath('input_image.rgb_to_raw_method', value)}
          />
        </FieldRow>
        {slider('upscale', 'input_image.upscale_factor', '放大系数', 0.5, 4, 0.05, 2, '×')}
      </Disclosure>

      <Disclosure title="拍摄" open={open.camera} onToggle={() => toggle('camera')}>
        {slider('ev', 'camera.exposure_compensation_ev', '曝光补偿', -5, 5, 0.1, 1, ' EV')}
        <FieldRow label="自动测光">
          <Toggle checked={boolAt(state, 'camera.auto_exposure', true)} onChange={(value) => onPath('camera.auto_exposure', value)} />
        </FieldRow>
        <FieldRow label="测光方法">
          <Select
            value={stringAt(state, 'camera.auto_exposure_method', 'center_weighted')}
            options={bootstrap.options.auto_exposure_methods.map((value) => ({ value, label: value }))}
            onChange={(value) => onPath('camera.auto_exposure_method', value)}
          />
        </FieldRow>
        {slider('lens-blur', 'camera.lens_blur_um', '镜头模糊', 0, 20, 0.5, 1, ' μm')}
      </Disclosure>

      <Disclosure title="印相" open={open.print} onToggle={() => toggle('print')}>
        {slider('print-exp', 'simulation.print_exposure', '印相曝光', 0.25, 4, 0.05, 2, '×')}
        <FieldRow label="自动亮度补偿">
          <Toggle
            checked={boolAt(state, 'simulation.print_exposure_compensation', true)}
            onChange={(value) => onPath('simulation.print_exposure_compensation', value)}
          />
        </FieldRow>
        {slider('y-shift', 'simulation.print_y_filter_shift', '黄滤镜位移', -200, 200, 1, 0, ' CC')}
        {slider('m-shift', 'simulation.print_m_filter_shift', '品红滤镜位移', -200, 200, 1, 0, ' CC')}
        <FieldRow label="印相光源">
          <Select
            value={stringAt(state, 'simulation.print_illuminant', 'TH-KG3')}
            options={bootstrap.options.illuminants.map((value) => ({ value, label: value }))}
            onChange={(value) => onPath('simulation.print_illuminant', value)}
          />
        </FieldRow>
      </Disclosure>

      <Disclosure title="颗粒" open={open.grain} onToggle={() => toggle('grain')}>
        <FieldRow label="启用">
          <Toggle checked={boolAt(state, 'grain.active', true)} onChange={(value) => onPath('grain.active', value)} />
        </FieldRow>
        {slider('grain-area', 'grain.particle_area_um2', '颗粒面积', 0.05, 1, 0.01, 2, ' μm²')}
        {slider('grain-blur', 'grain.blur', '颗粒柔化', 0, 2, 0.01, 2)}
        {slider('grain-uniform', 'grain.uniformity.0', '颗粒均匀度', 0.8, 1, 0.001, 3)}
      </Disclosure>

      <Disclosure title="光晕" open={open.halation} onToggle={() => toggle('halation')}>
        <FieldRow label="启用">
          <Toggle checked={boolAt(state, 'halation.active', true)} onChange={(value) => onPath('halation.active', value)} />
        </FieldRow>
        {slider('halation-amount', 'halation.halation_amount', '光晕强度', 0, 4, 0.01, 2)}
        {slider('halation-scale', 'halation.halation_spatial_scale', '光晕范围', 0.2, 4, 0.01, 2)}
        {slider('scatter-amount', 'halation.scatter_amount', '散射强度', 0, 4, 0.01, 2)}
        {slider('scatter-scale', 'halation.scatter_spatial_scale', '散射范围', 0.2, 4, 0.01, 2)}
      </Disclosure>

      <Disclosure title="眩光" open={open.glare} onToggle={() => toggle('glare')}>
        <FieldRow label="启用">
          <Toggle checked={boolAt(state, 'glare.active', true)} onChange={(value) => onPath('glare.active', value)} />
        </FieldRow>
        {slider('glare-percent', 'glare.percent', '眩光强度', 0, 0.2, 0.001, 3)}
        {slider('glare-rough', 'glare.roughness', '眩光粗糙度', 0, 1, 0.01, 2)}
      </Disclosure>

      <Disclosure title="扩散滤镜" open={open.diffusion} onToggle={() => toggle('diffusion')}>
        <FieldRow label="启用">
          <Toggle
            checked={boolAt(state, 'camera.diffusion_filter.active', false)}
            onChange={(value) => onPath('camera.diffusion_filter.active', value)}
          />
        </FieldRow>
        <FieldRow label="滤镜族">
          <Select
            value={stringAt(state, 'camera.diffusion_filter.filter_family', 'black_pro_mist')}
            options={bootstrap.options.diffusion_families.map((value) => ({ value, label: value }))}
            onChange={(value) => onPath('camera.diffusion_filter.filter_family', value)}
          />
        </FieldRow>
        {slider('diff-strength', 'camera.diffusion_filter.strength', '强度', 0, 1, 0.01, 2)}
        {slider('diff-scale', 'camera.diffusion_filter.spatial_scale', '范围', 0.2, 3, 0.01, 2)}
      </Disclosure>

      <Disclosure title="扫描" open={open.scanner} onToggle={() => toggle('scanner')}>
        {slider('unsharp', 'scanner.unsharp_mask.0', 'USM 强度', 0, 2, 0.01, 2)}
        {slider('scan-blur', 'scanner.lens_blur', '扫描镜头模糊', 0, 3, 0.01, 2)}
        {slider('white-level', 'scanner.white_level', '白场', 0.8, 1, 0.001, 3)}
        {slider('black-level', 'scanner.black_level', '黑场', 0, 0.1, 0.001, 3)}
      </Disclosure>

      <Disclosure title="输出" open={open.output} onToggle={() => toggle('output')}>
        <FieldRow label="输出色彩空间">
          <Select
            value={stringAt(state, 'simulation.output_color_space', 'sRGB')}
            options={colorSpaces}
            onChange={(value) => onPath('simulation.output_color_space', value)}
          />
        </FieldRow>
        <FieldRow label="保存色彩空间">
          <Select
            value={stringAt(state, 'simulation.saving_color_space', 'sRGB')}
            options={colorSpaces}
            onChange={(value) => onPath('simulation.saving_color_space', value)}
          />
        </FieldRow>
        <FieldRow label="保存 CCTF 编码">
          <Toggle
            checked={boolAt(state, 'simulation.saving_cctf_encoding', true)}
            onChange={(value) => onPath('simulation.saving_cctf_encoding', value)}
          />
        </FieldRow>
        <FieldRow label="正片扫描模式">
          <Toggle
            checked={boolAt(state, 'simulation.scan_film', false)}
            onChange={(value) => onPath('simulation.scan_film', value)}
          />
        </FieldRow>
        <FieldRow label="自动预览">
          <Toggle
            checked={boolAt(state, 'simulation.auto_preview', true)}
            onChange={(value) => onPath('simulation.auto_preview', value)}
          />
        </FieldRow>
      </Disclosure>

      <Disclosure title="显示" open={open.display} onToggle={() => toggle('display')}>
        <SwitchRow
          label="预览边框"
          checked={borderOn}
          onChange={onBorderChange}
          hint="只影响显影台预览白边，不写入成片；宽度由下面的白边比例控制"
        />
        {slider('white-padding', 'display.white_padding', '白边比例', 0, 0.2, 0.005, 3)}
        {slider('preview-size', 'display.preview_max_size', '预览长边', 128, 2048, 128, 0, ' px')}
      </Disclosure>
    </div>
  )
}
