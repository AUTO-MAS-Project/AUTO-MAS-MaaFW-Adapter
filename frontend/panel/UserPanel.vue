<script setup lang="ts">
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import { input, usePanel } from './bridge'
import ConfigField from './ConfigField.vue'
import QueueSources from './QueueSources.vue'
import TaskOptions from './TaskOptions.vue'
import { isMaaFWTaskActiveFor } from './queue/maafwHiddenTasks'
import { maafwMissingTaskName } from './queue/maafwTaskChanges'
import { buildMaaFWTaskInstanceIds, resolveMaaFWTaskName } from './queue/maafwTaskInstance'
import {
  applyMaaFWTaskWeekdaysSelection,
  duplicateMaaFWQueuedTask,
  MAAFW_WEEKDAYS,
  maafwDisplayedTaskWeekdays,
  normalizeTaskSnapshot,
  withMaaFWTaskLabel,
} from './queue/maafwTaskSnapshot'
import {
  isSupportedMaaFWControllerType,
  type MaaFWInterfacePreviewData,
  type MaaFWTaskInfo,
  type MaaFWTaskSnapshot,
} from './types'

type Context = {
  controller: string
  resource: string
  preferAdb: boolean
  templates: string
  preview: MaaFWInterfacePreviewData | null
}
const panel = usePanel()
const { t, working, disabled, error, status } = panel
const context = shallowRef<Context>()
const preview = computed(() => context.value?.preview ?? null)
const tasks = computed(() => new Map(preview.value?.tasks.map(task => [task.name, task])))
const sourceSnapshot = computed(() => panel.value('Task', 'TaskSnapshot'))
const importedSnapshot = shallowRef<MaaFWTaskSnapshot>()
watch(sourceSnapshot, () => {
  importedSnapshot.value = undefined
})
const snapshot = computed(() =>
  normalizeTaskSnapshot(
    importedSnapshot.value ??
      (typeof sourceSnapshot.value === 'string' ? sourceSnapshot.value : null),
    preview.value,
    { keepMissing: true }
  )
)
const added = ref('')
const selected = ref('')

const controller = computed(() => {
  const controllers =
    preview.value?.controllers.filter(item => isSupportedMaaFWControllerType(item.type)) ?? []
  return (
    controllers.find(item => item.name === context.value?.controller) ??
    (context.value?.preferAdb ? controllers.find(item => item.type === 'Adb') : undefined) ??
    controllers[0]
  )
})
const controllerName = computed(() => controller.value?.name ?? '')
const resource = computed(() => {
  const resources =
    preview.value?.resources.filter(
      item => !item.controller.length || item.controller.includes(controllerName.value)
    ) ?? []
  return resources.find(item => item.name === context.value?.resource) ?? resources[0]
})
const resourceName = computed(() => resource.value?.name ?? '')
const available = computed(() =>
  [...tasks.value.values()].filter(
    task =>
      !task.unselectableReason &&
      isMaaFWTaskActiveFor(task, controllerName.value, resourceName.value)
  )
)
const nameOf = (id: string) => resolveMaaFWTaskName(id, tasks.value)
const taskFor = (id: string) => tasks.value.get(nameOf(id))
const pretask = (id: string) => taskFor(id)?.entry === 'MXU_PRETASK'
const visibleOrder = computed(() =>
  snapshot.value.taskOrder.filter(id => {
    const task = taskFor(id)
    return !task || isMaaFWTaskActiveFor(task, controllerName.value, resourceName.value)
  })
)
const selectedTask = computed(() => taskFor(selected.value))
const selectedOptions = computed(() => {
  const task = selectedTask.value
  if (!task) return []
  if (pretask(selected.value)) return task.option
  return [...(controller.value?.option ?? []), ...(resource.value?.option ?? []), ...task.option]
})

async function reload() {
  context.value = await panel.request<Context>('GET')
}

onMounted(
  () =>
    void panel.run(async () => {
      await panel.initialize()
      await reload()
    })
)

async function save(next: MaaFWTaskSnapshot, preset?: string) {
  const changes = [
    {
      group: 'Task',
      field: 'TaskSnapshot',
      value: JSON.stringify({ ...next, keepUnchecked: true }),
    },
  ]
  if (preset !== undefined) changes.push({ group: 'Task', field: 'SelectedPreset', value: preset })
  await panel.save(changes)
  importedSnapshot.value = undefined
}

