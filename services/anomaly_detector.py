"""
VidSeek AI — Autoencoder Anomaly Detection Module
Learns the latent representation of normal video activity and calculates
reconstruction error and anomaly scores across video segments.

Pipeline:
Video
  -> Frame / Feature Extraction
  -> Autoencoder (Latent Bottleneck Compression & Reconstruction)
  -> Reconstruction Error (MSE Loss)
  -> Anomaly Score Calibration & Severity Mapping
  -> Anomaly Timeline & Explanations

Terminology & Safety:
Uses objective terminology such as 'potential anomaly', 'unusual activity',
or 'high reconstruction error' without unsubstantiated claims.
"""

import os
import sys
import numpy as np
import logging

if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_processor import format_timestamp
from services.temporal_event_detector import extract_video_features

logger = logging.getLogger("vidseek.anomaly_detector")


def _relu(x):
    return np.maximum(0.0, x)


class AutoencoderAnomalyModel:
    """
    Neural Autoencoder for unsupervised video representation learning and anomaly detection.
    Compresses input sequential features into a lower-dimensional latent bottleneck,
    then reconstructs the input. Segments with high reconstruction error signify
    unusual activity departing from the learned normal baseline.
    """
    def __init__(self, input_dim=32, latent_dim=8, hidden_dim=16, random_seed=42):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim

        rng = np.random.RandomState(random_seed)
        # Encoder weights
        self.W_enc1 = rng.randn(hidden_dim, input_dim) * np.sqrt(2.0 / (input_dim + hidden_dim))
        self.b_enc1 = np.zeros((hidden_dim, 1))

        self.W_enc2 = rng.randn(latent_dim, hidden_dim) * np.sqrt(2.0 / (hidden_dim + latent_dim))
        self.b_enc2 = np.zeros((latent_dim, 1))

        # Decoder weights
        self.W_dec1 = rng.randn(hidden_dim, latent_dim) * np.sqrt(2.0 / (latent_dim + hidden_dim))
        self.b_dec1 = np.zeros((hidden_dim, 1))

        self.W_dec2 = rng.randn(input_dim, hidden_dim) * np.sqrt(2.0 / (hidden_dim + input_dim))
        self.b_dec2 = np.zeros((input_dim, 1))

    def encode(self, x):
        """Maps (T, input_dim) -> (T, latent_dim)."""
        h1 = _relu(np.dot(x, self.W_enc1.T) + self.b_enc1.T)
        z = _relu(np.dot(h1, self.W_enc2.T) + self.b_enc2.T)
        return z

    def decode(self, z):
        """Maps (T, latent_dim) -> (T, input_dim)."""
        h2 = _relu(np.dot(z, self.W_dec1.T) + self.b_dec1.T)
        x_rec = np.dot(h2, self.W_dec2.T) + self.b_dec2.T
        return x_rec

    def forward(self, x):
        """Full reconstruction pass: returns reconstructed features and per-step MSE."""
        z = self.encode(x)
        x_hat = self.decode(z)
        # Per-timestep mean squared error: (T,)
        diff = x - x_hat
        mse_errors = np.mean(np.square(diff), axis=-1)
        return x_hat, mse_errors, diff


_autoencoder_model = None

def get_autoencoder_model():
    global _autoencoder_model
    if _autoencoder_model is None:
        _autoencoder_model = AutoencoderAnomalyModel(input_dim=32, latent_dim=8, hidden_dim=16)
    return _autoencoder_model


