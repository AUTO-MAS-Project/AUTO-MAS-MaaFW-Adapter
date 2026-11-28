<script setup lang="ts">
import { computed } from 'vue'
import { input, selection, type Panel } from './bridge'
import ConfigField from './ConfigField.vue'
import {
  buildPeriodTaskOptions,
  parseTaskNameList,
  PERIOD_KEYS,
  stringifyTaskNameList,
  type PeriodKey,
} from './script/periodTasks'
import { parseTaskLimitOverrides, stringifyTaskLimitOverrides } from './script/taskTimeLimits'
import type { MaaFWInterfacePreviewData } from './types'

const { panel, preview } = defineProps<{
  panel: Panel
  preview: MaaFWInterfacePreviewData | null
}>()
const { t } = panel
const taskOptions = computed(() => buildPeriodTaskOptions(preview?.tasks ?? []))
const limits = computed(() => parseTaskLimitOverrides(panel.value('Run', 'TaskTimeLimitOverrides')))
const fixedLimits = ['ProxyTimesLimit', 'RunTimesLimit', 'RunTimeLimit', 'TaskTimeLimit']

function updatePeriod(field: PeriodKey, event: Event) {
  const values = Array.from(selection(event).selectedOptions, option => option.value)
  const known = new Set(taskOptions.value.map(option => option.value))
  const hidden = parseTaskNameList(panel.value('Run', field)).filter(name => !known.has(name))
  return panel.run(() =>
    panel.saveField('Run', field, stringifyTaskNameList([...values, ...hidden]))
  )
}

function updateLimit(name: string, event: Event) {
  const field = input(event)
  if (!field.reportValidity()) return
  const next = { ...limits.value }
  if (field.value === '') delete next[name]
  else next[name] = field.valueAsNumber
  return panel.run(() =>
    panel.saveField('Run', 'TaskTimeLimitOverrides', stringifyTaskLimitOverrides(next))
  )
}
</script>

<template>
  <section class="card stack">
    <h2>{{ t('run') }}</h2>
    <div class="grid">
      <ConfigField
        v-for="(field, index) in fixedLimits"
        :key="field"
        :panel="panel"
        group="Run"
        :field="field"
        kind="number"
        :min="index === 1 || index === 2 ? 1 : 0"
        :max="9999"
      />
      <ConfigField :panel="panel" group="Run" field="LoopGuard" kind="toggle" />
    </div>
    <details v-if="taskOptions.length">
      <summary>{{ t('periodTasks') }}</summary>
      <div class="grid">
        <label v-for="field in PERIOD_KEYS" :key="field">
          {{ t(field) }}
          <select multiple @change="updatePeriod(field, $event)">
            <option
              v-for="item in taskOptions"
              :key="item.value"
              :value="item.value"
              :selected="parseTaskNameList(panel.value('Run', field)).includes(item.value)"
            >
              {{ item.label }}
            </option>
          </select>
        </label>
      </div>
    </details>
    <details v-if="taskOptions.length">
      <summary>{{ t('taskLimits') }}</summary>
      <div class="grid">
        <label v-for="item in taskOptions" :key="item.value">
          {{ item.label }}
          <input
            type="number"
            min="0"
            max="9999"
            :value="limits[item.value]"
            :placeholder="t('taskLimitDefault')"
            @change="updateLimit(item.value, $event)"
          />
        </label>
      </div>
    </details>
  </section>
</template>
