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
