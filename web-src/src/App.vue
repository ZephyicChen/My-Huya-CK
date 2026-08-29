<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import FeaturePanel from "./components/FeaturePanel.vue";
import {
  deleteNovel,
  getChatControl,
  getChatState,
  getConfig,
  getFeatures,
  getInteraction,
  getNovels,
  getNovelSettings,
  getRunStatus,
  playerAction,
  postRun,
  previewNovel,
  putChatControl,
  putFeatureConfig,
  putInteraction,
  putNovelSettings,
  putPlatform,
  uploadNovel,
} from "./api.js";

const tabs = [
  { id: "overview", label: "总览" },
  { id: "automatic", label: "自动场控" },
  { id: "remote", label: "远程控制" },
  { id: "interaction", label: "趣味互动" },
  { id: "records", label: "运行记录" },
];
const controlModules = [
  { id: "danmaku", label: "弹幕发送" },
  { id: "welcome", label: "进场欢迎" },
  { id: "gift_thank", label: "礼物感谢" },
  { id: "guard_thank", label: "守护感谢" },
  { id: "superfan_thank", label: "超粉感谢" },
  { id: "noble_thank", label: "贵族感谢" },
];

const activeTab = ref("overview");
const room = ref("");
const showBrowser = ref(false);
const features = ref([]);
const featureConfig = reactive({});
const status = ref({ running: false, logged_in: null, message: "" });
const chatControl = reactive({ owner_uid: "", owner_nick: "", whitelist: [] });
const chatState = ref({ attached: false, recent_speakers: [], records: [], authorized_count: 0, ignored_count: 0 });
const interactionEnabled = ref(false);
const novels = ref([]);
const novelConfig = reactive({ enabled: false, novel_id: "", max_chars: 28, interval_ms: 10000, loop: true });
const playerState = ref({ config: {}, total_segments: 0, current_index: 0, next_preview: "", last_error: "" });
const novelPreview = ref("");
const novelFile = ref(null);
const novelStateLabels = { idle: "待机", playing: "播放中", paused: "已暂停", completed: "已播完", error: "异常" };
const notice = ref("");
const error = ref("");
const busy = ref("");
let pollTimer = 0;
let lastCommandSeq = 0;

