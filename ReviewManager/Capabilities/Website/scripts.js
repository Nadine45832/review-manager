const SERVER = window.location.origin;
let audioPlaying = false;

window.addEventListener("load", () => {
  checkServer();
  bindDragAndDrop();
});

async function checkServer() {
  try {
    const response = await fetch(`${SERVER}/`);
    setStatus(response.ok);
  } catch (error) {
    setStatus(false);
  }
}

function setStatus(isOnline) {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  if (!dot || !text) return;

  dot.className = `dot ${isOnline ? "online" : "offline"}`;
  text.textContent = isOnline ? "Online" : "Offline";
}

function onFileSelected(input) {
  const chosen = document.getElementById("file-chosen");
  if (!chosen) return;

  chosen.innerHTML = input.files.length
    ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34C759" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> ${escapeHtml(input.files[0].name)}`
    : "";
}

function bindDragAndDrop() {
  const zone = document.getElementById("drop-zone");
  const input = document.getElementById("csv-file");
  if (!zone || !input) return;

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragover");
  });

  zone.addEventListener("dragleave", () => {
    zone.classList.remove("dragover");
  });

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragover");

    if (event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      onFileSelected(input);
    }
  });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function setStep(stepNumber, state) {
  const element = document.getElementById(`step-${stepNumber}`);
  if (element) {
    element.className = `sp ${state}`.trim();
  }
}

function resetSteps() {
  [1, 2, 3, 4].forEach((stepNumber) => setStep(stepNumber, ""));
}

function setLoading(isLoading) {
  const button = document.getElementById("run-btn");
  const spinner = document.getElementById("spinner");
  const label = document.getElementById("btn-label");
  if (!button || !spinner || !label) return;

  button.disabled = isLoading;
  spinner.style.display = isLoading ? "inline-block" : "none";
  label.textContent = isLoading ? "Processing…" : "Analyze Reviews";
}

function showError(message) {
  const box = document.getElementById("err-box");
  if (!box) return;
  box.textContent = message;
  box.style.display = "block";
}

function clearError() {
  const box = document.getElementById("err-box");
  if (!box) return;
  box.textContent = "";
  box.style.display = "none";
}

