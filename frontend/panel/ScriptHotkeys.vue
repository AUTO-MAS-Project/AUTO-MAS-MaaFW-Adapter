<script setup lang="ts">
import { computed } from 'vue'
import type { Panel } from './bridge'
import {
  collectHotkeyOptions,
  effectiveHotkeyValues,
  hotkeyModifierProblem,
  mergeHotkeyMap,
  parseHotkeyMap,
} from './script/hotkeyOptions'
import {
  canonicalHotkey,
  formatHotkey,
  hotkeyFromKeyboardEvent,
  isStorableHotkey,
  parseHotkey,
} from './script/maafwHotkey'
import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from './types'

const { panel, preview, controller, resource } = defineProps<{
  panel: Panel
  preview: MaaFWInterfacePreviewData
  controller: string
  resource: string
}>()
const { t } = panel
const options = computed(() => collectHotkeyOptions(preview, controller, resource))
const stored = computed(() => parseHotkeyMap(String(panel.value('Game', 'Hotkeys') ?? '')))
const values = computed(() => effectiveHotkeyValues(options.value, stored.value))
type Hotkey = MaaFWOptionInfo['hotkeys'][number]

function save(option: MaaFWOptionInfo, field: Hotkey, value: string) {
  return panel.run(async () => {
    if (
      value &&
      (!isStorableHotkey(value) || hotkeyModifierProblem(parseHotkey(value), field.modifierCount))
    )
      throw new Error(t('invalidHotkey'))
    const next = {
      ...values.value,
      [option.name]: {
        ...values.value[option.name],
        [field.name]: canonicalHotkey(value || field.default),
      },
    }
    await panel.saveField(
      'Game',
      'Hotkeys',
      JSON.stringify(mergeHotkeyMap(stored.value, [option], next))
    )
  })
}

function capture(event: KeyboardEvent, option: MaaFWOptionInfo, field: Hotkey) {
  if (event.key === 'Tab') return
  event.preventDefault()
  const combo = hotkeyFromKeyboardEvent(event)
  if (combo.kind === 'combo') void save(option, field, formatHotkey(combo.keys))
  if (combo.kind === 'unsupported' || combo.kind === 'too-many-modifiers')
    panel.error.value = t('invalidHotkey')
}
</script>

<template>
  <details v-if="options.length">
    <summary>{{ t('hotkeys') }}</summary>
    <div v-for="option in options" :key="option.name" class="stack">
      <strong>{{ option.label || option.name }}</strong>
      <div class="grid">
        <label v-for="field in option.hotkeys" :key="field.name">
          {{ field.label || field.name }}
          <span class="actions">
            <input
              :value="values[option.name]?.[field.name]"
              :placeholder="t('recordHotkey')"
              readonly
              @keydown="capture($event, option, field)"
            />
            <button type="button" @click.prevent="save(option, field, '')">{{ t('reset') }}</button>
          </span>
        </label>
      </div>
    </div>
  </details>
</template>
