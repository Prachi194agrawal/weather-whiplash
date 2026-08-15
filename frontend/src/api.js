const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function asJson(res) {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? " — " + body : ""}`);
  }
  return res.json();
}

export async function predict(file, session = "default") {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/predict?session=${encodeURIComponent(session)}`, {
    method: "POST",
    body: form,
  });
  return asJson(res);
}

export async function getTrend(session = "default", windowS = 900) {
  const params = new URLSearchParams({ session, window_s: windowS });
  const res = await fetch(`${API_URL}/trend?${params}`);
  return asJson(res);
}

export async function getHealth() {
  const res = await fetch(`${API_URL}/health`);
  return asJson(res);
}
