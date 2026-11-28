<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { selection, usePanel } from './bridge'
import ConfigField from './ConfigField.vue'
import ScriptRun from './ScriptRun.vue'
import ScriptHotkeys from './ScriptHotkeys.vue'
import { resolveMaaFWProjectName } from './script/maafwProjectName'
import { allHotkeyOptions, mergeImportedHotkeys } from './script/hotkeyImport'
import { parseHotkeyMap } from './script/hotkeyOptions'
import type {
  MaaFWInterfacePreviewData,
  MaaFWShellInstanceItem,
  MaaFWShellInstanceImportItem,
} from './types'

type Context = {
  path: string | null
  preferAdb: boolean
  preview: MaaFWInterfacePreviewData | null
}
const panel = usePanel()
const { t, error, status, disabled, working, config, target } = panel
const context = shallowRef<Context>()
const preview = computed(() => context.value?.preview ?? null)
const controllers = computed(() => preview.value?.controllers ?? [])
const supported = (type: string) => type === 'Adb' || type === 'Win32'
const directControllers = computed(() => controllers.value.filter(item => supported(item.type)))
function selectController(name: string) {
  return (
    directControllers.value.find(item => item.name === name) ??
    (context.value?.preferAdb
      ? directControllers.value.find(item => item.type === 'Adb')
      : undefined) ??
    directControllers.value[0]
  )
}
const controller = computed(() => selectController(String(config.value.Info?.Controller ?? '')))
function resourcesFor(name: string) {
  return (
    preview.value?.resources.filter(
      item => !name || !item.controller.length || item.controller.includes(name)
    ) ?? []
  )
}
const resources = computed(() => resourcesFor(controller.value?.name ?? ''))
const desktop = computed(() => controller.value?.type === 'Win32')
const shell = shallowRef<MaaFWShellInstanceItem[]>()
const picked = ref<string[]>([])
const importKeys = ref(false)
const shellResult = shallowRef<MaaFWShellInstanceImportItem[]>([])
const packageCandidates = ref<string[]>([])

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

function importProject() {
  return panel.run(async () => {
    const path = await panel.pickPath('folder', context.value?.path ?? undefined)
    if (!path) return
    const result = await panel.request<{ changed: boolean }>('POST', '/project', { path })
    shell.value = undefined
    picked.value = []
    shellResult.value = []
    await reload()
    const project = preview.value?.project
    if (project) {
      const name = resolveMaaFWProjectName(project)
      const current = config.value.Info?.Name
      const changes = [{ group: 'Info', field: 'ProjectLabel', value: name }]
      if (
        !current ||
        current === config.value.Info?.ProjectLabel ||
        current === '新 MFW 托管' ||
        current === '新 MFW 脚本'
      )
        changes.push({ group: 'Info', field: 'Name', value: name })
      await panel.save(changes)
    }
    status.value = result.changed ? 'imported' : 'unchangedSource'
  })
}

function action(suffix: string, body?: object) {
  return panel.run(async () => {
    const result = await panel.request<{ outcome?: string; message?: string; changed?: boolean }>(
      'POST',
      suffix,
      body
    )
    await reload()
    status.value =
      result.message || result.outcome || (result.changed ? 'synced' : 'unchangedSource')
  })
}

function changeController(name: string) {
  return panel.run(async () => {
    const changes = [{ group: 'Info', field: 'Controller', value: name }]
    const currentResource = config.value.Info?.Resource
    if (
      currentResource &&
      !resourcesFor(selectController(name)?.name ?? '').some(item => item.name === currentResource)
    )
      changes.push({ group: 'Info', field: 'Resource', value: '' })
    await panel.save(changes)
    packageCandidates.value = []
  })
}

