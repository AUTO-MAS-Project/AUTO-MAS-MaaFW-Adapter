<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import { type Panel } from './bridge'
import {
  buildProjectPresetAppliedSnapshot,
  isPresetAvailableForController,
  selectPresetTemplateQueue,
} from './queue/maafwPresetQueue'
import {
  buildMaaFWQueueReplacement,
  describeMaaFWQueueSource,
  maafwPasswordFields,
} from './queue/maafwQueueSource'
import {
  addMaaFWQueueTemplate,
  buildMaaFWQueueTemplateSnapshot,
  parseMaaFWQueueTemplates,
  removeMaaFWQueueTemplate,
  renameMaaFWQueueTemplate,
  type MaaFWQueueTemplate,
} from './queue/maafwQueueTemplates'
import { resolveMaaFWTaskName } from './queue/maafwTaskInstance'
import { normalizeTaskSnapshot } from './queue/maafwTaskSnapshot'
import type {
  MaaFWInterfacePreviewData,
  MaaFWPresetInfo,
  MaaFWShellInstanceImportItem,
  MaaFWShellInstanceItem,
  MaaFWTaskInfo,
  MaaFWTaskSnapshot,
} from './types'

const props = defineProps<{
  panel: Panel
  preview: MaaFWInterfacePreviewData
  snapshot: MaaFWTaskSnapshot
  templates: string
  available: MaaFWTaskInfo[]
  controller: string
  resource: string
  save: (snapshot: MaaFWTaskSnapshot, preset: string) => Promise<void>
}>()
const emit = defineEmits<{ templates: [raw: string]; imported: [snapshot: MaaFWTaskSnapshot] }>()
const { panel } = props
const { t } = panel
const byName = computed(() => new Map(props.preview.tasks.map(task => [task.name, task])))
const active = computed(() => new Map(props.available.map(task => [task.name, task])))
const nameOf = (id: string) => resolveMaaFWTaskName(id, byName.value)
const pretask = (id: string) => byName.value.get(nameOf(id))?.entry === 'MXU_PRETASK'
const passwords = computed(() => maafwPasswordFields(props.preview.options))
const templates = computed(() => parseMaaFWQueueTemplates(props.templates))
const presetName = ref('')
const templateName = ref('')
const nextName = ref('')
const sourceUser = ref('')
const sourceShell = ref('')
const shellPath = ref<string>()
const shell = shallowRef<MaaFWShellInstanceItem[]>()
const users = shallowRef<{ id: string; name: string; snapshot: MaaFWTaskSnapshot }[]>()
const shellResult = shallowRef<MaaFWShellInstanceImportItem>()

function availablePreset(preset: MaaFWPresetInfo) {
  return (
    isPresetAvailableForController(preset, props.controller) &&
    (!preset.resource?.length || preset.resource.includes(props.resource))
  )
}

function applyPreset() {
  return panel.run(async () => {
    const preset = props.preview.presets.find(item => item.name === presetName.value)
    if (!preset || !availablePreset(preset)) return
    const source = normalizeTaskSnapshot(preset.snapshot, props.preview)
    const queue = selectPresetTemplateQueue(
      source.taskOrder,
      preset.snapshot,
      active.value,
      byName.value,
      pretask
    )
    if (!queue) throw new Error(t('emptySource'))
    if (!(await panel.confirm(t('confirmReplace')))) return
    const next = buildProjectPresetAppliedSnapshot(
      queue.entries,
      source.taskOptions,
      queue.pretasks,
      queue.pretaskEntries,
      props.snapshot,
      pretask,
      nameOf
    )
    await props.save(
      {
        ...next,
        globalOptions: { ...props.snapshot.globalOptions, ...source.globalOptions },
      },
      preset.name
    )
  })
}

function replace(raw: MaaFWTaskSnapshot) {
  return panel.run(async () => {
    const source = describeMaaFWQueueSource(
      normalizeTaskSnapshot(raw, props.preview, { keepMissing: true }),
      {
        taskByName: byName.value,
        availableTaskByName: active.value,
        isManagedTask: task => !!task.unselectableReason || task.entry === 'MXU_PRETASK',
        passwordFields: passwords.value,
        displayName: task => task.label || task.name,
      }
    )
    if (!source.entries.length) throw new Error(t('emptySource'))
    if (!(await panel.confirm(t('confirmReplace')))) return
    const next = buildMaaFWQueueReplacement(source, props.snapshot, pretask, passwords.value)
    await props.save({ ...next, globalOptions: props.snapshot.globalOptions }, '')
    if (source.invalidCount) panel.status.value = 'unavailableSkipped'
  })
}

function applyTemplate() {
  const template = templates.value.find(item => item.name === templateName.value)
  if (template) return replace(template.snapshot)
}

async function persistTemplates(next: MaaFWQueueTemplate[] | null) {
  if (!next) throw new Error(t('invalidTemplateName'))
  const result = await panel.request<{ templates: string }>('PUT', '/templates', {
    before: props.templates,
    templates: next,
  })
  emit('templates', result.templates)
}

function addTemplate() {
  return panel.run(async () => {
    const { taskOrder, taskOptions, taskLabels, taskChecked, taskSchedules } = props.snapshot
    const entries = taskOrder
      .filter(id => active.value.has(nameOf(id)) && !pretask(id))
      .map(id => ({ id }))
    if (!entries.length) throw new Error(t('emptySource'))
    const snapshot = buildMaaFWQueueTemplateSnapshot(
      entries,
      taskOptions,
      passwords.value,
      taskLabels,
      taskChecked,
      taskSchedules
    )
    const name = nextName.value.trim()
    await persistTemplates(addMaaFWQueueTemplate(templates.value, { name, snapshot }))
    templateName.value = name
    nextName.value = ''
  })
}