function addTask() {
  return panel.run(async () => {
    const task = tasks.value.get(added.value)
    if (!task) return
    const next = snapshot.value
    const ids = buildMaaFWTaskInstanceIds(task.name, task.repeatCount, next.taskOrder)
    const order = [...next.taskOrder, ...ids]
    await save({
      ...next,
      taskOrder: [...order.filter(pretask), ...order.filter(id => !pretask(id))],
      taskChecked: { ...next.taskChecked, ...Object.fromEntries(ids.map(id => [id, true])) },
    })
    selected.value = ids[0]
    added.value = ''
  })
}

function duplicate(id: string) {
  return panel.run(async () => {
    const result = duplicateMaaFWQueuedTask(snapshot.value, id, nameOf(id))
    if (!result) return
    await save(result.snapshot)
    selected.value = result.taskId
  })
}

function move(id: string, offset: number) {
  return panel.run(async () => {
    const order = [...snapshot.value.taskOrder]
    const sibling = visibleOrder.value[visibleOrder.value.indexOf(id) + offset]
    if (!sibling || pretask(id) !== pretask(sibling)) return
    const from = order.indexOf(id)
    const to = order.indexOf(sibling)
    ;[order[from], order[to]] = [order[to], order[from]]
    await save({ ...snapshot.value, taskOrder: order })
  })
}

function remove(id: string) {
  return panel.run(async () => {
    if (!(await panel.confirm(t('confirmRemove'), true))) return
    const next = normalizeTaskSnapshot(
      {
        ...snapshot.value,
        taskOrder: snapshot.value.taskOrder.filter(item => item !== id),
      },
      preview.value,
      { keepMissing: true }
    )
    await save(next)
    if (selected.value === id) selected.value = ''
  })
}

function setDay(id: string, day: number, enabled: boolean) {
  const current = maafwDisplayedTaskWeekdays(snapshot.value, id)
  const days = enabled ? [...current, day] : current.filter(value => value !== day)
  return panel.run(() =>
    save({ ...snapshot.value, ...applyMaaFWTaskWeekdaysSelection(snapshot.value, id, days) })
  )
}

function setTaskOptions(values: MaaFWTaskSnapshot['taskOptions'][string]) {
  return save({
    ...snapshot.value,
    taskOptions: { ...snapshot.value.taskOptions, [selected.value]: values },
  })
}

function setLabel(event: Event, task: MaaFWTaskInfo) {
  const taskLabels = withMaaFWTaskLabel(
    snapshot.value.taskLabels,
    selected.value,
    input(event).value,
    task.label || task.name
  )
  return panel.run(() => save({ ...snapshot.value, taskLabels }))
}
</script>

