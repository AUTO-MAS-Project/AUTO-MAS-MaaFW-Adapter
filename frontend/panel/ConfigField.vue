<script setup lang="ts">
import { input, selection, type Panel } from './bridge'

const props = defineProps<{
  panel: Panel
  group: string
  field: string
  kind?: 'file' | 'number' | 'select' | 'toggle'
  choices?: string[]
  min?: number
  max?: number
}>()

function save(value: string | number | boolean | null) {
  return props.panel.run(() => props.panel.saveField(props.group, props.field, value))
}

function pick() {
  return props.panel.run(async () => {
    const value = props.panel.value(props.group, props.field)
    const path = await props.panel.pickPath('file', typeof value === 'string' ? value : undefined)
    if (path) await props.panel.saveField(props.group, props.field, path)
  })
}
</script>

<template>
  <label v-if="kind === 'toggle'" class="switch-tile">
    <input
      type="checkbox"
      :checked="panel.value(group, field) === true"
      @change="save(input($event).checked)"
    />
    {{ panel.t(field) }}
  </label>
  <label v-else>
    {{ panel.t(field) }}
    <select
      v-if="kind === 'select'"
      :value="panel.value(group, field)"
      @change="save(selection($event).value)"
    >
      <option v-for="choice in choices" :key="choice" :value="choice">{{ panel.t(choice) }}</option>
    </select>
    <span v-else-if="kind === 'file'" class="actions">
      <input :value="panel.value(group, field)" @change="save(input($event).value || null)" />
      <button type="button" @click.prevent="pick">{{ panel.t('browse') }}</button>
    </span>
    <input
      v-else-if="kind === 'number'"
      type="number"
      :min="min"
      :max="max"
      :value="panel.value(group, field)"
      @change="input($event).reportValidity() && save(input($event).valueAsNumber)"
      required
    />
    <input v-else :value="panel.value(group, field)" @change="save(input($event).value)" />
  </label>
</template>
