import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function predict(file) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await axios.post(`${API_URL}/predict`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getTrend(windowMinutes = 15) {
  const { data } = await axios.get(`${API_URL}/trend`, {
    params: { window_minutes: windowMinutes },
  });
  return data;
}

export async function getSuggestion(windowMinutes = 15) {
  const { data } = await axios.get(`${API_URL}/suggestion`, {
    params: { window_minutes: windowMinutes },
  });
  return data;
}
