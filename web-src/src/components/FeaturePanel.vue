<script setup>
defineProps({
  spec: { type: Object, required: true },
  modelValue: { type: Object, required: true },
  embedded: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue"]);

function displayValue(field, stored) {
  if (field.type === "yuan") return ((Number(stored) || 0) / 100).toString();
  if (field.type === "seconds") return ((Number(stored) || 0) / 1000).toString();
  return stored;
}

function change(config, field, event) {
  const next = { ...config };
  const key = field.key;
  if (field.type === "bool") {
    next[key] = event.target.checked;
  } else if (field.type === "select") {
    next[key] = Number(event.target.value);
  } else if (field.type === "yuan") {
    next[key] = Math.round(Number(event.target.value || 0) * 100);
  } else if (field.type === "seconds") {
    next[key] = Math.round(Number(event.target.value || 0) * 1000);
  } else if (field.type === "int") {
    next[key] = event.target.value === "" ? 0 : Number(event.target.value);
  } else {
    next[key] = event.target.value;
  }
  emit("update:modelValue", next);
}
</script>

<template>
  <component :is="embedded ? 'div' : 'section'" :class="embedded ? 'feature-subpanel' : 'panel'">
    <header>
      <h3 v-if="embedded">{{ spec.title }}</h3>
      <h2 v-else>{{ spec.title }}</h2>
    </header>
    <div v-for="field in spec.fields" :key="field.key" class="field">
      <label v-if="field.type === 'bool'" class="check">
        <input
          type="checkbox"
          :checked="!!modelValue[field.key]"
          @change="change(modelValue, field, $event)"
        />
        {{ field.label }}
      </label>
      <template v-else>
        <label>{{ field.label }}</label>
        <select
          v-if="field.type === 'select'"
          :value="modelValue[field.key]"
          @change="change(modelValue, field, $event)"
        >
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <input
          v-else-if="field.type === 'yuan' || field.type === 'seconds'"
          type="number"
          :min="field.min ?? 0"
          :step="field.step ?? 1"
          :value="displayValue(field, modelValue[field.key])"
          @change="change(modelValue, field, $event)"
        />
        <input
          v-else-if="field.type === 'int'"
          type="number"
          :min="field.min ?? 0"
          :value="modelValue[field.key]"
          :placeholder="field.placeholder || ''"
          @change="change(modelValue, field, $event)"
        />
        <input
          v-else
          type="text"
          :value="modelValue[field.key]"
          @change="change(modelValue, field, $event)"
        />
      </template>
      <p v-if="field.hint" class="hint">{{ field.hint }}</p>
    </div>
  </component>
</template>
