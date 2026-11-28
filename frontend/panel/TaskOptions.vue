<script setup lang="ts">
import { computed } from 'vue'
import { input, selection, type Panel } from './bridge'
import { getCheckboxCountState, isCheckboxCaseLocked } from './queue/maafwOptionConstraints'
import {
  activeMaaFWNestedOptionGroups,
  checkMaaFWInputValue,
  effectiveMaaFWInputFieldValue,
  isMaaFWBooleanInput,
  isMaaFWChoiceOption,
  isMaaFWOptionActiveFor,
  isMaaFWTruthyInputText,
  maafwInputPathKind,
  resolveMaaFWCheckboxValue,
  resolveMaaFWChoiceValue,
  storedMaaFWInputFieldValue,
} from './queue/maafwOptionValues'
import type { MaaFWOptionInfo, MaaFWOptionInputInfo, MaaFWTaskOptionValue } from './types'

type Values = Record<string, MaaFWTaskOptionValue>
const props = defineProps<{
  panel: Panel
  options: readonly MaaFWOptionInfo[]
  names: readonly string[]
  controller: string
  resource: string
  values: Values
  save: (values: Values) => Promise<void>
}>()
const { panel } = props
const { t } = panel

const visible = computed(() => {
  const byName = new Map(props.options.map(option => [option.name, option]))
  const selected = new Map<string, MaaFWOptionInfo>()
  function visit(names: readonly string[]) {
    for (const name of names) {
      const option = byName.get(name)
      if (
        !option ||
        selected.has(name) ||
        !isMaaFWOptionActiveFor(option, props.controller, props.resource)
      )
        continue
      selected.set(name, option)
      for (const group of activeMaaFWNestedOptionGroups(option, props.values[name])) visit(group)
    }
  }
  visit(props.names)
  return [...selected.values()].filter(
    option => option.type === 'input' || option.type === 'checkbox' || isMaaFWChoiceOption(option)
  )
})

const checked = (option: MaaFWOptionInfo) =>
  resolveMaaFWCheckboxValue(option, props.values[option.name])

function choiceCountProblem(option: MaaFWOptionInfo) {
  const state = getCheckboxCountState(option, checked(option))
  if (state?.violation === 'min') return t('checkboxMin').replace('{count}', String(state.min))
  if (state?.violation === 'max') return t('checkboxMax').replace('{count}', String(state.max))
  return ''
}

function saveValue(option: MaaFWOptionInfo, value: MaaFWTaskOptionValue) {
  return props.save({ ...props.values, [option.name]: value })
}

function changeCase(option: MaaFWOptionInfo, name: string, enabled: boolean) {
  const next = checked(option).filter(item => item !== name)
  if (enabled) next.push(name)
  return panel.run(() =>
    saveValue(
      option,
      option.cases.filter(item => next.includes(item.name)).map(item => item.name)
    )
  )
}

function fieldValue(option: MaaFWOptionInfo, field: MaaFWOptionInputInfo) {
  const value = effectiveMaaFWInputFieldValue(field, props.values[option.name])
  return field.password || value.startsWith('mas-dpapi:') ? '' : value
}

async function saveField(option: MaaFWOptionInfo, field: MaaFWOptionInputInfo, value: string) {
  const problem = checkMaaFWInputValue(field, value)
  if (problem) throw new Error(field.verifyError || field.patternMsg || t(problem))
  const current = props.values[option.name]
  const fields = typeof current === 'object' && !Array.isArray(current) ? current : {}
  await saveValue(option, { ...fields, [field.name]: value })
}

function pick(option: MaaFWOptionInfo, field: MaaFWOptionInputInfo) {
  return panel.run(async () => {
    const mode = maafwInputPathKind(field)
    if (!mode) return
    const path = await panel.pickPath(
      mode === 'directory' ? 'folder' : 'file',
      fieldValue(option, field)
    )
    if (path) await saveField(option, field, path)
  })
}
</script>

<template>
  <div v-if="visible.length" class="stack">
    <div v-for="option in visible" :key="option.name" class="stack">
      <label v-if="isMaaFWChoiceOption(option)">
        {{ option.label || option.name }}
        <select
          :value="resolveMaaFWChoiceValue(option, values[option.name])"
          @change="panel.run(() => saveValue(option, selection($event).value))"
        >
          <option v-for="item in option.cases" :key="item.name" :value="item.name">
            {{ item.label || item.name }}
          </option>
        </select>
      </label>
      <fieldset v-else-if="option.type === 'checkbox'">
        <legend>{{ option.label || option.name }}</legend>
        <p v-if="choiceCountProblem(option)" class="field-error">
          {{ choiceCountProblem(option) }}
        </p>
        <div class="checks">
          <label
            v-for="item in option.cases"
            :key="item.name"
            :title="item.description ?? undefined"
          >
            <input
              type="checkbox"
              :checked="checked(option).includes(item.name)"
              :disabled="isCheckboxCaseLocked(option, checked(option), item.name)"
              @change="changeCase(option, item.name, input($event).checked)"
            />
            {{ item.label || item.name }}
          </label>
        </div>
      </fieldset>
      <template v-else>
        <strong>{{ option.label || option.name }}</strong>
        <div class="grid">
          <label
            v-for="field in option.inputs"
            :key="field.name"
            :title="field.description ?? undefined"
          >
            {{ field.label || field.name }}
            <input
              v-if="isMaaFWBooleanInput(field) && !field.password"
              type="checkbox"
              :checked="isMaaFWTruthyInputText(fieldValue(option, field))"
              @change="panel.run(() => saveField(option, field, String(input($event).checked)))"
            />
            <span v-else class="actions">
              <input
                :type="field.password ? 'password' : 'text'"
                :value="fieldValue(option, field)"
                autocomplete="off"
                :placeholder="
                  field.password && storedMaaFWInputFieldValue(values[option.name], field.name)
                    ? t('configured')
                    : undefined
                "
                @change="
                  panel.run(async () => {
                    const element = input($event)
                    await saveField(option, field, element.value)
                    if (field.password) element.value = ''
                  })
                "
              />
              <button
                v-if="maafwInputPathKind(field) && !field.password"
                type="button"
                @click.prevent="pick(option, field)"
              >
                {{ t('browse') }}
              </button>
              <button
                v-if="field.password && storedMaaFWInputFieldValue(values[option.name], field.name)"
                type="button"
                @click.prevent="panel.run(() => saveField(option, field, ''))"
              >
                {{ t('clear') }}
              </button>
            </span>
          </label>
        </div>
      </template>
      <p v-if="option.description" class="hint">{{ option.description }}</p>
    </div>
  </div>
</template>