<template>
  <p v-if="working" role="status">{{ t('working') }}</p>
  <p v-if="error" role="alert" class="field-error">{{ error }}</p>
  <p v-else-if="status" role="status">{{ t(status) }}</p>
  <fieldset v-if="panel.target.value" :disabled="disabled" class="stack">
    <section class="card stack">
      <h2>{{ t('queue') }}</h2>
      <div class="actions">
        <button type="button" @click="panel.run(reload)">{{ t('refreshPreview') }}</button>
        <p v-if="preview">
          {{ controller?.label || controllerName }} · {{ resource?.label || resourceName }}
        </p>
      </div>
      <p v-if="!preview" class="hint">{{ t('projectRequired') }}</p>
      <template v-else>
        <div class="actions task-select">
          <select v-model="added" :aria-label="t('addTask')">
            <option value="" disabled>{{ t('chooseTask') }}</option>
            <option v-for="task in available" :key="task.name" :value="task.name">
              {{ task.label || task.name }}
            </option>
          </select>
          <button type="button" :disabled="!added" @click="addTask">{{ t('addTask') }}</button>
        </div>
        <p v-if="!visibleOrder.length" class="hint">{{ t('emptyQueue') }}</p>
        <p v-if="visibleOrder.length !== snapshot.taskOrder.length" class="hint">
          {{ t('hiddenTasks') }} ({{ snapshot.taskOrder.length - visibleOrder.length }})
        </p>
        <ol v-if="visibleOrder.length">
          <li v-for="(id, index) in visibleOrder" :key="id">
            <div class="queue-row">
              <input
                type="checkbox"
                :aria-label="t('enabled')"
                :checked="snapshot.taskChecked[id] !== false"
                @change="
                  panel.run(() =>
                    save({
                      ...snapshot,
                      taskChecked: { ...snapshot.taskChecked, [id]: input($event).checked },
                    })
                  )
                "
              />
              <strong>{{
                snapshot.taskLabels?.[id] ||
                taskFor(id)?.label ||
                taskFor(id)?.name ||
                maafwMissingTaskName(id)
              }}</strong>
              <span v-if="!taskFor(id)" class="hint">{{ t('missingTask') }}</span>
              <button
                v-if="taskFor(id)"
                type="button"
                :aria-expanded="selected === id"
                @click="selected = selected === id ? '' : id"
              >
                {{ t('editTask') }}
              </button>
              <button
                type="button"
                :aria-label="t('moveUp')"
                :disabled="!index || pretask(id) !== pretask(visibleOrder[index - 1])"
                @click="move(id, -1)"
              >
                ↑
              </button>
              <button
                type="button"
                :aria-label="t('moveDown')"
                :disabled="
                  index === visibleOrder.length - 1 ||
                  pretask(id) !== pretask(visibleOrder[index + 1])
                "
                @click="move(id, 1)"
              >
                ↓
              </button>
              <button v-if="taskFor(id)" type="button" @click="duplicate(id)">
                {{ t('duplicate') }}
              </button>
              <button type="button" @click="remove(id)">{{ t('remove') }}</button>
            </div>
            <div v-if="selected === id && selectedTask" class="stack queue-editor">
              <label
                >{{ t('taskLabel') }}
                <input
                  :value="snapshot.taskLabels?.[id]"
                  :placeholder="selectedTask.label || selectedTask.name"
                  maxlength="40"
                  @change="setLabel($event, selectedTask)"
                />
              </label>
              <fieldset v-if="!pretask(id)">
                <legend>{{ t('weekdays') }}</legend>
                <div class="checks">
                  <label v-for="day in MAAFW_WEEKDAYS" :key="day">
                    <input
                      type="checkbox"
                      :checked="maafwDisplayedTaskWeekdays(snapshot, id).includes(day)"
                      @change="setDay(id, day, input($event).checked)"
                    />{{ t('day' + day) }}
                  </label>
                </div>
              </fieldset>
              <TaskOptions
                :panel="panel"
                :options="preview.options"
                :names="selectedOptions"
                :controller="controllerName"
                :resource="resourceName"
                :values="snapshot.taskOptions[id] ?? {}"
                :save="setTaskOptions"
              />
            </div>
          </li>
        </ol>
      </template>
    </section>
    <section v-if="preview?.globalOption.length" class="card stack">
      <h2>{{ t('globalOptions') }}</h2>
      <TaskOptions
        :panel="panel"
        :options="preview.options"
        :names="preview.globalOption"
        :controller="controllerName"
        :resource="resourceName"
        :values="snapshot.globalOptions ?? {}"
        :save="values => save({ ...snapshot, globalOptions: values })"
      />
    </section>
    <QueueSources
      v-if="preview && context"
      :panel="panel"
      :preview="preview"
      :snapshot="snapshot"
      :templates="context.templates"
      :available="available"
      :controller="controllerName"
      :resource="resourceName"
      :save="save"
      @templates="
        value => {
          if (context) context = { ...context, templates: value }
        }
      "
      @imported="
        value => {
          importedSnapshot = value
          selected = ''
        }
      "
    />
    <section class="card stack">
      <h2>{{ t('deviceOverrides') }}</h2>
      <div class="grid">
        <ConfigField
          v-if="!controller || controller.type === 'Adb'"
          :panel="panel"
          group="Device"
          field="AdbAddress"
        />
        <ConfigField
          v-if="!controller || controller.type === 'Win32' || controller.type === 'Gamepad'"
          :panel="panel"
          group="Device"
          field="HWnd"
          kind="number"
          :min="0"
        />
        <template v-if="!controller || controller.type === 'PlayCover'">
          <ConfigField :panel="panel" group="Device" field="PlayCoverAddress" />
          <ConfigField :panel="panel" group="Device" field="PlayCoverUuid" />
        </template>
      </div>
    </section>
  </fieldset>
</template>
