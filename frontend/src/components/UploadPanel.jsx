import { useState } from "react";
import ConditionBadge from "./ConditionBadge.jsx";
import { predict } from "../api.js";

export default function UploadPanel({ onPredicted }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function handleFileChange(e) {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setPreviewUrl(URL.createObjectURL(selected));
    setResult(null);
    setError(null);
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const data = await predict(file);
      setResult(data);
      onPredicted?.();
    } catch (err) {
      setError(
        err.response?.data?.detail || "Prediction failed — is the backend running?"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2>Upload a track frame</h2>
      <input type="file" accept="image/*" onChange={handleFileChange} />
      <button onClick={handleUpload} disabled={!file || loading} style={{ marginLeft: 12 }}>
        {loading ? "Analyzing…" : "Analyze"}
      </button>

      {previewUrl && <img className="preview-img" src={previewUrl} alt="preview" />}

      {result && (
        <div style={{ marginTop: 12 }}>
          <ConditionBadge label={result.label} confidence={result.confidence} />
        </div>
      )}

      {error && <p style={{ color: "#ff8080" }}>{error}</p>}
    </div>
  );
}