const specById = computed(() => Object.fromEntries(features.value.map((spec) => [spec.id, spec])));
const automaticSections = computed(() => {
  const sections = [];
  const grouped = new Map();
  for (const spec of features.value.filter((item) => item.id !== "danmaku")) {
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

function loadChatConfig(config) {
  chatControl.owner_uid = String(config?.owner_uid || "");
  chatControl.owner_nick = String(config?.owner_nick || "");
  chatControl.whitelist = (config?.whitelist || []).map((item) => ({
    uid: String(item.uid || ""),
    nick: String(item.nick || ""),
    enabled: item.enabled !== false,
    allowed_modules: [...(item.allowed_modules || [])],
    allowed_interactions: [...(item.allowed_interactions || [])],
  }));
}

function toggleInteractionPermission(item, interactionId, checked) {
  const list = new Set(item.allowed_interactions || []);
  if (checked) list.add(interactionId);
  else list.delete(interactionId);
  item.allowed_interactions = [...list];
}

async function refreshPlayer() {
  const data = await getInteraction();
  interactionEnabled.value = !!data.interaction?.enabled;
  const player = data.player || {};
  playerState.value = player;
  if (player.config) {
    Object.assign(novelConfig, player.config);
  }
}

async function refreshNovels() {
  const data = await getNovels();
  novels.value = data.novels || [];
  const current = novels.value.find((item) => item.id === novelConfig.novel_id);
  if (current && !novelPreview.value) {
    try {
      const preview = await previewNovel(current.id);
      novelPreview.value = preview.head || "";
    } catch (_) {
      novelPreview.value = "";
    }
  }
}

async function onInteractionToggle(event) {
  try {
    const data = await putInteraction({ enabled: event.target.checked });
    interactionEnabled.value = !!data.interaction?.enabled;
    playerState.value = data.player || playerState.value;
    notice.value = data.interaction?.enabled ? "趣味互动已开启" : "趣味互动已关闭，所有互动模块停止产生新弹幕";
  } catch (err) {
    error.value = String(err.message || err);
  }
}

async function onNovelFilePicked(event) {
  novelFile.value = event.target.files?.[0] || null;
}

async function onUploadNovel() {
  const file = novelFile.value;
  if (!file) {
    error.value = "请先选择 .txt 文件";
    return;
  }
  busy.value = "upload";
  error.value = "";
  notice.value = "";
  try {
    const data = await uploadNovel(file.name.replace(/\.txt$/i, ""), file);
    notice.value = `《${data.novel?.name}》已导入`;
    novelFile.value = null;
    await refreshNovels();
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}

async function onSelectNovel(novel) {
  try {
    const data = await putNovelSettings({ novel_id: novel.id });
    Object.assign(novelConfig, data.config);
    playerState.value = data.player || playerState.value;
    novelPreview.value = "";
    const preview = await previewNovel(novel.id);
    novelPreview.value = preview.head || "";
  } catch (err) {
    error.value = String(err.message || err);
  }
}

async function onDeleteNovel(novel) {
  if (!window.confirm(`删除《${novel.name}》？正文和进度将一并删除，不可恢复。`)) return;
  try {
    await deleteNovel(novel.id);
    if (novelConfig.novel_id === novel.id) {
      novelPreview.value = "";
    }
    await refreshNovels();
    notice.value = "已删除";
  } catch (err) {
    error.value = String(err.message || err);
  }
}

async function onSaveNovelSettings() {
  busy.value = "novel-save";
  error.value = "";
  notice.value = "";
  try {
    const data = await putNovelSettings({
      enabled: novelConfig.enabled,
      max_chars: Number(novelConfig.max_chars),
      interval_ms: Number(novelConfig.interval_ms),
      loop: !!novelConfig.loop,
    });
    Object.assign(novelConfig, data.config);
    playerState.value = data.player || playerState.value;
    notice.value = "轮播设置已保存";
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}

async function onPlayerAction(action) {
  busy.value = `player-${action}`;
  error.value = "";
  notice.value = "";
  try {
    const data = await playerAction(action);
    playerState.value = data.player || playerState.value;
    if (playerState.value.config) Object.assign(novelConfig, playerState.value.config);
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}

async function refreshLiveStatus() {
  try {
    const [run, chat, interaction] = await Promise.all([getRunStatus(), getChatState(), getInteraction()]);
    status.value = run;
    const nextChat = chat.state || chat;
    chatState.value = nextChat;
    interactionEnabled.value = !!interaction.interaction?.enabled;
    const player = interaction.player || {};
    playerState.value = player;
    if (player.config && !busy.value) {
      Object.assign(novelConfig, player.config);
    }
    if ((nextChat.command_seq || 0) > lastCommandSeq) {
      lastCommandSeq = nextChat.command_seq || 0;
      const config = await getConfig();
      for (const spec of features.value) {
        if (featureConfig[spec.id] && config.features[spec.id]) {
          featureConfig[spec.id].enabled = !!config.features[spec.id].enabled;
        }
      }
      const command = nextChat.last_command;
      if (command) {
        notice.value = command.ok
          ? `LU 指令已执行：${command.action}${command.target}`
          : `LU 指令未执行：没有${command.target}权限`;
      }
    }
  } catch (_) {
    // 页面初始错误会显示；轮询失败不反复刷提示。
  }
}

onMounted(async () => {
  try {
    const [catalog, config, run, control, interaction, novelList] = await Promise.all([
      getFeatures(),
      getConfig(),
      getRunStatus(),
      getChatControl(),
      getInteraction(),
      getNovels(),
    ]);
    features.value = catalog.features;
    room.value = config.platform.room || "";
    showBrowser.value = !!config.platform.show_browser;
    for (const spec of catalog.features) {
      featureConfig[spec.id] = { ...(config.features[spec.id] || {}) };
    }
    status.value = run;
    loadChatConfig(control.config || {});
    chatState.value = control.state || chatState.value;
    lastCommandSeq = chatState.value.command_seq || 0;
    interactionEnabled.value = !!interaction.interaction?.enabled;
    playerState.value = interaction.player || playerState.value;
    if (interaction.player?.config) {
      Object.assign(novelConfig, interaction.player.config);
    }
    novels.value = novelList.novels || [];
    const current = novels.value.find((item) => item.id === novelConfig.novel_id);
    if (current) {
      try {
        const preview = await previewNovel(current.id);
        novelPreview.value = preview.head || "";
      } catch (_) {
        novelPreview.value = "";
      }
    }
    pollTimer = window.setInterval(refreshLiveStatus, 3000);
  } catch (err) {
    error.value = String(err.message || err);
  }
});

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});

async function saveSettings() {
  error.value = "";
  notice.value = "";
  await putPlatform({ room: room.value, show_browser: showBrowser.value });
  for (const spec of features.value) {
    await putFeatureConfig(spec.id, featureConfig[spec.id]);
  }
  const result = await putChatControl(chatControl);
  loadChatConfig(result.config || chatControl);
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
    if (name === "start" || name === "stop") await saveSettings();
    const result = await postRun(name);
    status.value = result.status || status.value;
    if (result.ok) notice.value = result.message || "";
    else error.value = result.message || "操作未完成";
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    busy.value = "";
  }
}

function toggleSend(event) {
  if (!featureConfig.danmaku) return;
  featureConfig.danmaku = { ...featureConfig.danmaku, enabled: event.target.checked };
}

function setOwner(speaker) {
  chatControl.owner_uid = String(speaker.uid || "");
  chatControl.owner_nick = String(speaker.nick || "");
}

function addWhitelist(speaker = {}) {
  const uid = String(speaker.uid || "");
  if (uid && chatControl.whitelist.some((item) => item.uid === uid)) return;
  chatControl.whitelist.push({
    uid,
    nick: String(speaker.nick || ""),
    enabled: true,
    allowed_modules: [],
    allowed_interactions: [],
  });
}

function removeWhitelist(index) {
  chatControl.whitelist.splice(index, 1);
}

function toggleModule(item, moduleId, checked) {
  const modules = new Set(item.allowed_modules || []);
  if (checked) modules.add(moduleId);
  else modules.delete(moduleId);
  item.allowed_modules = [...modules];
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString("zh-CN", { hour12: false });
}
</script>

<template>
  <main>
    <header class="core-bar">
      <div class="brand">
        <h1>My-Huya-CK</h1>
        <span class="room-label">{{ status.room || room || "未设置房间" }}</span>
      </div>
      <div class="core-statuses">
        <span class="status-chip" :class="{ good: status.running }">{{ status.running ? "运行中" : "未启动" }}</span>
        <span class="status-chip" :class="{ good: status.taf_connected }">TAF {{ status.taf_connected ? "正常" : "未连接" }}</span>
        <span class="status-chip" :class="{ good: chatState.attached }">1400 {{ chatState.attached ? "已监听" : "未监听" }}</span>
        <span class="queue-chip">队列 {{ status.queue_size || 0 }}/{{ featureConfig.danmaku?.queue_max || 0 }}</span>
        <label class="master-switch">
          <input type="checkbox" :checked="!!featureConfig.danmaku?.enabled" @change="toggleSend" />
          <span>允许发送</span>
        </label>
      </div>
    </header>

    <nav class="tabs" aria-label="设置分页">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="page-feedback">
      <p v-if="notice" class="ok">{{ notice }}</p>
      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <section v-if="activeTab === 'overview'" class="tab-page">
      <div class="page-heading">
        <div><h2>总览</h2><p>配置直播间、运行方式和统一弹幕输出。</p></div>
        <button type="button" class="save-button" :disabled="!!busy" @click="onSave">{{ busy === "save" ? "保存中…" : "保存全部设置" }}</button>
      </div>
      <div class="overview-grid">
        <section class="panel core-panel">
          <header><h2>直播间与运行</h2></header>
          <p class="hint">{{ status.message || "关掉启动场控的命令行窗口才会完全退出。" }}</p>
          <div class="field"><label>房间</label><input v-model="room" type="text" placeholder="房间号，例如 123456" /></div>
          <label class="check"><input v-model="showBrowser" type="checkbox" />显示直播间窗口（调试用）</label>
          <div class="actions">
            <button type="button" :disabled="!!busy" @click="onAction('login')">{{ busy === "login" ? "打开中…" : "打开浏览器登录" }}</button>
            <button type="button" class="primary" :disabled="!!busy" @click="onAction('start')">{{ busy === "start" ? "启动中…" : "启动场控" }}</button>
            <button type="button" :disabled="!!busy || !status.running" @click="onAction('stop')">停止</button>
          </div>
        </section>
        <section class="panel core-panel">
          <header><h2>弹幕发送核心</h2></header>
          <FeaturePanel
            v-if="specById.danmaku && featureConfig.danmaku"
            :spec="specById.danmaku"
            v-model="featureConfig.danmaku"
            embedded
          />
          <div class="metric-row">
            <div><strong>{{ status.queue_size || 0 }}</strong><span>当前排队</span></div>
            <div><strong>{{ featureConfig.danmaku?.queue_max || 0 }}</strong><span>队列上限</span></div>
            <div><strong>{{ (featureConfig.danmaku?.interval_ms || 0) / 1000 }}s</strong><span>成功后 CD</span></div>
          </div>
        </section>
      </div>
    </section>

    <section v-else-if="activeTab === 'automatic'" class="tab-page">
      <div class="page-heading"><div><h2>自动场控</h2><p>事件触发的欢迎与感谢模块。</p></div><button type="button" class="save-button" :disabled="!!busy" @click="onSave">保存全部设置</button></div>
      <div class="feature-grid">
        <template v-for="section in automaticSections" :key="section.id">
          <section v-if="section.title" class="panel feature-group">
            <header><h2>{{ section.title }}</h2></header>
            <div class="feature-group-items">
              <FeaturePanel v-for="spec in section.specs" :key="spec.id" :spec="spec" :model-value="featureConfig[spec.id]" embedded @update:model-value="featureConfig[spec.id] = $event" />
            </div>
          </section>
          <FeaturePanel v-else-if="featureConfig[section.specs[0].id]" :spec="section.specs[0]" v-model="featureConfig[section.specs[0].id]" />
        </template>
      </div>
    </section>

    <section v-else-if="activeTab === 'remote'" class="tab-page">
      <div class="page-heading"><div><h2>远程控制</h2><p>随场控运行，没有更高一级开关；仅当前账号和授权白名单可以执行。</p></div><span class="status-chip good">随场控运行</span></div>
      <section class="panel command-panel">
        <header><h2>LU 场控指令</h2><span class="hint">LU 不区分大小写，空格可以省略</span></header>
        <div class="command-grid">
          <code>LU 开启 发送</code><code>LU 关闭 发送</code>
          <code>LU 开启 欢迎</code><code>LU 关闭 欢迎</code>
          <code>LU 开启 感谢</code><code>LU 关闭 感谢</code>
          <code>LU 轮播 开始</code><code>LU 轮播 暂停</code>
          <code>LU 轮播 继续</code><code>LU 轮播 停止</code>
          <code>LU 轮播 下一条</code><code>LU 轮播 状态</code>
        </div>
        <p class="hint command-hint">“感谢”同时控制礼物、守护、超粉和贵族感谢。关闭“发送”会立即清空尚未发送的队列，轮播也会暂停。轮播指令需要在白名单里单独勾选“允许控制轮播”。</p>
      </section>
      <div class="remote-grid">
        <section class="panel">
          <header><h2>当前登录账号</h2></header>
          <p class="hint">从其他设备发送一条弹幕后，在右侧最近发言用户中选择该账号。</p>
          <div class="field"><label>账号 UID</label><input v-model="chatControl.owner_uid" type="text" placeholder="尚未设置" /></div>
          <div class="field"><label>备注昵称</label><input v-model="chatControl.owner_nick" type="text" placeholder="用于界面识别" /></div>
          <span class="status-chip" :class="{ good: chatControl.owner_uid }">{{ chatControl.owner_uid ? "已设置" : "待设置" }}</span>
        </section>
        <section class="panel">
          <header><h2>最近发言用户</h2><span class="hint">最多保留 100 人，不保存普通观众正文</span></header>
          <div v-if="!chatState.recent_speakers?.length" class="empty-state">启动场控并等待弹幕后，这里会出现 UID 和昵称。</div>
          <div v-else class="speaker-list">
            <div v-for="speaker in chatState.recent_speakers" :key="speaker.uid" class="speaker-row">
              <div><strong>{{ speaker.nick || "未知昵称" }}</strong><span>UID {{ speaker.uid }} · {{ formatTime(speaker.last_seen) }}</span></div>
              <div class="row-actions"><button type="button" @click="setOwner(speaker)">设为当前账号</button><button type="button" @click="addWhitelist(speaker)">加入白名单</button></div>
            </div>
          </div>
        </section>
      </div>

      <section class="panel">
        <header><h2>白名单与预留权限</h2><button type="button" class="small-button" @click="addWhitelist()">手工添加</button></header>
        <p class="hint">勾选白名单成员可以通过 LU 指令控制的模块；“感谢”只会调整该成员有权限的感谢模块。</p>
        <div v-if="!chatControl.whitelist.length" class="empty-state">白名单为空，普通观众不会触发任何功能。</div>
        <div v-else class="whitelist-list">
          <article v-for="(item, index) in chatControl.whitelist" :key="`${item.uid}-${index}`" class="whitelist-card">
            <div class="whitelist-main">
              <label class="check"><input v-model="item.enabled" type="checkbox" />启用</label>
              <input v-model="item.uid" type="text" placeholder="UID" />
              <input v-model="item.nick" type="text" placeholder="备注昵称" />
              <button type="button" class="danger-link" @click="removeWhitelist(index)">移除</button>
            </div>
            <div class="permission-list">
              <label v-for="module in controlModules" :key="module.id" class="check compact"><input type="checkbox" :checked="item.allowed_modules.includes(module.id)" @change="toggleModule(item, module.id, $event.target.checked)" />{{ module.label }}</label>
              <label class="check compact"><input type="checkbox" :checked="item.allowed_interactions.includes('novel')" @change="toggleInteractionPermission(item, 'novel', $event.target.checked)" />允许控制轮播</label>
            </div>
          </article>
        </div>
        <div class="actions"><button type="button" class="primary" :disabled="!!busy" @click="onSave">保存白名单</button></div>
      </section>
    </section>

    <section v-else-if="activeTab === 'interaction'" class="tab-page">
      <div class="page-heading">
        <div><h2>趣味互动</h2><p>只允许当前登录账号和获得授权的白名单用户触发；文本的上传、删除和选择只能在本页完成。</p></div>
        <span class="status-chip" :class="{ good: interactionEnabled }">{{ interactionEnabled ? "已启用" : "未启用" }}</span>
      </div>

      <section class="panel">
        <header><h2>趣味互动总控</h2></header>
        <label class="check"><input type="checkbox" :checked="interactionEnabled" @change="onInteractionToggle" />启用趣味互动</label>
        <p class="hint">总开关关闭后，所有趣味互动模块不再产生新弹幕；远程控制不受影响。</p>
      </section>

      <section class="panel">
        <header><h2>文本库</h2><span class="hint">UTF-8 文本，最大 5 MiB；小说、话术、台词都可以</span></header>
        <div class="actions novel-upload">
          <input type="file" accept=".txt" @change="onNovelFilePicked" />
          <button type="button" :disabled="!!busy" @click="onUploadNovel">{{ busy === "upload" ? "导入中…" : "上传文本" }}</button>
        </div>
        <div v-if="!novels.length" class="empty-state">还没有导入文本。上传后会显示名称、大小和进度。</div>
        <div v-else class="novel-list">
          <article v-for="novel in novels" :key="novel.id" class="novel-row" :class="{ active: novelConfig.novel_id === novel.id }">
            <label class="check compact">
              <input type="radio" name="current-novel" :checked="novelConfig.novel_id === novel.id" :disabled="!novel.exists" @change="onSelectNovel(novel)" />
              <strong>{{ novel.name }}</strong>
            </label>
            <span>{{ novel.exists ? `${Math.round((novel.size || 0) / 1024)} KB` : "文件丢失" }}</span>
            <button type="button" class="danger-link" :disabled="playerState.config?.state === 'playing' && novelConfig.novel_id === novel.id" @click="onDeleteNovel(novel)">删除</button>
          </article>
        </div>
        <p v-if="novelPreview" class="hint novel-preview">开头预览：{{ novelPreview }}</p>
      </section>

      <section class="panel">
        <header><h2>轮播播放</h2><span class="status-chip" :class="{ good: playerState.config?.state === 'playing' }">{{ novelStateLabels[playerState.config?.state] || "待机" }}</span></header>
        <div class="novel-settings">
          <label class="check"><input v-model="novelConfig.enabled" type="checkbox" />轮播模块开关</label>
          <div class="field"><label>每条最大字数（15～28）</label><input v-model="novelConfig.max_chars" type="number" min="15" max="28" /></div>
          <div class="field"><label>发送间隔（秒，最小 3）</label><input :value="novelConfig.interval_ms / 1000" type="number" min="3" step="1" @input="novelConfig.interval_ms = Math.round($event.target.value * 1000)" /></div>
          <label class="check"><input v-model="novelConfig.loop" type="checkbox" />循环播放（播完回卷，适合话术库轮播）</label>
        </div>
        <div class="actions"><button type="button" class="primary" :disabled="!!busy" @click="onSaveNovelSettings">{{ busy === "novel-save" ? "保存中…" : "保存轮播设置" }}</button></div>
        <div class="metric-row">
          <div><strong>{{ playerState.current_index || 0 }}</strong><span>当前条</span></div>
          <div><strong>{{ playerState.total_segments || 0 }}</strong><span>总条数</span></div>
        </div>
        <p v-if="playerState.next_preview" class="hint novel-preview">下一条预览：{{ playerState.next_preview }}</p>
        <p v-if="playerState.last_error" class="err">{{ playerState.last_error }}</p>
        <div class="actions">
          <button type="button" :disabled="!!busy" @click="onPlayerAction('start')">开始</button>
          <button type="button" :disabled="!!busy || playerState.config?.state !== 'playing'" @click="onPlayerAction('pause')">暂停</button>
          <button type="button" :disabled="!!busy || playerState.config?.state !== 'paused'" @click="onPlayerAction('resume')">继续</button>
          <button type="button" :disabled="!!busy" @click="onPlayerAction('stop')">停止</button>
          <button type="button" :disabled="!!busy" @click="onPlayerAction('next')">下一条</button>
        </div>
        <p class="hint">实际发送间隔取全局发送 CD 与轮播间隔的较大值；轮播为低优先级，欢迎和感谢先发。发送失败不重试，顺序播下一条。重启程序后保留进度但保持暂停。</p>
      </section>
    </section>

    <section v-else class="tab-page">
      <div class="page-heading"><div><h2>运行记录</h2><p>当前阶段显示授权弹幕和识别状态，固定保留最近 200 条。</p></div><span class="hint">授权 {{ chatState.authorized_count || 0 }} · 忽略 {{ chatState.ignored_count || 0 }}</span></div>
      <section class="panel record-panel">
        <div v-if="!chatState.records?.length" class="empty-state">暂无授权弹幕记录。</div>
        <div v-else class="record-list">
          <div v-for="(record, index) in chatState.records" :key="`${record.time}-${index}`" class="record-row">
            <time>{{ formatTime(record.time) }}</time>
            <span class="record-kind">{{ record.role === "owner" ? "当前账号" : "白名单" }}</span>
            <strong>{{ record.nick }}</strong>
            <span>{{ record.content }}</span>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>