async function api(path, body) {
  const response = await fetch(`${SERVER}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let message = "Request failed";
    try {
      const errorPayload = await response.json();
      message = errorPayload.error || message;
    } catch (error) {
      // Keep default error message.
    }
    throw new Error(message);
  }

  return response.json();
}

async function runPipeline() {
  clearError();
  resetSteps();

  const results = document.getElementById("results");
  if (results) {
    results.style.display = "none";
  }

  const fileInput = document.getElementById("csv-file");
  const targetLang = document.getElementById("target-lang")?.value || "en";
  const audioLang = document.getElementById("audio-lang")?.value || "en";

  if (!fileInput || !fileInput.files.length) {
    showError("Please select a CSV file first.");
    return;
  }

  setLoading(true);

  try {
    const file = fileInput.files[0];

    setStep(1, "active");
    const filebytes = await fileToBase64(file);
    const uploadResult = await api("/reviews/upload", {
      filename: file.name,
      filebytes,
      target_lang: targetLang,
    });
    setStep(1, "done");
    setStep(2, "done");

    setStep(3, "active");
    const analysisResult = await api(`/reviews/${encodeURIComponent(uploadResult.batch_id)}/analyze`, {});
    setStep(3, "done");

    let audioUrl = null;
    setStep(4, "active");
    try {
      const audioResult = await api(`/reviews/${encodeURIComponent(uploadResult.batch_id)}/audio-summary`, {
        language_code: audioLang,
      });
      audioUrl = audioResult.audio_url || null;
    } catch (error) {
      console.warn("Audio summary failed:", error);
    }
    setStep(4, "done");

    renderResults(analysisResult, uploadResult.translated_reviews || [], audioUrl);
  } catch (error) {
    resetSteps();
    showError(`Error: ${error.message}`);
  } finally {
    setLoading(false);
  }
}

function renderResults(data, translatedReviews, audioUrl) {
  const summary = data.summary || {};
  const results = data.results || [];
  const keyPhrases = data.key_phrases || [];
  const total = Math.max(summary.total || 0, 1);
  const toPercent = (value) => Math.round(((value || 0) / total) * 100);

  setText("r-total", String(summary.total || 0));
  setText("r-pos", String(summary.positive || 0));
  setText("r-neg", String(summary.negative || 0));

  const positivePercent = toPercent(summary.positive);
  const negativePercent = toPercent(summary.negative);
  const neutralPercent = toPercent(summary.neutral);
  const mixedPercent = toPercent(summary.mixed);

  setWidth("bp", positivePercent);
  setWidth("bn", negativePercent);
  setWidth("bnu", neutralPercent);
  setWidth("bm", mixedPercent);

  setText("leg-pos", `Positive ${positivePercent}%`);
  setText("leg-neg", `Negative ${negativePercent}%`);
  setText("leg-neu", `Neutral ${neutralPercent}%`);
  setText("leg-mix", `Mixed ${mixedPercent}%`);

  const translatedCount = translatedReviews.filter((item) => item.was_translated).length;
  setText("r-trans-note", translatedCount > 0 ? `${translatedCount} translated` : "");

  const keyPhraseCard = document.getElementById("kp-card");
  const keyPhraseContainer = document.getElementById("kp-chips");
  if (keyPhraseCard && keyPhraseContainer) {
    if (keyPhrases.length) {
      keyPhraseContainer.innerHTML = keyPhrases
        .slice(0, 20)
        .map((phrase) => `<span class="kp-chip">${escapeHtml(phrase)}</span>`)
        .join("");
      keyPhraseCard.style.display = "block";
    } else {
      keyPhraseContainer.innerHTML = "";
      keyPhraseCard.style.display = "none";
    }
  }

  const audioCard = document.getElementById("audio-card");
  const audioPlayer = document.getElementById("audio-player");
  if (audioCard && audioPlayer) {
    if (audioUrl) {
      audioPlayer.src = audioUrl;
      audioCard.style.display = "block";
      setText("audio-detail", "Tap to play the spoken analysis");
    } else {
      audioPlayer.removeAttribute("src");
      audioCard.style.display = "none";
    }
  }

  const reviewList = document.getElementById("review-list");
  if (reviewList) {
    reviewList.innerHTML = results
      .map((result, index) => {
        const translation = translatedReviews[index] || {};
        const original = translation.original || result.text || "";
        const translated = translation.translated || result.text || "";
        const sourceLanguage = translation.source_language || "";
        const showTranslation = translation.was_translated && translated;

        return `
          <div class="review-item">
            <div class="ri-top">
              <span class="ri-idx">#${index + 1}</span>
              <span class="sbadge s-${escapeHtml(result.sentiment || "NEUTRAL")}">${escapeHtml(result.sentiment || "NEUTRAL")}</span>
            </div>
            <div class="ri-original">${escapeHtml(original)}</div>
            ${showTranslation ? `<div class="ri-translated">${escapeHtml(translated)}</div>` : ""}
            ${sourceLanguage ? `<div class="ri-lang">${escapeHtml(sourceLanguage.toUpperCase())}</div>` : ""}
          </div>`;
      })
      .join("");
  }

  const resultsBlock = document.getElementById("results");
  if (resultsBlock) {
    resultsBlock.style.display = "block";
    resultsBlock.scrollIntoView({ behavior: "smooth" });
  }
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setWidth(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.style.width = `${value}%`;
  }
}

function toggleAudio() {
  const audio = document.getElementById("audio-player");
  if (!audio) return;

  if (audioPlaying) {
    audio.pause();
    audioPlaying = false;
    setPlayIcon(false);
  } else {
    audio.play();
    audioPlaying = true;
    setPlayIcon(true);
  }
}

function onAudioEnded() {
  audioPlaying = false;
  setPlayIcon(false);
}

function setPlayIcon(isPlaying) {
  const icon = document.getElementById("play-icon");
  if (!icon) return;

  icon.outerHTML = isPlaying
    ? '<svg id="play-icon" viewBox="0 0 24 24" fill="#fff"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>'
    : '<svg id="play-icon" viewBox="0 0 24 24" fill="#fff"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}