function detectPackage() {
  return panel.run(async () => {
    const configured = config.value.Info?.Resource
    const resource = resources.value.find(item => item.name === configured) ?? resources.value[0]
    const result = await panel.request<{ package: string | null; candidates: string[] }>(
      'POST',
      '/game-package',
      { resource: resource?.name ?? '' }
    )
    packageCandidates.value = result.candidates
    if (result.package) await panel.saveField('Game', 'PackageName', result.package)
    else if (!result.candidates.length) status.value = 'packageMissing'
  })
}

function scanShell() {
  return panel.run(async () => {
    const result = await panel.request<{ data: MaaFWShellInstanceItem[] }>('POST', '/shell')
    shell.value = result.data
    picked.value = result.data.filter(item => item.active).map(item => item.id)
    shellResult.value = []
  })
}

function importShell() {
  return panel.run(async () => {
    const { data } = await panel.request<{ data: MaaFWShellInstanceImportItem[] }>(
      'POST',
      '/shell/import',
      { instances: picked.value }
    )
    shellResult.value = data
    if (importKeys.value) {
      let keys = parseHotkeyMap(String(panel.value('Game', 'Hotkeys') ?? ''))
      const options = allHotkeyOptions(preview.value)
      for (const item of shell.value ?? []) {
        if (data.some(result => result.instanceId === item.id && result.success) && item.hotkeys)
          keys = mergeImportedHotkeys(keys, options, item.hotkeys)
      }
      await panel.saveField('Game', 'Hotkeys', JSON.stringify(keys))
    }
    picked.value = []
  })
}
</script>

