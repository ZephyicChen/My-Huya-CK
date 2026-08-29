async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail ? JSON.stringify(data.detail) : response.statusText;
    throw new Error(detail);
  }
  return data;
}

export function getFeatures() {
  return request("/api/features");
}

export function getConfig() {
  return request("/api/config");
}

export function putPlatform(platform) {
  return request("/api/config", { method: "PUT", body: JSON.stringify({ platform }) });
}

export function putFeatureConfig(id, config) {
  return request(`/api/features/${id}/config`, {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}

export function getRunStatus() {
  return request("/api/run/status");
}

export function postRun(action) {
  return request(`/api/run/${action}`, { method: "POST", body: JSON.stringify({}) });
}

export function getChatControl() {
  return request("/api/chat/control");
}

export function putChatControl(config) {
  return request("/api/chat/control", {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}

export function getChatState() {
  return request("/api/chat/state");
}

export function getInteraction() {
  return request("/api/interaction");
}

export function putInteraction(interaction) {
  return request("/api/interaction", { method: "PUT", body: JSON.stringify({ interaction }) });
}

export function getNovels() {
  return request("/api/novels");
}

export async function uploadNovel(name, file) {
  // 正文按原始字节上传，显示名走查询参数；避免引入 multipart 依赖。
  const response = await fetch(`/api/novels?name=${encodeURIComponent(name)}`, {
    method: "POST",
    body: await file.arrayBuffer(),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail ? String(data.detail) : response.statusText);
  }
  return data;
}

export function previewNovel(id) {
  return request(`/api/novels/${id}/preview`);
}

export function deleteNovel(id) {
  return request(`/api/novels/${id}`, { method: "DELETE" });
}

export function getNovelSettings() {
  return request("/api/novels/settings");
}

export function putNovelSettings(config) {
  return request("/api/novels/settings", { method: "PUT", body: JSON.stringify({ config }) });
}

export function playerAction(action) {
  return request(`/api/novels/player/${action}`, { method: "POST", body: JSON.stringify({}) });
}
