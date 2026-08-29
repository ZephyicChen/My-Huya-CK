<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import FeaturePanel from "./components/FeaturePanel.vue";
import {
  getConfig,
  getFeatures,
  getRunStatus,
  postRun,
  putFeatureConfig,
  putPlatform,
} from "./api.js";

const room = ref("");
const showBrowser = ref(false);
const features = ref([]);
const featureConfig = reactive({});
const status = ref({ running: false, logged_in: null, message: "" });
const notice = ref("");
const error = ref("");
const busy = ref("");

const featureSections = computed(() => {
  const sections = [];
  const grouped = new Map();
  for (const spec of features.value) {
    const group = spec.ui_group;
    if (!group) {
      sections.push({ id: spec.id, title: "", specs: [spec] });
      continue;
    }
    let section = grouped.get(group.id);
    if (!section) {
      section = { id: group.id, title: group.title, specs: [] };
      grouped.set(group.id, section);
      sections.push(section);
    }
    section.specs.push(spec);
  }
  return sections;
});

onMounted(async () => {
  try {
    const [catalog, config, run] = await Promise.all([getFeatures(), getConfig(), getRunStatus()]);
    features.value = catalog.features;
    room.value = config.platform.room || "";
    showBrowser.value = !!config.platform.show_browser;
    for (const spec of catalog.features) {
      featureConfig[spec.id] = { ...(config.features[spec.id] || {}) };
    }
    status.value = run;
  } catch (err) {
    error.value = String(err.message || err);
  }
});

async function saveSettings() {
  error.value = "";
  notice.value = "";
  await putPlatform({ room: room.value, show_browser: showBrowser.value });
  for (const spec of features.value) {
    await putFeatureConfig(spec.id, featureConfig[spec.id]);
  }
}

async function onSave() {
  busy.value = "save";
  try {
    await saveSettings();
    notice.value = "设置已保存";
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}

async function onAction(name) {
  busy.value = name;
  error.value = "";
  notice.value = "";
  try {
    if (name === "start" || name === "stop") {
      await saveSettings();
    }
    const result = await postRun(name);
    status.value = result.status || status.value;
    if (result.ok) {
      notice.value = result.message || "";
    } else {
      error.value = result.message || "操作未完成";
    }
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <main>
    <header class="top">
      <div>
        <h1>虎牙场控</h1>
        <p class="sub">{{ status.message || "本页只是控制台。关掉启动场控的那个命令行窗口才会完全退出。" }}</p>
      </div>
      <span class="badge" :class="{ on: status.running }">
        {{ status.running ? "运行中" : "未启动" }}
      </span>
    </header>

    <p v-if="notice" class="ok">{{ notice }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <section class="panel run">
      <header><h2>直播间</h2></header>
      <div class="field">
        <label>房间</label>
        <input v-model="room" type="text" placeholder="房间号，例如 123456" />
      </div>
      <label class="check">
        <input v-model="showBrowser" type="checkbox" />
        显示直播间窗口（调试用，正式运行请关闭）
      </label>
      <div class="actions">
        <button type="button" :disabled="!!busy" @click="onAction('login')">
          {{ busy === "login" ? "打开中…" : "打开浏览器登录" }}
        </button>
        <button type="button" class="primary" :disabled="!!busy" @click="onAction('start')">
          {{ busy === "start" ? "启动中…" : "启动场控" }}
        </button>
        <button type="button" :disabled="!!busy || !status.running" @click="onAction('stop')">
          停止
        </button>
        <button type="button" :disabled="!!busy" @click="onSave">
          {{ busy === "save" ? "保存中…" : "保存设置" }}
        </button>
      </div>
    </section>

    <div class="feature-grid">
      <template v-for="section in featureSections" :key="section.id">
        <section v-if="section.title" class="panel feature-group">
          <header><h2>{{ section.title }}</h2></header>
          <div class="feature-group-items">
            <FeaturePanel
              v-for="spec in section.specs"
              :key="spec.id"
              :spec="spec"
              :model-value="featureConfig[spec.id]"
              embedded
              @update:model-value="featureConfig[spec.id] = $event"
            />
          </div>
        </section>
        <FeaturePanel
          v-else-if="featureConfig[section.specs[0].id]"
          :spec="section.specs[0]"
          v-model="featureConfig[section.specs[0].id]"
          :class="{ 'feature-wide': section.id === 'danmaku' }"
        />
      </template>
    </div>
  </main>
</template>
