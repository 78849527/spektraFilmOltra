import { useState } from 'react'
import { pickFolder } from '../api'
import type { ExportSettings } from '../types'
import { Button, FieldRow, Select } from './Controls'

const FORMATS = ['JPEG', 'PNG', 'TIFF', 'EXR']

export function ExportDialog({
  initial,
  onClose,
  onConfirm,
  notice,
}: {
  initial: ExportSettings
  onClose: () => void
  onConfirm: (settings: ExportSettings) => void
  notice?: string | null
}) {
  const [settings, setSettings] = useState<ExportSettings>({ ...initial })

  function update<K extends keyof ExportSettings>(key: K, value: ExportSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  async function chooseDirectory() {
    const folder = await pickFolder()
    if (folder) update('directory', folder)
  }

  return (
    <div className="modal-scrim" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">导出设置</div>
        </div>
        <div className="modal-body">
          <FieldRow label="格式">
            <Select
              value={settings.format}
              options={FORMATS.map((format) => ({ value: format, label: format }))}
              onChange={(value) => update('format', value)}
            />
          </FieldRow>
          <FieldRow label="位深">
            <Select
              value={String(settings.bit_depth)}
              options={[8, 16, 32].map((depth) => ({ value: String(depth), label: `${depth} bit` }))}
              onChange={(value) => update('bit_depth', Number(value))}
            />
          </FieldRow>
          {settings.format === 'JPEG' ? (
            <FieldRow label="质量">
              <input
                className="input num"
                value={settings.jpeg_quality}
                onChange={(event) => update('jpeg_quality', Number(event.target.value) || 1)}
              />
            </FieldRow>
          ) : null}
          {settings.format === 'PNG' ? (
            <FieldRow label="压缩">
              <Select
                value={String(settings.png_compression)}
                options={Array.from({ length: 10 }, (_, index) => ({
                  value: String(index),
                  label: String(index),
                }))}
                onChange={(value) => update('png_compression', Number(value))}
              />
            </FieldRow>
          ) : null}
          {settings.format === 'TIFF' ? (
            <FieldRow label="压缩">
              <Select
                value={settings.tiff_compression}
                options={['none', 'zip', 'lzw'].map((value) => ({ value, label: value }))}
                onChange={(value) => update('tiff_compression', value)}
              />
            </FieldRow>
          ) : null}
          {settings.format === 'EXR' ? (
            <FieldRow label="压缩">
              <Select
                value={settings.exr_compression}
                options={['zip', 'piz', 'rle'].map((value) => ({ value, label: value }))}
                onChange={(value) => update('exr_compression', value)}
              />
            </FieldRow>
          ) : null}
          <FieldRow label="长边像素">
            <input
              className="input num"
              value={settings.long_edge}
              onChange={(event) => update('long_edge', Number(event.target.value) || 0)}
            />
          </FieldRow>
          <FieldRow label="目录">
            <button className="button button-secondary" onClick={chooseDirectory}>
              <span className="truncate">{settings.directory || '与原文件相同'}</span>
            </button>
          </FieldRow>
          <FieldRow label="文件名">
            <input
              className="input"
              value={settings.filename_template}
              onChange={(event) => update('filename_template', event.target.value)}
            />
          </FieldRow>
          <div className="micro" style={{ marginTop: 8 }}>
            可用变量：{'{name}'} 原文件名 · {'{film}'} 胶片 · {'{paper}'} 相纸
          </div>
          {notice ? (
            <div className="micro" style={{ marginTop: 10, color: '#c08a2e' }}>
              {notice}
            </div>
          ) : null}
        </div>
        <div className="modal-foot">
          <Button kind="secondary" onClick={onClose}>
            取消
          </Button>
          <Button kind="primary" onClick={() => onConfirm(settings)}>
            导出
          </Button>
        </div>
      </div>
    </div>
  )
}
