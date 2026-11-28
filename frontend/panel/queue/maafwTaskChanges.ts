import { MAAFW_DUPLICATE_TASK_SEPARATOR } from './maafwTaskInstance'

/** 对不上的实例 id → 原任务名：副本去掉 `__MAS_DUP__` 后缀 */
export const maafwMissingTaskName = (taskId: string) => {
  const separatorIndex = taskId.lastIndexOf(MAAFW_DUPLICATE_TASK_SEPARATOR)
  return separatorIndex > 0 ? taskId.slice(0, separatorIndex) : taskId
}