<template>
  <p v-if="working" role="status">{{ t('working') }}</p>
  <p v-if="error" role="alert" class="field-error">{{ error }}</p>
  <p v-else-if="status" role="status">{{ t(status) }}</p>
  <fieldset v-if="target" :disabled="disabled" class="stack">
    <section class="card stack">
      <h2>{{ t('project') }}</h2>
      <div class="grid">
        <ConfigField :panel="panel" group="Info" field="Name" />
        <label
          >{{ t('projectPath') }}
          <span class="actions">
            <input :value="context?.path" readonly />
            <button type="button" @click.prevent="importProject">{{ t('importProject') }}</button>
          </span>
        </label>
      </div>
      <p v-if="preview">
        {{ resolveMaaFWProjectName(preview.project) }} {{ preview.project.version }}
      </p>
      <div class="actions">
        <button type="button" @click="panel.run(reload)">{{ t('refreshPreview') }}</button>
        <button type="button" :disabled="!preview" @click="action('/sync')">
          {{ t('syncProject') }}
        </button>
        <button type="button" :disabled="!preview" @click="action('/environment')">
          {{ t('prepareEnvironment') }}
        </button>
      </div>
      <ConfigField :panel="panel" group="Embedded" field="FollowSource" kind="toggle" />
    </section>

    <section v-if="preview" class="card stack">
      <h2>{{ t('control') }}</h2>
      <div class="grid">
        <label
          >{{ t('controller') }}
          <select
            :value="config.Info?.Controller"
            @change="changeController(selection($event).value)"
          >
            <option value="">{{ t('automatic') }}</option>
            <option
              v-for="item in controllers"
              :key="item.name"
              :value="item.name"
              :disabled="!supported(item.type)"
            >
              {{ item.label || item.name }} · {{ item.type }}
              {{ supported(item.type) ? '' : t('unsupportedController') }}
            </option>
          </select>
        </label>
        <label
          >{{ t('resource') }}
          <select
            :value="config.Info?.Resource"
            @change="panel.run(() => panel.saveField('Info', 'Resource', selection($event).value))"
          >
            <option value="">{{ t('automatic') }}</option>
            <option v-for="item in resources" :key="item.name" :value="item.name">
              {{ item.label || item.name }}
            </option>
          </select>
        </label>
      </div>
      <details v-if="!controller || controller.type === 'Adb'">
        <summary>ADB</summary>
        <div class="grid">
          <ConfigField :panel="panel" group="Device" field="AdbAddress" />
          <ConfigField :panel="panel" group="Device" field="AdbPath" kind="file" />
          <ConfigField :panel="panel" group="Game" field="PackageName" />
          <div class="actions">
            <button type="button" @click="detectPackage">{{ t('detectPackage') }}</button>
            <select
              v-if="packageCandidates.length > 1"
              :aria-label="t('PackageName')"
              value=""
              @change="
                panel.run(() => panel.saveField('Game', 'PackageName', selection($event).value))
              "
            >
              <option value="" disabled>{{ t('PackageName') }}</option>
              <option v-for="name in packageCandidates" :key="name">{{ name }}</option>
            </select>
          </div>
        </div>
      </details>
      <details v-if="!controller || desktop">
        <summary>{{ t('desktop') }}</summary>
        <div class="grid">
          <ConfigField
            :panel="panel"
            group="Game"
            field="LaunchMode"
            kind="select"
            :choices="['DirectExe', 'URL', 'AttachOnly']"
          />
          <ConfigField :panel="panel" group="Game" field="LaunchPath" kind="file" />
          <ConfigField
            v-if="config.Game?.LaunchMode === 'DirectExe'"
            :panel="panel"
            group="Game"
            field="Arguments"
          />
          <ConfigField
            v-if="config.Game?.LaunchMode === 'URL'"
            :panel="panel"
            group="Game"
            field="URL"
          />
          <template v-if="config.Game?.LaunchMode === 'AttachOnly'">
            <ConfigField :panel="panel" group="Game" field="LauncherPath" kind="file" />
            <ConfigField
              :panel="panel"
              group="Game"
              field="CloseMode"
              kind="select"
              :choices="['Script', 'OnFailure', 'Always']"
            />
          </template>
          <ConfigField
            v-else
            :panel="panel"
            group="Game"
            field="UnityResolution"
            kind="select"
            :choices="['Off', '1920x1080', '1280x720']"
          />
          <ConfigField :panel="panel" group="Device" field="HWnd" kind="number" :min="0" />
        </div>
      </details>
      <ConfigField
        :panel="panel"
        group="Game"
        field="WaitTime"
        kind="number"
        :min="0"
        :max="9999"
      />
      <ScriptHotkeys
        v-if="controller?.type === 'Win32'"
        :panel="panel"
        :preview="preview"
        :controller="controller.name"
        :resource="String(config.Info?.Resource || resources[0]?.name || '')"
      />
    </section>

    <ScriptRun :panel="panel" :preview="preview" />

    <section v-if="preview" class="card stack">
      <h2>{{ t('update') }}</h2>
      <div class="actions">
        <button type="button" @click="action('/update', { action: 'check' })">
          {{ t('checkUpdate') }}
        </button>
        <button type="button" @click="action('/update', { action: 'apply' })">
          {{ t('applyUpdate') }}
        </button>
      </div>
    </section>
    <section v-if="preview" class="card stack">
      <h2>{{ t('shellImport') }}</h2>
      <div class="actions">
        <button type="button" @click="scanShell">{{ t('scanShell') }}</button>
        <button type="button" :disabled="!picked.length" @click="importShell">
          {{ t('importUsers') }}
        </button>
      </div>
      <p v-if="shell?.length === 0">{{ t('noShell') }}</p>
      <div v-if="shell?.length" class="checks">
        <label v-for="item in shell" :key="item.id">
          <input v-model="picked" type="checkbox" :value="item.id" />
          {{ item.userName }} · {{ item.source }} ({{ item.taskCount ?? 0 }})
        </label>
        <label><input v-model="importKeys" type="checkbox" />{{ t('importHotkeys') }}</label>
      </div>
      <p
        v-for="item in shellResult"
        :key="item.instanceId"
        :class="{ 'field-error': !item.success }"
      >
        {{ item.name || item.instanceName }} ·
        {{ item.success ? item.importedTaskCount : item.error }}
        <span v-if="item.skipped?.length"> · {{ t('skipped') }} {{ item.skipped.join('、') }}</span>
      </p>
    </section>
  </fieldset>
</template>
