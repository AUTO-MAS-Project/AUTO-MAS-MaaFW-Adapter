export type MaaFWTaskOptionValue = string | string[] | Record<string, string>

export interface MaaFWShellInstanceItem {
  id: string
  name: string
  userName: string
  source: string
  active?: boolean
  taskCount?: number
  hotkeys?: Record<string, Record<string, string>>
}

export interface MaaFWShellInstanceImportItem {
  instanceId: string
  instanceName?: string
  name?: string
  success?: boolean
  importedTaskCount?: number
  skipped?: string[]
  error?: string
}

/**
 * 前三个字段的 key 都是「任务实例 id」而不是任务名：同一个任务可以被重复加入队列，
 * 首份的 id 就是裸任务名，第二份起是 `<任务名>__MAS_DUP__<随机后缀>`。
 */
export interface MaaFWTaskSnapshot {
  taskOrder: string[]
  taskChecked: Record<string, boolean>
  taskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>
  /** 新队列显式保留跳过实例；旧快照没有此键时仍隐藏未勾选实例 */
  keepUnchecked?: true
  /**
   * 全局选项（interface 的 global_option 及其子选项）的值：每个用户一份、所有任务共用，
   * taskOptions 里不再有它们。没设过任何全局选项时可以没有这个键（按默认值）。
   */
  globalOptions?: Record<string, MaaFWTaskOptionValue>
  /** 用户给某一份实例起的显示名（只影响显示，不改任务 name）；没改过名的实例不在里面 */
  taskLabels?: Record<string, string>
  /**
   * 用户给某一份实例设的运行日：`weekdays` 是 ISO 星期（1=周一 … 7=周日），升序去重。
   * 七天全选（不限制）的实例不在里面；一项都没有时不写这个键
   */
  taskSchedules?: Record<string, MaaFWTaskSchedule>
}

/** 一份实例的运行日 */
export interface MaaFWTaskSchedule {
  weekdays: number[]
}

export interface MaaFWProjectInfo {
  name: string
  label?: string | null
  title?: string | null
  version?: string | null
  github?: string | null
  mirrorchyanRid?: string | null
  mirrorchyanMultiplatform?: boolean | null
  description?: string | null
  icon?: string | null
}

const MAAFW_SUPPORTED_CONTROLLER_TYPES = ['Adb', 'Win32', 'Gamepad', 'PlayCover'] as const

export const isSupportedMaaFWControllerType = (type: string) =>
  (MAAFW_SUPPORTED_CONTROLLER_TYPES as readonly string[]).includes(type)

export interface MaaFWControllerInfo {
  name: string
  label?: string | null
  type: string
  description?: string | null
  icon?: string | null
  option: string[]
  permissionRequired: boolean
}

export interface MaaFWResourceInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  path: string[]
  controller: string[]
  option: string[]
}

export interface MaaFWGroupInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  defaultExpand: boolean
}

export interface MaaFWSettingInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
  defaultExpand: boolean
}

export interface MaaFWTaskInfo {
  name: string
  label?: string | null
  entry: string
  description?: string | null
  icon?: string | null
  group: string[]
  controller: string[]
  resource: string[]
  option: string[]
  defaultCheck: boolean
  /** 加入任务队列时展开成几份（interface 的 repeatable / repeat_count），缺省 1 */
  repeatCount?: number
  /**
   * 特调声明不可选时的原因（后端 `unselectable_entries`）：不进「添加任务」与预设模板，
   * 已在队列里的照常显示，运行时跳过。可选任务为空
   */
  unselectableReason?: string | null
}

export interface MaaFWOptionCaseInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
}

export interface MaaFWOptionInputInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  default?: string | null
  pipelineType?: string | null
  verify?: string | null
  verifyError?: string | null
  patternMsg?: string | null
  /** PI v2.10.0：密码 / 密钥字段，掩码输入，保存后只拿得到密文 */
  password?: boolean
  /** PI v2.10.5：编辑控件，file / directory 为路径框 + 系统选择对话框；缺省为 text */
  inputType?: 'text' | 'file' | 'directory'
}

export interface MaaFWOptionInfo {
  name: string
  type: string
  label?: string | null
  description?: string | null
  icon?: string | null
  controller: string[]
  resource: string[]
  cases: MaaFWOptionCaseInfo[]
  inputs: MaaFWOptionInputInfo[]
  hotkeys: Array<{
    name: string
    label?: string | null
    description?: string | null
    default?: string | null
    /** 项目 pipeline 用到的修饰键个数（0–2）：录制的组合键须恰好这么多修饰键 */
    modifierCount?: number
  }>
  defaultCase?: string | string[] | null
  /** PI v2.10.1：checkbox 最少 / 最多选择数，后端已放宽成自洽值；null 为不限 */
  minCount?: number | null
  maxCount?: number | null
}

export interface MaaFWAdbEmulatorExtraCapabilityInfo {
  screencap: boolean
  input: boolean
}

export interface MaaFWControlCapabilitiesInfo {
  emulatorExtras: Record<string, MaaFWAdbEmulatorExtraCapabilityInfo>
}

export interface MaaFWPresetInfo {
  name: string
  label?: string | null
  description?: string | null
  taskCount: number
  checkedCount: number
  snapshot: MaaFWTaskSnapshot
  /** PI v2.10.4：适用的控制器名，空为不限 */
  controller?: string[]
  resource?: string[]
}

export interface MaaFWInterfacePreviewData {
  path: string
  project: MaaFWProjectInfo
  globalOption: string[]
  controlCapabilities: MaaFWControlCapabilitiesInfo
  controllers: MaaFWControllerInfo[]
  resources: MaaFWResourceInfo[]
  groups: MaaFWGroupInfo[]
  settings: MaaFWSettingInfo[]
  tasks: MaaFWTaskInfo[]
  options: MaaFWOptionInfo[]
  presets: MaaFWPresetInfo[]
  importCount: number
  agentCount: number
}
