import type { MaaFWTaskInfo } from '../types'

/**
 * 任务在脚本当前的控制器 / 资源下能不能用：任务声明了 controller / resource 列表时必须包含当前那个。
 * 控制器或资源还没定（项目没有可用的）时一律不可用。用户页的队列显示、「添加任务」候选与
 * 「N 项不可用已隐藏」都按这一个口径。
 */
export function isMaaFWTaskActiveFor(
  task: Pick<MaaFWTaskInfo, 'controller' | 'resource'>,
  controllerName: string,
  resourceName: string
) {
  if (!controllerName || !resourceName) return false
  if (task.controller.length > 0 && !task.controller.includes(controllerName)) return false
  if (task.resource.length > 0 && !task.resource.includes(resourceName)) return false
  return true
}