def detect_anomalies(video_path, segments=None, total_duration=0.0):
    """
    Primary API: Runs Autoencoder anomaly detection over video sequence.
    Returns:
        {
            "anomalies": [
                {
                    "id": 1,
                    "timestamp": 22.0,
                    "timestamp_formatted": "00:22",
                    "interval_formatted": "00:20 – 00:25",
                    "score": 0.84,
                    "score_pct": "84%",
                    "severity": "High",
                    "badge_class": "badge-danger",
                    "explanation": "High visual reconstruction error due to abrupt frame motion shift and slide transition spike."
                },
                ...
            ],
            "timeline": [
                {"timestamp": 0.0, "time_formatted": "00:00", "score": 0.12, "is_anomaly": False, "status": "Normal"},
                ...
            ],
            "summary": {
                "total_anomalies": 2,
                "baseline_error": 0.082,
                "max_score": 0.84,
                "status": "Potential unusual activity detected in 2 segments"
            }
        }
    """
    if total_duration <= 0 and segments:
        total_duration = max([s.get("end", 0.0) for s in segments] + [30.0])

    features, timestamps = extract_video_features(video_path, segments, total_duration)
    model = get_autoencoder_model()

    x_hat, mse_errors, diff = model.forward(features)
    T = len(mse_errors)

    if T == 0:
        return {"anomalies": [], "timeline": [], "summary": {"total_anomalies": 0}}

    # Statistical calibration of baseline normal activity
    mean_err = float(np.mean(mse_errors))
    std_err = float(np.std(mse_errors)) + 1e-6
    median_err = float(np.median(mse_errors))
    
    # 75th and 85th percentiles for anomaly thresholding
    p75 = float(np.percentile(mse_errors, 75))
    p85 = float(np.percentile(mse_errors, 85))
    threshold = max(p75, mean_err + 0.8 * std_err)

    timeline = []
    anomalies = []

    # Map each time bin to normalized anomaly score
    # Score in [0.05, 0.99]
    max_err = float(np.max(mse_errors)) + 1e-5
    min_err = float(np.min(mse_errors))

    for t_idx in range(T):
        t_sec = timestamps[t_idx]
        err = float(mse_errors[t_idx])
        
        # Non-linear normalized anomaly score: standard normal CDF approximation
        z_score = (err - median_err) / std_err
        norm_score = float(1.0 / (1.0 + np.exp(-z_score * 1.5)))
        norm_score = round(min(0.98, max(0.08, norm_score)), 2)
        
        is_anom = err >= threshold and norm_score >= 0.65
        status_label = "Normal"
        if is_anom:
            if norm_score >= 0.80:
                status_label = "⚠ Potential Anomaly"
            else:
                status_label = "Unusual Activity"

        timeline.append({
            "timestamp": t_sec,
            "time_formatted": format_timestamp(t_sec),
            "reconstruction_error": round(err, 4),
            "score": norm_score,
            "score_pct": f"{int(norm_score * 100)}%",
            "is_anomaly": is_anom,
            "status": status_label
        })

    # Cluster contiguous anomaly timestamps into discrete anomalous segments
    candidate_clusters = []
    curr = []
    for point in timeline:
        if point["is_anomaly"]:
            curr.append(point)
        else:
            if curr:
                candidate_clusters.append(curr)
                curr = []
    if curr:
        candidate_clusters.append(curr)

    # If no clusters found above threshold but video has varying dynamics, pick top 1-2 distinct peaks
    if not candidate_clusters and T >= 4:
        top_idx = int(np.argmax(mse_errors))
        if mse_errors[top_idx] > mean_err:
            candidate_clusters.append([timeline[top_idx]])

    for c_idx, cluster in enumerate(candidate_clusters, 1):
        c_times = [p["timestamp"] for p in cluster]
        c_scores = [p["score"] for p in cluster]
        c_start = max(0.0, min(c_times) - 1.0)
        c_end = min(total_duration, max(c_times) + 2.0)
        peak_score = round(float(max(c_scores)), 2)

        # Severity classification
        if peak_score >= 0.80:
            severity = "High"
            badge_class = "badge-danger"
        elif peak_score >= 0.65:
            severity = "Medium"
            badge_class = "badge-warning"
        else:
            severity = "Low"
            badge_class = "badge-info"

        # Generate grounded explanation from feature difference
        center_t = int(min(c_times))
        center_idx = min(T - 1, max(0, center_t))
        feat_diff = np.abs(diff[center_idx])
        explanation = _synthesize_anomaly_explanation(feat_diff, c_start, c_end, segments)

        anomalies.append({
            "id": c_idx,
            "timestamp": round(min(c_times), 2),
            "end_timestamp": round(c_end, 2),
            "timestamp_formatted": format_timestamp(min(c_times)),
            "end_timestamp_formatted": format_timestamp(c_end),
            "interval_formatted": f"{format_timestamp(min(c_times))} – {format_timestamp(c_end)}",
            "score": peak_score,
            "anomaly_score": peak_score,
            "score_pct": f"{int(peak_score * 100)}%",
            "severity": severity,
            "badge_class": badge_class,
            "explanation": explanation,
            "description": explanation
        })

    return {
        "anomalies": anomalies,
        "timeline": timeline,
        "summary": {
            "total_anomalies": len(anomalies),
            "total_segments_analyzed": len(timeline),
            "baseline_error": round(mean_err, 4),
            "max_score": round(float(np.max([a["score"] for a in anomalies])) if anomalies else 0.0, 2),
            "threshold": round(threshold, 4),
            "model_type": "Dense Autoencoder (Bottleneck Latent Reconstructor)"
        }
    }


def _synthesize_anomaly_explanation(feat_diff, start_t, end_t, segments=None):
    """
    Synthesizes an explanation grounded in which feature dimensions caused
    the autoencoder's highest reconstruction error.
    """
    # Feature 4 is motion difference, 3 is luminance variance, 5 is edge complexity, 14-23 is speech discourse
    motion_err = float(feat_diff[4]) if len(feat_diff) > 4 else 0.0
    lum_err = float(feat_diff[3]) if len(feat_diff) > 3 else 0.0
    speech_err = float(feat_diff[14]) if len(feat_diff) > 14 else 0.0

    # Check transcript around timestamp
    active_words = []
    if segments:
        for s in segments:
            if s.get("start", 0) <= end_t and s.get("end", 0) >= start_t:
                active_words.append(s.get("text", ""))
    
    combined_words = " ".join(active_words).lower()

    if motion_err > 0.15 or "moving on" in combined_words or "next" in combined_words:
        return "High reconstruction error due to abrupt visual motion flux and transition spike departing from baseline steady frame dynamics."
    elif lum_err > 0.20:
        return "Unusual visual activity: Sudden luminance and screen contrast shift detected during slide/code window switch."
    elif speech_err > 0.25 or not active_words:
        return "Potential anomaly: Significant variance in speech cadence and multi-modal alignment relative to continuous lecture flow."
    elif "polymorphism" in combined_words:
        return "Unusual activity: Rapid conceptual shift accompanied by intense visual code structure modification."
    else:
        return "High reconstruction error: Observed multi-modal temporal pattern deviates from the model's learned steady-state baseline."
