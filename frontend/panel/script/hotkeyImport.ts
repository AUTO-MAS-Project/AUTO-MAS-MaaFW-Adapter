// 把外壳（MXU / MFAAvalonia / MFW-PyQt6）实例里已经配好的键位带进脚本级 Game.Hotkeys：
// 键位弹窗的「从项目导入」与新建引导最后一步的「同时把键位导入到脚本」共用这里的纯逻辑。
import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from '../types'
import { formatHotkey, isStorableHotkey, parseHotkey } from './maafwHotkey'
import { effectiveHotkeyValues, mergeHotkeyMap, type MaaFWHotkeyMap } from './hotkeyOptions'

export interface MaaFWHotkeyImportResult {
  /** 要填进去的字段（按存储串归一过），只含候选里有值且支持的 */
  values: MaaFWHotkeyMap
  /** 填进去的字段数 */
  applied: number
  /** 按键不支持、跳过的字段数 */
  skipped: number
}

/**
 * 把一份键位换成要填进弹窗草稿的值：展示的每个字段候选里有值就归一后填，主键不支持或解析不出的
 * 跳过并计数。修饰键个数与项目要的不符照样填，由弹窗标红并拦住保存。
 */
export const importHotkeyValues = (
  options: readonly MaaFWOptionInfo[],
  hotkeys: MaaFWHotkeyMap
): MaaFWHotkeyImportResult => {
  const values: MaaFWHotkeyMap = {}
  let applied = 0
  let skipped = 0
  for (const option of options) {
    for (const field of option.hotkeys ?? []) {
      const value = hotkeys[option.name]?.[field.name]
      if (typeof value !== 'string' || !value.trim()) continue
      if (!isStorableHotkey(value)) {
        skipped += 1
        continue
      }
      values[option.name] = {
        ...values[option.name],
        [field.name]: formatHotkey(parseHotkey(value)),
      }
      applied += 1
    }
  }
  return { values, applied, skipped }
}

/** interface 里全部 hotkey option（不按控制器 / 资源过滤：Game.Hotkeys 按 option 名存，切换后照样用） */
export const allHotkeyOptions = (
  previewData: MaaFWInterfacePreviewData | null
): MaaFWOptionInfo[] =>
  (previewData?.options ?? []).filter(option => option.type === 'hotkey' && option.hotkeys?.length)

/**
 * 把导入的键位并进 Game.Hotkeys：只动导入里出现的 option，其余条目原样保留；这些 option 里导入没给
 * 或不支持的字段沿用已存的值；与默认相同的字段不存。
 */
export const mergeImportedHotkeys = (
  existing: MaaFWHotkeyMap,
  options: readonly MaaFWOptionInfo[],
  imported: MaaFWHotkeyMap
): MaaFWHotkeyMap => {
  const { values } = importHotkeyValues(options, imported)
  const touched = options.filter(option => values[option.name])
  if (touched.length === 0) return existing
  const merged = effectiveHotkeyValues(touched, existing)
  for (const option of touched) {
    merged[option.name] = { ...merged[option.name], ...values[option.name] }
  }
  return mergeHotkeyMap(existing, touched, merged)
}