function renameTemplate() {
  return panel.run(async () => {
    const name = nextName.value.trim()
    await persistTemplates(renameMaaFWQueueTemplate(templates.value, templateName.value, name))
    templateName.value = name
    nextName.value = ''
  })
}

function deleteTemplate() {
  return panel.run(async () => {
    if (!(await panel.confirm(t('confirmRemoveTemplate'), true))) return
    await persistTemplates(removeMaaFWQueueTemplate(templates.value, templateName.value))
    templateName.value = ''
  })
}

function loadUsers() {
  return panel.run(async () => {
    users.value = await panel.request<NonNullable<typeof users.value>>('GET', '/queues')
    sourceUser.value = ''
  })
}

function copyUser() {
  const user = users.value?.find(item => item.id === sourceUser.value)
  if (user) return replace(user.snapshot)
}

function scanShell(pick = false) {
  return panel.run(async () => {
    const path = pick ? await panel.pickPath('folder', shellPath.value) : undefined
    if (pick && !path) return
    const result = await panel.request<{ data: MaaFWShellInstanceItem[] }>('POST', '/shell', {
      path,
    })
    shellPath.value = path ?? undefined
    shell.value = result.data
    sourceShell.value = result.data.find(item => item.active)?.id ?? ''
    shellResult.value = undefined
  })
}

function importShell() {
  return panel.run(async () => {
    if (!(await panel.confirm(t('confirmReplace')))) return
    const { data } = await panel.request<{
      data: { result: MaaFWShellInstanceImportItem | null; snapshot: MaaFWTaskSnapshot | null }
    }>('POST', '/shell/apply', { instance: sourceShell.value, path: shellPath.value })
    if (!data.result?.success || !data.snapshot)
      throw new Error(data.result?.error || t('shellFailed'))
    emit('imported', data.snapshot)
    shellResult.value = data.result
  })
}
</script>

<template>
  <section class="card stack">
    <h2>{{ t('queueSources') }}</h2>
    <details v-if="preview.presets.length">
      <summary>{{ t('presets') }}</summary>
      <div class="actions task-select">
        <select v-model="presetName" :aria-label="t('presets')">
          <option value="" disabled>{{ t('presets') }}</option>
          <option
            v-for="preset in preview.presets"
            :key="preset.name"
            :value="preset.name"
            :disabled="!availablePreset(preset)"
          >
            {{ preset.label || preset.name }}
          </option>
        </select>
        <button type="button" :disabled="!presetName" @click="applyPreset">{{ t('apply') }}</button>
      </div>
    </details>
    <details>
      <summary>{{ t('templates') }}</summary>
      <div class="stack">
        <div v-if="templates.length" class="actions task-select">
          <select v-model="templateName" :aria-label="t('templates')">
            <option value="" disabled>{{ t('templates') }}</option>
            <option v-for="template in templates" :key="template.name">{{ template.name }}</option>
          </select>
          <button type="button" :disabled="!templateName" @click="applyTemplate">
            {{ t('apply') }}
          </button>
          <button type="button" :disabled="!templateName" @click="deleteTemplate">
            {{ t('remove') }}
          </button>
        </div>
        <div class="actions">
          <input
            v-model="nextName"
            :aria-label="t('templateName')"
            :placeholder="t('templateName')"
          />
          <button type="button" :disabled="!nextName.trim()" @click="addTemplate">
            {{ t('saveTemplate') }}
          </button>
          <button
            type="button"
            :disabled="!templateName || !nextName.trim()"
            @click="renameTemplate"
          >
            {{ t('rename') }}
          </button>
        </div>
      </div>
    </details>
    <details>
      <summary>{{ t('otherUsers') }}</summary>
      <div class="stack">
        <div class="actions task-select">
          <button type="button" @click="loadUsers">{{ t('loadUsers') }}</button>
          <select v-if="users?.length" v-model="sourceUser" :aria-label="t('otherUsers')">
            <option value="" disabled>{{ t('otherUsers') }}</option>
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.name }}</option>
          </select>
          <button type="button" :disabled="!sourceUser" @click="copyUser">{{ t('apply') }}</button>
        </div>
        <p v-if="users?.length === 0" class="hint">{{ t('noOtherUsers') }}</p>
      </div>
    </details>
    <details>
      <summary>{{ t('shellImport') }}</summary>
      <div class="stack">
        <div class="actions task-select">
          <button type="button" @click="scanShell()">{{ t('scanShell') }}</button>
          <button type="button" @click="scanShell(true)">{{ t('browse') }}</button>
          <select v-if="shell?.length" v-model="sourceShell" :aria-label="t('shellImport')">
            <option value="" disabled>{{ t('shellImport') }}</option>
            <option v-for="item in shell" :key="item.id" :value="item.id">
              {{ item.name }} · {{ item.source }} ({{ item.taskCount ?? 0 }})
            </option>
          </select>
          <button type="button" :disabled="!sourceShell" @click="importShell">
            {{ t('apply') }}
          </button>
        </div>
        <p v-if="shell?.length === 0" class="hint">{{ t('noShell') }}</p>
        <p v-if="shellResult">
          {{ t('shellApplied') }} ({{ shellResult.importedTaskCount ?? 0 }})
          <span v-if="shellResult.skipped?.length">
            · {{ t('skipped') }} {{ shellResult.skipped.join('、') }}</span
          >
        </p>
      </div>
    </details>
  </section>
</template>
