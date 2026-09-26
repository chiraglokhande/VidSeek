// VidSeek AI Frontend Application Logic

let currentJobId = null;
let currentJobData = null;
let pollInterval = null;

// DOM Elements
const uploadSection = document.getElementById('upload-section');
const workspaceSection = document.getElementById('workspace-section');
const processingModal = document.getElementById('processing-modal');
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('video-file-input');

const mainPlayer = document.getElementById('main-player');
const chapterTimelineBar = document.getElementById('chapter-timeline-bar');
const transcriptContainer = document.getElementById('transcript-container');
const chaptersGridContainer = document.getElementById('chapters-grid-container');
const currentChapterToast = document.getElementById('current-chapter-toast');
const toastTitle = document.getElementById('toast-title');

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
  setupTheme();
  setupNavigation();
  setupHistoryListeners();
  setupUploadListeners();
  setupUrlListeners();
  setupTabListeners();
  setupSearchListeners();
  setupQAListeners();
  setupPlayerSync();
  setupFilterListener();
  setupStudyMode();
  setupQuizRunner();
  setupAnalytics();
  setupEnhancedQA();
  setupWatchTracker();
  setupTemporalFeatures();

  // Load initial history count to update badge
  loadHistory(true);

  const clearBtn = document.getElementById('btn-clear-storage');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (confirm('Delete all downloaded videos and temporary files from server storage?')) {
        fetch('/api/history/clear', { method: 'POST' })
          .then(res => res.json())
          .then(() => {
            currentJobId = null;
            currentJobData = null;
            if (pollInterval) clearInterval(pollInterval);
            mainPlayer.pause();
            mainPlayer.src = '';
            workspaceSection.classList.add('hidden');
            uploadSection.classList.remove('hidden');
            loadHistory(false);
            alert('Storage cleared! Downloaded videos and temporary files deleted.');
          })
          .catch(err => alert('Cleanup failed: ' + err.message));
      }
    });
  }

  document.getElementById('btn-new-upload').addEventListener('click', () => {
    navigateTo('home');
    workspaceSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  const btnLoadSample = document.getElementById('btn-load-sample');
  if (btnLoadSample) btnLoadSample.addEventListener('click', loadSampleDemo);
  const btnQuickSample = document.getElementById('btn-quick-sample');
  if (btnQuickSample) btnQuickSample.addEventListener('click', loadSampleDemo);
});

function setupUrlListeners() {
  const urlInput = document.getElementById('video-url-input');
  const processBtn = document.getElementById('btn-process-url');

  const handleUrlSubmit = () => {
    const url = urlInput.value.trim();
    if (!url) {
      alert('Please enter a YouTube link or video URL');
      return;
    }

    showProcessingModal(url);
    fetch('/api/process-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url })
    })
    .then(res => res.json())
    .then(data => {
      if (data.job_id) {
        currentJobId = data.job_id;
        startStatusPolling(currentJobId);
      } else {
        alert('Could not process link: ' + (data.error || 'Unknown error'));
        hideProcessingModal();
      }
    })
    .catch(err => {
      alert('Network error: ' + err.message);
      hideProcessingModal();
    });
  };

  processBtn.addEventListener('click', handleUrlSubmit);
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleUrlSubmit();
  });
}

// Upload & Drag-and-Drop
function setupUploadListeners() {
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });
}

function uploadFile(file) {
  const formData = new FormData();
  formData.append('video', file);

  showProcessingModal(file.name);

  fetch('/api/upload', {
    method: 'POST',
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    if (data.job_id) {
      currentJobId = data.job_id;
      startStatusPolling(currentJobId);
    } else {
      alert('Upload failed: ' + (data.error || 'Unknown error'));
      hideProcessingModal();
    }
  })
  .catch(err => {
    alert('Upload error: ' + err.message);
    hideProcessingModal();
  });
}

function loadSampleDemo() {
  showProcessingModal('Java_Programming_Masterclass.mp4');

  fetch('/api/load-sample', {
    method: 'POST'
  })
  .then(res => res.json())
  .then(data => {
    if (data.job_id) {
      currentJobId = data.job_id;
      startStatusPolling(currentJobId);
    } else {
      alert('Could not load sample: ' + (data.error || 'Unknown error'));
      hideProcessingModal();
    }
  })
  .catch(err => {
    alert('Failed to load demo: ' + err.message);
    hideProcessingModal();
  });
}

// Processing Modal & Polling
function showProcessingModal(filename) {
  document.getElementById('proc-filename').innerText = filename;
  document.getElementById('proc-bar').style.width = '10%';
  document.getElementById('proc-percent').innerText = '10%';
  document.getElementById('proc-stage-text').innerText = 'Initializing AI pipeline...';

  // Reset steps
  ['step-dl', 'step-meta', 'step-audio', 'step-whisper', 'step-topics', 'step-split'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active', 'done');
  });

  processingModal.classList.remove('hidden');
}

function hideProcessingModal() {
  processingModal.classList.add('hidden');
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

function startStatusPolling(jobId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(() => {
    fetch(`/api/status/${jobId}`)
      .then(res => res.json())
      .then(data => {
        updateProgressUI(data);

        if (data.completed) {
          clearInterval(pollInterval);
          setTimeout(() => {
            hideProcessingModal();
            loadWorkspace(jobId);
          }, 600);
        } else if (data.stage === 'error') {
          clearInterval(pollInterval);
          alert('Error during processing: ' + data.error);
          hideProcessingModal();
        }
      })
      .catch(err => console.error('Status poll error:', err));
  }, 800);
}

function updateProgressUI(data) {
  const progress = data.progress || 10;
  document.getElementById('proc-bar').style.width = `${progress}%`;
  document.getElementById('proc-percent').innerText = `${progress}%`;
  document.getElementById('proc-stage-text').innerText = data.message || 'Processing...';

  const stage = data.stage;
  const stepDl = document.getElementById('step-dl');
  const stepMeta = document.getElementById('step-meta');
  const stepAudio = document.getElementById('step-audio');
  const stepWhisper = document.getElementById('step-whisper');
  const stepTopics = document.getElementById('step-topics');
  const stepSplit = document.getElementById('step-split');

  if (stage === 'downloading') {
    if (stepDl) stepDl.classList.add('active');
  } else if (stage === 'metadata') {
    if (stepDl) { stepDl.classList.remove('active'); stepDl.classList.add('done'); }
    stepMeta.classList.add('active');
  } else if (stage === 'audio_extraction') {
    if (stepDl) stepDl.classList.add('done');
    stepMeta.classList.remove('active'); stepMeta.classList.add('done');
    stepAudio.classList.add('active');
  } else if (stage === 'transcription') {
    if (stepDl) stepDl.classList.add('done');
    stepAudio.classList.remove('active'); stepAudio.classList.add('done');
    stepWhisper.classList.add('active');
  } else if (stage === 'topic_detection') {
    if (stepDl) stepDl.classList.add('done');
    stepWhisper.classList.remove('active'); stepWhisper.classList.add('done');
    stepTopics.classList.add('active');
  } else if (stage === 'video_splitting') {
    if (stepDl) stepDl.classList.add('done');
    stepTopics.classList.remove('active'); stepTopics.classList.add('done');
    stepSplit.classList.add('active');
  } else if (stage === 'completed') {
    [stepDl, stepMeta, stepAudio, stepWhisper, stepTopics, stepSplit].forEach(el => {
      if (el) {
        el.classList.remove('active');
        el.classList.add('done');
      }
    });
  }
}

// Load Completed Job into Workspace
function loadWorkspace(jobId) {
  fetch(`/api/job/${jobId}`)
    .then(res => {
      if (!res.ok) throw new Error('Video data not found');
      return res.json();
    })
    .then(job => {
      currentJobId = jobId;
      currentJobData = job;
      renderWorkspace(job);
      loadHistory(true);
    })
    .catch(err => alert('Failed to load video details: ' + err.message));
}

const CHAPTER_COLORS = [
  '#38bdf8', '#818cf8', '#34d399', '#fbbf24', '#f43f5e', '#a855f7', '#06b6d4'
];

function renderWorkspace(job) {
  // Ensure we are viewing Home page
  navigateTo('home', false);
  uploadSection.classList.add('hidden');
  workspaceSection.classList.remove('hidden');

  // Video Title & Meta
  const cleanHeading = formatCleanTitle(job.filename, job.job_id);
  document.getElementById('video-title').innerText = cleanHeading;
  document.getElementById('meta-duration').innerText = `⏱️ ${job.video_info.duration_formatted || '00:00'}`;
  document.getElementById('meta-chapters').innerText = `📚 ${job.chapters.length} Chapters`;
  document.getElementById('meta-res').innerText = `🖥️ ${job.video_info.width}x${job.video_info.height}`;
  document.getElementById('meta-size').innerText = `💾 ${job.video_info.size_mb} MB`;
  document.getElementById('tab-chap-count').innerText = job.chapters.length;

  document.getElementById('btn-download-notes').href = `/api/download/notes/${job.job_id}`;

  // Load video into main player
  mainPlayer.src = job.master_video_url;
  mainPlayer.load();

  // Render Interactive Timeline Bar
  renderTimelineBar(job.chapters, job.video_info.duration);

  // Render Multi-Track Timeline (BiLSTM Events & Autoencoder Anomalies)
  renderTemporalTracks(job.temporal_events || [], job.anomalies || [], job.video_info.duration);

  // Render Sliced Chapters Grid
  renderChaptersGrid(job.chapters, job.job_id);

  // Render BiLSTM Temporal Events List
  renderTemporalEvents(job.temporal_events || [], job.video_info.duration);

  // Render Autoencoder Anomaly Detection
  renderAnomalies(job.anomalies || [], job.anomaly_timeline || [], job.anomaly_summary || {}, job.video_info.duration);

  // Render Temporal Event MCQs
  renderEventMCQs(job.job_id, job.temporal_events || []);

  // Render Synchronized Transcript
  renderTranscript(job.segments);

  // Render Notes
  renderNotes(job.notes);

  // Auto-switch to chapters tab
  switchTab('chapters-tab');

  // Load QA history for video
  loadQAHistory(job.job_id);

  // Reset study mode view if open
  closeStudyMode();
}

function renderTimelineBar(chapters, totalDuration) {
  chapterTimelineBar.innerHTML = '';
  if (!totalDuration || totalDuration <= 0) totalDuration = 1;

  chapters.forEach((chap, idx) => {
    const dur = chap.end_time - chap.start_time;
    const pct = Math.max(2, (dur / totalDuration) * 100);
    const color = CHAPTER_COLORS[idx % CHAPTER_COLORS.length];

    const segEl = document.createElement('div');
    segEl.className = 'timeline-segment';
    segEl.style.width = `${pct}%`;
    segEl.style.backgroundColor = color;
    segEl.title = `${chap.title} (${chap.start_formatted} - ${chap.end_formatted})`;

    segEl.addEventListener('click', () => {
      seekTo(chap.start_time);
    });

    chapterTimelineBar.appendChild(segEl);
  });
}

function renderChaptersGrid(chapters, jobId) {
  chaptersGridContainer.innerHTML = '';

  chapters.forEach((chap, idx) => {
    const color = CHAPTER_COLORS[idx % CHAPTER_COLORS.length];
    const card = document.createElement('div');
    card.className = 'chapter-card';

    const pointsHtml = (chap.key_points || [])
      .map(p => `<span class="point-tag">${p}</span>`)
      .join('');

    card.innerHTML = `
      <div class="chapter-thumb-wrap">
        <img class="chapter-thumb" src="${chap.thumbnail_url}" alt="${chap.title}" onerror="this.src='/static/img/placeholder.jpg'">
        <span class="chapter-badge-num">Chapter ${chap.chapter_number || (idx + 1)}</span>
        <span class="chapter-badge-time">${chap.start_formatted} – ${chap.end_formatted}</span>
      </div>
      <div class="chapter-body">
        <h4 class="chapter-title" style="border-left: 3px solid ${color}; padding-left: 8px;">${chap.title}</h4>
        <p class="chapter-summary">${chap.summary || 'Topic video clip generated automatically by VidSeek AI.'}</p>
        <div class="key-points-pills">${pointsHtml}</div>
        <div class="chapter-actions">
          <button class="btn btn-primary btn-sm" onclick="seekTo(${chap.start_time})">
            ▶ Watch in Player
          </button>
          <a class="btn btn-secondary btn-sm" href="/api/download/chapter/${jobId}/${chap.video_filename}" download>
            ⬇ Sliced Video (${chap.size_mb}MB)
          </a>
        </div>
      </div>
    `;

    chaptersGridContainer.appendChild(card);
  });
}

function renderTranscript(segments) {
  transcriptContainer.innerHTML = '';

  segments.forEach(seg => {
    const segEl = document.createElement('div');
    segEl.className = 'transcript-segment-card';
    segEl.dataset.start = seg.start;
    segEl.dataset.end = seg.end;
    segEl.id = `transcript-seg-${seg.id}`;

    segEl.innerHTML = `
      <span class="seg-time">${seg.start_formatted}</span>
      <span class="seg-text">${seg.text}</span>
    `;

    segEl.addEventListener('click', () => {
      seekTo(seg.start);
    });

    transcriptContainer.appendChild(segEl);
  });
}

function renderNotes(notesMd) {
  const container = document.getElementById('notes-content-container');
  // Simple markdown to HTML formatter for notes
  let html = notesMd
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`([^`]+)`/gim, '<code>$1</code>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/^\- (.*$)/gim, '<li>$1</li>')
    .replace(/\n\n/gim, '<p></p>');

  container.innerHTML = html;
}

// Player Synchronization with Transcript & Chapter Toast
function setupPlayerSync() {
  mainPlayer.addEventListener('timeupdate', () => {
    const currentTime = mainPlayer.currentTime;
    const duration = mainPlayer.duration || 1;

    // Update timeline time readout
    const curFmt = formatSeconds(currentTime);
    const durFmt = formatSeconds(duration);
    document.getElementById('timeline-time-display').innerText = `${curFmt} / ${durFmt}`;

    if (!currentJobData) return;

    // 1. Identify active chapter
    const currentChap = currentJobData.chapters.find(c => currentTime >= c.start_time && currentTime < c.end_time);
    if (currentChap) {
      toastTitle.innerText = `Ch. ${currentChap.chapter_number}: ${currentChap.title}`;
      currentChapterToast.style.opacity = '1';
    } else {
      currentChapterToast.style.opacity = '0.7';
    }

    // 2. Highlight active segment in transcript
    const activeSeg = currentJobData.segments.find(s => currentTime >= s.start && currentTime <= s.end);
    if (activeSeg) {
      const allCards = document.querySelectorAll('.transcript-segment-card');
      allCards.forEach(c => c.classList.remove('active'));

      const activeCard = document.getElementById(`transcript-seg-${activeSeg.id}`);
      if (activeCard) {
        activeCard.classList.add('active');
        // Smooth scroll if not manually hovering
        activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  });
}

function seekTo(seconds) {
  mainPlayer.currentTime = Math.max(0, seconds);
  mainPlayer.play();
}

function formatSeconds(secs) {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

// Search Logic
function setupSearchListeners() {
  const searchInput = document.getElementById('search-query-input');
  const searchBtn = document.getElementById('btn-run-search');

  const executeSearch = () => {
    const q = searchInput.value.trim();
    if (!q || !currentJobId) return;

    fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: currentJobId, query: q })
    })
    .then(res => res.json())
    .then(data => {
      renderSearchResults(data.results, data.ai_best_match, data.target_concept, q);
      // If user asked an explanatory question like "what is order by", automatically seek to that video moment!
      const qLower = q.toLowerCase();
      if (data.ai_best_match && (qLower.startsWith('what') || qLower.startsWith('explain') || qLower.startsWith('how') || qLower.startsWith('define') || qLower.includes('?'))) {
        seekTo(data.ai_best_match.start);
      }
    })
    .catch(err => console.error('Search error:', err));
  };

  searchBtn.addEventListener('click', executeSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') executeSearch();
  });
}

function applySearch(text) {
  document.getElementById('search-query-input').value = text;
  switchTab('search-tab');
  document.getElementById('btn-run-search').click();
}

function renderSearchResults(results, aiBestMatch, targetConcept, rawQuery) {
  const list = document.getElementById('search-results-list');
  list.innerHTML = '';

  // Render Top Relevant Result Card (AI Best Match)
  if (aiBestMatch) {
    const topicRange = aiBestMatch.topic_interval || aiBestMatch.passage_interval || aiBestMatch.timestamp_formatted;
    const passageRange = aiBestMatch.passage_interval || aiBestMatch.timestamp_formatted;
    const bestCard = document.createElement('div');
    bestCard.className = 'ai-best-match-card';
    bestCard.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.75rem;">
        <div class="ai-best-badge" style="margin-bottom:0;">
          <span>🏆 TOP RELEVANT RESULT • ${aiBestMatch.target_concept.toUpperCase()}</span>
        </div>
        <div class="topic-interval-pill" style="display:inline-flex; align-items:center; padding:0.25rem 0.65rem; border-radius:var(--radius-full); background:var(--badge-bg); color:var(--accent-primary); border:1px solid var(--badge-border); font-weight:700; font-size:0.8rem; font-family:var(--font-mono);">
          ⏱️ ${topicRange}
        </div>
      </div>
      <h4 class="ai-best-title">📍 Topic: ${aiBestMatch.chapter_title} (${topicRange})</h4>
      <p class="ai-best-summary">${aiBestMatch.summary}</p>
      <blockquote class="ai-best-quote">"${aiBestMatch.snippet}"</blockquote>
      <div class="ai-best-actions" style="display:flex; gap:0.75rem; align-items:center; flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="seekTo(${aiBestMatch.start})" style="font-weight:700;">
          ▶ Watch Topic (${topicRange})
        </button>
        <span style="font-size:0.82rem; color:var(--text-muted);">Key passage: ${passageRange}</span>
      </div>
    `;
    list.appendChild(bestCard);
  }

  if (!results || results.length === 0) {
    if (!aiBestMatch) {
      list.innerHTML = `<div class="empty-state"><p>No moments found matching your query. Try different keywords.</p></div>`;
    }
    return;
  }

  const sub = document.createElement('div');
  sub.className = 'search-subheading';
  sub.innerHTML = `<span>Ranked Topic Passages (${results.length})</span>`;
  list.appendChild(sub);

  results.forEach(hit => {
    const card = document.createElement('div');
    card.className = 'search-hit-card';
    const hitRange = hit.topic_interval || hit.passage_interval || hit.timestamp_formatted;
    const hitPassage = hit.passage_interval || hit.timestamp_formatted;
    card.innerHTML = `
      <div class="hit-content">
        <div class="hit-header">
          <span class="hit-chapter">📍 ${hit.chapter_title}</span>
          <span class="hit-time" style="background:var(--badge-bg); color:var(--accent-primary); border:1px solid var(--badge-border); padding:2px 8px; border-radius:4px; font-weight:600;">⏱️ ${hitRange}</span>
        </div>
        <p class="hit-snippet">"${hit.snippet}"</p>
        <span style="font-size:0.75rem; color:var(--text-muted);">Passage moment: ${hitPassage} • Relevance score: ${hit.score}</span>
      </div>
      <button class="btn btn-primary btn-sm" onclick="seekTo(${hit.start})" style="white-space:nowrap;">
        ▶ Watch Topic
      </button>
    `;
    list.appendChild(card);
  });
}

// Ask AI (Q&A)
function setupQAListeners() {
  const input = document.getElementById('qa-question-input');
  const btn = document.getElementById('btn-submit-qa');
  const btnAskCurrent = document.getElementById('btn-ask-current-topic');

  if (btnAskCurrent) {
    btnAskCurrent.addEventListener('click', () => {
      if (!currentJobData || !currentJobData.chapters || currentJobData.chapters.length === 0) {
        alert('Please open or process a video first.');
        return;
      }
      const curTime = mainPlayer.currentTime || 0;
      let activeChap = currentJobData.chapters.find(c => curTime >= c.start_time && curTime <= c.end_time);
      if (!activeChap) activeChap = currentJobData.chapters[0];
      input.value = `Explain the concept of ${activeChap.title} covered at this timestamp`;
      input.focus();
    });
  }

  const ask = () => {
    const q = input.value.trim();
    if (!q || !currentJobId) return;

    const feed = document.getElementById('qa-answers-feed');
    const pendingId = 'pending-' + Date.now();
    const pendingBubble = document.createElement('div');
    pendingBubble.className = 'qa-bubble';
    pendingBubble.id = pendingId;
    pendingBubble.innerHTML = `
      <div class="qa-q-text">Q: "${escapeHtml(q)}"</div>
      <div class="qa-a-text text-muted">Analyzing lecture transcript and finding timestamp...</div>
    `;
    feed.prepend(pendingBubble);
    input.value = '';

    fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: currentJobId, question: q })
    })
    .then(res => res.json())
    .then(ans => {
      renderQABubble(pendingId, q, ans);
      loadQAHistory(currentJobId);
      if (ans.timestamp !== undefined) {
        seekTo(ans.timestamp);
      }
    })
    .catch(err => {
      const bubble = document.getElementById(pendingId);
      if (bubble) {
        bubble.innerHTML = `<div class="qa-a-text text-muted">Error answering question: ${escapeHtml(err.message)}</div>`;
      }
    });
  };

  btn.addEventListener('click', ask);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') ask();
  });
}

function askQuestion(q) {
  const input = document.getElementById('qa-question-input');
  if (input) input.value = q;
  switchTab('qa-tab');
  const btn = document.getElementById('btn-submit-qa');
  if (btn) btn.click();
}

// Tabs
function setupTabListeners() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      switchTab(target);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    const isActive = b.dataset.tab === tabId;
    b.classList.toggle('active', isActive);
    if (isActive && window.innerWidth <= 768) {
      try {
        b.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      } catch (e) {}
    }
  });
  document.querySelectorAll('.tab-content').forEach(c => {
    c.classList.toggle('active', c.id === tabId);
  });
}

// Transcript Filter
function setupFilterListener() {
  const filterInput = document.getElementById('transcript-filter');
  if (!filterInput) return;
  filterInput.addEventListener('input', (e) => {
    const val = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.transcript-segment-card').forEach(card => {
      const text = card.innerText.toLowerCase();
      card.style.display = text.includes(val) ? 'block' : 'none';
    });
  });
}

// Light / Dark Theme Management
function setupTheme() {
  const btn = document.getElementById('btn-theme-toggle');
  const label = document.getElementById('theme-label');

  const getSavedTheme = () => {
    const saved = localStorage.getItem('vidseek-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  };

  const applyTheme = (theme, animate = false) => {
    if (animate) {
      document.documentElement.classList.add('theme-transitioning');
      if (btn) btn.classList.add('theme-spin');
    }

    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('vidseek-theme', theme);
    if (label) {
      label.textContent = theme === 'dark' ? 'Light' : 'Dark';
    }
    if (btn) {
      btn.setAttribute('title', `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`);
    }

    window.dispatchEvent(new CustomEvent('vidseek-theme-changed', { detail: { theme } }));

    if (animate) {
      setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
        if (btn) btn.classList.remove('theme-spin');
      }, 500);
    }
  };

  function triggerFullscreenThemeRipple(sourceEl, theme) {
    try {
      const ripple = document.createElement('div');
      ripple.className = 'fullscreen-theme-ripple ' + (theme === 'light' ? 'to-light' : 'to-dark');
      const rect = sourceEl ? sourceEl.getBoundingClientRect() : { left: window.innerWidth / 2, top: 40, width: 0, height: 0 };
      ripple.style.left = (rect.left + (rect.width || 0) / 2) + 'px';
      ripple.style.top = (rect.top + (rect.height || 0) / 2) + 'px';
      document.body.appendChild(ripple);
      setTimeout(() => {
        if (ripple.parentNode) ripple.parentNode.removeChild(ripple);
      }, 800);
    } catch (e) {}
  }

  // Initial sync without animation
  const currentTheme = getSavedTheme();
  applyTheme(currentTheme, false);

  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      triggerFullscreenThemeRipple(btn, next);
      applyTheme(next, true);
    });
  }

  // Follow system theme changes if not overridden
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
      if (!localStorage.getItem('vidseek-theme')) {
        applyTheme(e.matches ? 'light' : 'dark', true);
      }
    });
  }
}

// ==========================================================================
// STRING & TITLE FORMATTING HELPERS
// ==========================================================================

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatCleanTitle(rawTitle, jobId) {
  if (!rawTitle) return 'Educational Lecture Video';
  let t = rawTitle.replace(/\.[^/.]+$/, '').replace(/_/g, ' ').trim();
  if (jobId && t.toLowerCase().startsWith(jobId.toLowerCase())) {
    t = t.substring(jobId.length).trim();
  }
  return t || 'Educational Lecture Video';
}

// ==========================================================================
// MULTI-PAGE NAVIGATION ROUTER (HOME, HISTORY, ABOUT)
// ==========================================================================

function setupNavigation() {
  const navBtns = document.querySelectorAll('.nav-link-btn');
  navBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const page = btn.dataset.page;
      navigateTo(page);
    });
  });

  // Handle URL hash navigation (e.g. #home, #history, #analytics, #about)
  window.addEventListener('hashchange', () => {
    const hash = (window.location.hash || '').replace('#', '').toLowerCase().trim();
    if (['home', 'history', 'analytics', 'about'].includes(hash)) {
      navigateTo(hash, false);
    }
  });

  // Initial page selection from hash or default to home
  const initialHash = (window.location.hash || '').replace('#', '').toLowerCase().trim();
  if (['home', 'history', 'analytics', 'about'].includes(initialHash)) {
    navigateTo(initialHash, false);
  } else {
    navigateTo('home', false);
  }
}

function navigateTo(pageName, updateHash = true) {
  if (!pageName) pageName = 'home';

  // 1. Update navigation tab active states
  document.querySelectorAll('.nav-link-btn').forEach(btn => {
    const isTarget = btn.dataset.page === pageName;
    btn.classList.toggle('active', isTarget);
  });

  // 2. Switch visible page container
  document.querySelectorAll('.page-view').forEach(view => {
    const isTarget = view.id === `page-${pageName}`;
    if (isTarget) {
      view.classList.remove('hidden');
      view.classList.add('active');
    } else {
      view.classList.add('hidden');
      view.classList.remove('active');
    }
  });

  // 3. Sync browser URL hash
  if (updateHash) {
    try {
      history.replaceState(null, '', `#${pageName}`);
    } catch (e) {
      window.location.hash = pageName;
    }
  }

  // 4. Page lifecycle triggers
  if (pageName === 'history') {
    loadHistory(false);
  } else if (pageName === 'analytics') {
    loadAnalyticsDashboard();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (pageName === 'home') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (pageName === 'about') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

// ==========================================================================
// PERSISTENT VIDEO HISTORY MODULE
// ==========================================================================

let cachedHistoryJobs = [];

function setupHistoryListeners() {
  const refreshBtn = document.getElementById('btn-refresh-history');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      loadHistory(false);
    });
  }

  const clearAllBtn = document.getElementById('btn-clear-all-history');
  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', () => {
      if (confirm('Are you sure you want to permanently delete all saved video lectures from your history?')) {
        fetch('/api/history/clear', { method: 'POST' })
          .then(res => res.json())
          .then(() => {
            cachedHistoryJobs = [];
            renderHistoryCards([]);
            updateHistoryCountBadge(0);
            if (currentJobId) {
              currentJobId = null;
              currentJobData = null;
              if (mainPlayer) {
                mainPlayer.pause();
                mainPlayer.src = '';
              }
              workspaceSection.classList.add('hidden');
              uploadSection.classList.remove('hidden');
            }
          })
          .catch(err => alert('Failed to clear history: ' + err.message));
      }
    });
  }

  const searchInput = document.getElementById('history-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      if (!q) {
        renderHistoryCards(cachedHistoryJobs);
        return;
      }
      const filtered = cachedHistoryJobs.filter(job => {
        const titleMatch = (job.title || '').toLowerCase().includes(q);
        const filenameMatch = (job.filename || '').toLowerCase().includes(q);
        const sourceMatch = (job.source_type || '').toLowerCase().includes(q);
        return titleMatch || filenameMatch || sourceMatch;
      });
      renderHistoryCards(filtered, q);
    });
  }
}

function updateHistoryCountBadge(count) {
  const badge = document.getElementById('history-count-badge');
  if (badge) {
    badge.innerText = count || 0;
  }
}

function loadHistory(countOnly = false) {
  fetch('/api/jobs')
    .then(res => res.json())
    .then(data => {
      const jobs = data.jobs || [];
      cachedHistoryJobs = jobs;
      updateHistoryCountBadge(jobs.length);

      if (!countOnly) {
        renderHistoryCards(jobs);
      }
    })
    .catch(err => console.warn('Could not load history library:', err));
}

function renderHistoryCards(jobs, filterQuery = '') {
  const grid = document.getElementById('history-videos-grid');
  const emptyState = document.getElementById('history-empty-state');
  if (!grid || !emptyState) return;

  grid.innerHTML = '';

  if (!jobs || jobs.length === 0) {
    grid.style.display = 'none';
    emptyState.classList.remove('hidden');
    if (filterQuery) {
      emptyState.querySelector('h3').innerText = `No videos match "${filterQuery}"`;
      emptyState.querySelector('p').innerText = 'Try searching with another keyword or clear the search input.';
    } else {
      emptyState.querySelector('h3').innerText = 'No Processed Videos in History Yet';
      emptyState.querySelector('p').innerText = 'Paste a YouTube URL or upload a video on the Home page to start building your video lecture library.';
    }
    return;
  }

  emptyState.classList.add('hidden');
  grid.style.display = 'grid';

  jobs.forEach(job => {
    const card = document.createElement('div');
    card.className = 'history-card';
    card.id = `history-card-${job.job_id}`;

    // Source badges
    let sourceClass = 'source-pill-upload';
    let sourceLabel = 'Upload';
    let sourceIcon = '📁';
    if (job.source_type === 'youtube') {
      sourceClass = 'source-pill-youtube';
      sourceLabel = 'YouTube';
      sourceIcon = '▶';
    } else if (job.source_type === 'sample') {
      sourceClass = 'source-pill-sample';
      sourceLabel = 'Sample';
      sourceIcon = '⭐';
    } else if (job.source_type === 'web') {
      sourceClass = 'source-pill-web';
      sourceLabel = 'Web Video';
      sourceIcon = '🌐';
    }

    const title = job.title || 'Educational Lecture Video';
    const duration = job.duration || '00:00';
    const chaptersCount = job.chapters_count || 0;
    const dateStr = job.created_at_formatted || 'Saved';
    const thumbUrl = job.thumbnail_url || `/api/video/${job.job_id}/thumbnail/thumbnail.jpg`;

    card.innerHTML = `
      <div class="history-thumb-wrap" onclick="openJobFromHistory('${job.job_id}')" title="Click to study: ${escapeHtml(title)}">
        <img src="${thumbUrl}" alt="${escapeHtml(title)}" loading="lazy" onerror="this.onerror=null;this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'340\\' height=\\'190\\' viewBox=\\'0 0 340 190\\' fill=\\'%230f172a\\'><rect width=\\'100%\\' height=\\'100%\\' fill=\\'%231e293b\\'/><text x=\\'50%\\' y=\\'50%\\' fill=\\'%2394a3b8\\' font-size=\\'14\\' font-family=\\'sans-serif\\' text-anchor=\\'middle\\' dominant-baseline=\\'middle\\'>${escapeHtml(title).substring(0, 24)}</text></svg>'">
        <span class="history-source-badge ${sourceClass}">${sourceIcon} ${sourceLabel}</span>
        <span class="history-duration-badge">⏱️ ${duration}</span>
        <div class="history-play-overlay">
          <div class="history-play-btn-circle">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
          </div>
        </div>
      </div>
      <div class="history-body">
        <h4 class="history-title" onclick="openJobFromHistory('${job.job_id}')" title="${escapeHtml(title)}">${escapeHtml(title)}</h4>
        <div class="history-meta-row">
          <span>📚 ${chaptersCount} Chapters</span>
          <span>•</span>
          <span>📅 ${dateStr}</span>
        </div>
        <div class="history-card-footer">
          <button class="btn-history-open" onclick="openJobFromHistory('${job.job_id}')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            Open &amp; Study Video
          </button>
          <button class="btn-history-del" onclick="deleteHistoryItem('${job.job_id}', event)" title="Delete video from history">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      </div>
    `;

    grid.appendChild(card);
  });
}

function openJobFromHistory(jobId) {
  if (!jobId) return;

  fetch(`/api/job/${jobId}`)
    .then(res => {
      if (!res.ok) throw new Error('Video data not found on server');
      return res.json();
    })
    .then(job => {
      currentJobId = jobId;
      currentJobData = job;
      renderWorkspace(job);
      navigateTo('home');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    })
    .catch(err => {
      alert('Could not open video: ' + err.message);
    });
}

function deleteHistoryItem(jobId, event) {
  if (event) event.stopPropagation();
  if (!confirm('Are you sure you want to delete this video from your history?')) return;

  fetch(`/api/history/delete/${jobId}`, { method: 'POST' })
    .then(res => res.json())
    .then(() => {
      if (currentJobId === jobId) {
        currentJobId = null;
        currentJobData = null;
        if (mainPlayer) {
          mainPlayer.pause();
          mainPlayer.src = '';
        }
        workspaceSection.classList.add('hidden');
        uploadSection.classList.remove('hidden');
      }
      loadHistory(false);
    })
    .catch(err => alert('Failed to delete item: ' + err.message));
}

// ==========================================================================
// A. AI STUDY MODE CONTROLLER
// ==========================================================================

let activeStudyTopicData = null;

function setupStudyMode() {
  const btnOpen = document.getElementById('btn-open-study-mode');
  if (btnOpen) {
    btnOpen.addEventListener('click', () => {
      openStudyMode();
    });
  }

  const btnClose = document.getElementById('btn-close-study-mode');
  if (btnClose) {
    btnClose.addEventListener('click', () => {
      closeStudyMode();
    });
  }

  const btnStudyFullQuiz = document.getElementById('btn-study-full-quiz');
  if (btnStudyFullQuiz) {
    btnStudyFullQuiz.addEventListener('click', () => {
      openFullLectureQuiz(currentJobId);
    });
  }

  const btnCloseTopicStudy = document.getElementById('btn-close-topic-study');
  if (btnCloseTopicStudy) {
    btnCloseTopicStudy.addEventListener('click', () => {
      const modal = document.getElementById('study-topic-modal');
      if (modal) modal.classList.add('hidden');
    });
  }
}

function openStudyMode() {
  if (!currentJobId) {
    alert('Please open or process a video first to enter Study Mode.');
    return;
  }
  const theaterGrid = document.querySelector('.theater-grid');
  const studyModeView = document.getElementById('study-mode-view');
  if (theaterGrid) theaterGrid.classList.add('hidden');
  if (studyModeView) studyModeView.classList.remove('hidden');

  const titleEl = document.getElementById('study-mode-video-title');
  if (titleEl && currentJobData) {
    titleEl.innerText = formatCleanTitle(currentJobData.filename, currentJobData.job_id);
  }

  loadStudyModeData(currentJobId);
  window.scrollTo({ top: (studyModeView ? studyModeView.offsetTop - 50 : 0), behavior: 'smooth' });
}

function closeStudyMode() {
  const theaterGrid = document.querySelector('.theater-grid');
  const studyModeView = document.getElementById('study-mode-view');
  if (studyModeView) studyModeView.classList.add('hidden');
  if (theaterGrid) theaterGrid.classList.remove('hidden');
}

function loadStudyModeData(jobId) {
  if (!jobId) return;

  fetch(`/api/study/video/${jobId}`)
    .then(res => res.json())
    .then(data => {
      // 1. Metrics
      document.getElementById('study-stat-total-topics').innerText = data.total_topics || 0;
      document.getElementById('study-stat-completed').innerText = data.completed_topics || 0;
      const remaining = Math.max(0, (data.total_topics || 0) - (data.completed_topics || 0));
      document.getElementById('study-stat-remaining-sub').innerText = `${remaining} Remaining`;

      const mins = Math.round((data.watch_time_seconds || 0) / 60);
      document.getElementById('study-stat-study-time').innerText = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`;

      const pct = data.progress_pct || 0;
      document.getElementById('study-stat-progress-pct').innerText = `${pct}%`;
      const fill = document.getElementById('study-stat-progress-fill');
      if (fill) fill.style.width = `${pct}%`;

      // 2. Render Topic Cards Grid
      renderStudyCardsGrid(data.topics || [], jobId);
    })
    .catch(err => {
      console.error('Failed to load study mode data:', err);
    });
}

function renderStudyCardsGrid(topics, jobId) {
  const grid = document.getElementById('study-topics-grid');
  if (!grid) return;
  grid.innerHTML = '';

  if (topics.length === 0) {
    grid.innerHTML = `<div class="text-muted" style="padding: 2rem;">No topic segments detected for this video yet.</div>`;
    return;
  }

  topics.forEach((t, idx) => {
    const card = document.createElement('div');
    card.className = 'study-topic-card' + (t.status === 'completed' ? ' is-completed' : '');

    const isCompleted = t.status === 'completed';
    const hasAttempts = (t.quiz_attempts || 0) > 0;
    const bestScore = t.best_score || 0;

    let scoreBadgeHtml = '';
    if (hasAttempts) {
      if (bestScore >= 60) {
        scoreBadgeHtml = `<span class="study-score-pill score-pass">🎯 Best Quiz: ${bestScore}%</span>`;
      } else {
        scoreBadgeHtml = `<span class="study-score-pill score-weak">⚠ Best Quiz: ${bestScore}%</span>`;
      }
    }

    const keyPointsHtml = (t.key_points || [])
      .slice(0, 3)
      .map(kp => `<span class="study-card-chip">${escapeHtml(kp)}</span>`)
      .join('');

    card.innerHTML = `
      <div class="study-card-header">
        <div class="study-card-index">TOPIC ${idx + 1}</div>
        <div class="study-card-badges">
          ${isCompleted ? '<span class="study-status-pill status-completed">✓ Completed</span>' : (t.status === 'in_progress' ? '<span class="study-status-pill status-in-progress">◐ In Progress</span>' : '<span class="study-status-pill status-not-started">○ Not Started</span>')}
          ${scoreBadgeHtml}
        </div>
      </div>
      <h4 class="study-card-title">${escapeHtml(t.title)}</h4>
      <div class="study-card-time">⏱️ ${t.start_formatted} – ${t.end_formatted}</div>
      <p class="study-card-summary">${escapeHtml((t.summary || '').substring(0, 140))}${((t.summary || '').length > 140) ? '...' : ''}</p>
      <div class="study-card-chips">${keyPointsHtml}</div>
      <div class="study-card-footer">
        <button class="btn btn-secondary btn-sm btn-study-deep" title="Step-by-step deep-dive study">
          📖 Deep-Dive
        </button>
        <button class="btn btn-secondary btn-sm btn-study-watch" title="Watch video segment">
          ▶ Watch
        </button>
        <button class="btn btn-primary btn-sm btn-study-quiz" title="Test knowledge with quiz">
          📝 Quiz
        </button>
        <button class="btn btn-sm ${isCompleted ? 'btn-emerald-outline' : 'btn-ghost-check'} btn-study-toggle" title="Toggle completion">
          ${isCompleted ? '✓ Done' : 'Mark Done'}
        </button>
      </div>
    `;

    // Wire Card Events
    card.querySelector('.btn-study-deep').addEventListener('click', () => {
      openStudyTopicModal(t);
    });

    card.querySelector('.btn-study-watch').addEventListener('click', () => {
      closeStudyMode();
      seekTo(t.start_time);
    });

    card.querySelector('.btn-study-quiz').addEventListener('click', () => {
      openTopicQuiz(jobId, t.topic_id);
    });

    card.querySelector('.btn-study-toggle').addEventListener('click', () => {
      toggleTopicComplete(jobId, t.topic_id, !isCompleted);
    });

    grid.appendChild(card);
  });
}

function openStudyTopicModal(topic) {
  activeStudyTopicData = topic;
  const modal = document.getElementById('study-topic-modal');
  if (!modal) return;

  document.getElementById('study-topic-modal-title').innerText = topic.title || 'Topic Study';
  document.getElementById('study-topic-modal-time').innerText = `⏱️ ${topic.start_formatted} – ${topic.end_formatted}`;
  document.getElementById('study-flow-summary').innerText = topic.summary || 'Summary generated from lecture transcript...';

  // Render Concepts
  const conceptsContainer = document.getElementById('study-flow-concepts');
  conceptsContainer.innerHTML = '';
  const points = topic.key_points || [];
  if (points.length === 0) {
    conceptsContainer.innerHTML = `<span class="text-muted text-sm">Key concepts extracted automatically from transcript.</span>`;
  } else {
    points.forEach(p => {
      const chip = document.createElement('span');
      chip.className = 'flow-concept-chip';
      chip.innerText = p;
      conceptsContainer.appendChild(chip);
    });
  }

  // Render Transcript Excerpt
  const trContainer = document.getElementById('study-flow-transcript');
  trContainer.innerHTML = '';
  if (currentJobData && currentJobData.segments) {
    const topicSegments = currentJobData.segments.filter(s => s.start >= topic.start_time && s.start <= topic.end_time);
    if (topicSegments.length === 0) {
      trContainer.innerHTML = `<p class="text-muted text-sm">Transcript excerpt for this section is synchronizing...</p>`;
    } else {
      topicSegments.forEach(seg => {
        const row = document.createElement('div');
        row.className = 'flow-transcript-row';
        row.innerHTML = `
          <button class="flow-tr-time" title="Jump to timestamp">${seg.start_formatted || formatSeconds(seg.start)}</button>
          <span class="flow-tr-text">${escapeHtml(seg.text)}</span>
        `;
        row.querySelector('.flow-tr-time').addEventListener('click', () => {
          modal.classList.add('hidden');
          closeStudyMode();
          seekTo(seg.start);
        });
        trContainer.appendChild(row);
      });
    }
  }

  // Modal Actions
  const btnWatch = document.getElementById('btn-flow-watch-topic');
  btnWatch.onclick = () => {
    modal.classList.add('hidden');
    closeStudyMode();
    seekTo(topic.start_time);
  };

  const btnQuiz = document.getElementById('btn-flow-take-quiz');
  btnQuiz.onclick = () => {
    modal.classList.add('hidden');
    openTopicQuiz(currentJobId, topic.topic_id);
  };

  const btnAsk = document.getElementById('btn-flow-ask-ai');
  btnAsk.onclick = () => {
    modal.classList.add('hidden');
    closeStudyMode();
    switchTab('qa-tab');
    const input = document.getElementById('qa-question-input');
    if (input) {
      input.value = `Explain the concept of ${topic.title} in detail`;
      input.focus();
    }
  };

  const btnComplete = document.getElementById('btn-flow-mark-complete');
  const isCompleted = topic.status === 'completed';
  btnComplete.innerHTML = isCompleted ? `<span>✓ Mark Incomplete</span>` : `<span>✓ Mark Topic as Completed</span>`;
  btnComplete.onclick = () => {
    toggleTopicComplete(currentJobId, topic.topic_id, !isCompleted, () => {
      topic.status = !isCompleted ? 'completed' : 'in_progress';
      btnComplete.innerHTML = topic.status === 'completed' ? `<span>✓ Mark Incomplete</span>` : `<span>✓ Mark Topic as Completed</span>`;
    });
  };

  modal.classList.remove('hidden');
}

function toggleTopicComplete(jobId, topicId, completed, callback) {
  fetch('/api/study/topic/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      topic_id: topicId,
      completed: completed
    })
  })
  .then(res => res.json())
  .then(res => {
    loadStudyModeData(jobId);
    if (callback) callback(res);
  })
  .catch(err => console.error('Failed to toggle completion:', err));
}

// ==========================================================================
// B. MCQ / QUIZ SYSTEM RUNNER
// ==========================================================================

let activeQuizData = null;
let activeQuizQuestionIdx = 0;
let activeQuizUserAnswers = [];

function setupQuizRunner() {
  const btnFullQuizHeader = document.getElementById('btn-open-full-quiz');
  if (btnFullQuizHeader) {
    btnFullQuizHeader.addEventListener('click', () => {
      openFullLectureQuiz(currentJobId);
    });
  }

  const btnCloseModal = document.getElementById('btn-close-quiz-modal');
  if (btnCloseModal) {
    btnCloseModal.addEventListener('click', closeQuizModal);
  }

  const btnFinish = document.getElementById('btn-finish-quiz');
  if (btnFinish) {
    btnFinish.addEventListener('click', () => {
      closeQuizModal();
      if (currentJobId) {
        loadStudyModeData(currentJobId);
      }
      const analyticsPage = document.getElementById('page-analytics');
      if (analyticsPage && !analyticsPage.classList.contains('hidden')) {
        loadAnalyticsDashboard();
      }
    });
  }
}

function closeQuizModal() {
  const modal = document.getElementById('quiz-modal');
  if (modal) modal.classList.add('hidden');
}

function openTopicQuiz(jobId, topicId) {
  if (!jobId) jobId = currentJobId;
  if (!jobId) {
    alert('Please open a video first.');
    return;
  }
  startQuizSession(`/api/quiz/topic/${jobId}/${topicId}`, 'TOPIC MASTERY QUIZ');
}

function openFullLectureQuiz(jobId) {
  if (!jobId) jobId = currentJobId;
  if (!jobId) {
    alert('Please open a video first.');
    return;
  }
  startQuizSession(`/api/quiz/full/${jobId}`, 'FULL LECTURE MASTERY QUIZ');
}

function startQuizSession(endpointUrl, quizTypeTitle) {
  const modal = document.getElementById('quiz-modal');
  modal.classList.remove('hidden');

  // Loading state
  document.getElementById('quiz-type-badge').innerText = quizTypeTitle;
  document.getElementById('quiz-title-display').innerText = 'Generating Grounded Quiz...';
  document.getElementById('quiz-question-view').classList.remove('hidden');
  document.getElementById('quiz-results-view').classList.add('hidden');
  document.getElementById('quiz-feedback-box').classList.add('hidden');

  document.getElementById('quiz-question-text').innerText = 'Synthesizing lecture concept questions from transcript...';
  document.getElementById('quiz-options-container').innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-secondary); width: 100%;">
      <div class="loading-spinner" style="margin: 0 auto 1rem auto;"></div>
      <p>Analyzing speech passages and building grounded multiple choice questions...</p>
    </div>
  `;

  fetch(endpointUrl)
    .then(res => {
      if (!res.ok) throw new Error('Failed to generate or fetch quiz');
      return res.json();
    })
    .then(data => {
      activeQuizData = data;
      activeQuizQuestionIdx = 0;
      activeQuizUserAnswers = [];

      document.getElementById('quiz-type-badge').innerText = quizTypeTitle;
      document.getElementById('quiz-title-display').innerText = data.title || 'Lecture Quiz';

      renderQuizQuestion();
    })
    .catch(err => {
      document.getElementById('quiz-question-text').innerText = 'Could not load quiz questions.';
      document.getElementById('quiz-options-container').innerHTML = `
        <div style="color: #ef4444; padding: 1.5rem; text-align: center;">
          ${escapeHtml(err.message)}
          <br><br>
          <button class="btn btn-secondary btn-sm" onclick="closeQuizModal()">Close</button>
        </div>
      `;
    });
}

function renderQuizQuestion() {
  if (!activeQuizData || !activeQuizData.questions || activeQuizData.questions.length === 0) {
    alert('No questions available in this quiz.');
    closeQuizModal();
    return;
  }

  const q = activeQuizData.questions[activeQuizQuestionIdx];
  const total = activeQuizData.questions.length;

  // Normalize options and timestamps if coming from temporal event MCQs
  if (!q.options && (q.option_a || q.option_b)) {
    q.options = {
      A: q.option_a || '',
      B: q.option_b || '',
      C: q.option_c || '',
      D: q.option_d || ''
    };
  }
  if (q.source_timestamp !== undefined && q.timestamp === undefined) {
    q.timestamp = q.source_timestamp;
  }
  if (q.source_time_fmt && !q.timestamp_formatted) {
    q.timestamp_formatted = q.source_time_fmt;
  }

  document.getElementById('quiz-question-view').classList.remove('hidden');
  document.getElementById('quiz-results-view').classList.add('hidden');
  document.getElementById('quiz-feedback-box').classList.add('hidden');

  document.getElementById('quiz-step-counter').innerText = `Question ${activeQuizQuestionIdx + 1} of ${total}`;
  document.getElementById('quiz-diff-badge').innerText = q.difficulty || 'Medium';

  const fillPct = Math.round(((activeQuizQuestionIdx) / total) * 100);
  document.getElementById('quiz-progress-fill').style.width = `${fillPct}%`;

  document.getElementById('quiz-question-text').innerText = q.question;

  // Render 4 options
  const optContainer = document.getElementById('quiz-options-container');
  optContainer.innerHTML = '';

  const letters = ['A', 'B', 'C', 'D'];
  letters.forEach(letter => {
    const text = (q.options || {})[letter] || '';
    const btn = document.createElement('button');
    btn.className = 'quiz-option-btn';
    btn.id = `quiz-opt-${letter}`;
    btn.innerHTML = `
      <span class="opt-badge">${letter}</span>
      <span class="opt-text">${escapeHtml(text)}</span>
    `;

    btn.addEventListener('click', () => {
      handleSelectQuizOption(letter, q);
    });

    optContainer.appendChild(btn);
  });
}

function handleSelectQuizOption(chosenLetter, question) {
  // Prevent double answers
  const existingAns = activeQuizUserAnswers.find(a => a.question_id === question.id);
  if (existingAns) return;

  const correctLetter = (question.correct_answer || 'A').toUpperCase();
  const isCorrect = (chosenLetter.toUpperCase() === correctLetter);

  // Lock and style all buttons
  const optButtons = document.querySelectorAll('.quiz-option-btn');
  optButtons.forEach(btn => {
    btn.disabled = true;
    const badge = btn.querySelector('.opt-badge').innerText.trim();
    if (badge === correctLetter) {
      btn.classList.add('correct');
      btn.innerHTML += `<span class="feedback-mark-pill mark-correct">✓ Correct</span>`;
    } else if (badge === chosenLetter && !isCorrect) {
      btn.classList.add('incorrect');
      btn.innerHTML += `<span class="feedback-mark-pill mark-incorrect">✗ Incorrect</span>`;
    }
  });

  // Record answer
  activeQuizUserAnswers.push({
    question_id: question.id,
    selected_option: chosenLetter,
    is_correct: isCorrect
  });

  // Show Feedback Box
  const feedbackBox = document.getElementById('quiz-feedback-box');
  const banner = document.getElementById('feedback-banner');
  const icon = document.getElementById('feedback-icon');
  const title = document.getElementById('feedback-title');
  const explanation = document.getElementById('feedback-explanation');
  const timeDisplay = document.getElementById('feedback-time-display');

  if (isCorrect) {
    banner.className = 'feedback-banner feedback-correct';
    icon.innerText = '✓';
    title.innerText = 'Correct Answer!';
  } else {
    banner.className = 'feedback-banner feedback-incorrect';
    icon.innerText = '✗';
    title.innerText = `Incorrect — The correct answer is Option ${correctLetter}`;
  }

  explanation.innerText = question.explanation || 'Refer to the video lecture segment for complete concept derivation.';
  timeDisplay.innerText = question.timestamp_formatted || formatSeconds(question.timestamp || 0);

  // Jump to Explanation button
  const jumpBtn = document.getElementById('btn-quiz-jump-explanation');
  jumpBtn.onclick = () => {
    closeQuizModal();
    if (question.timestamp !== undefined) {
      seekTo(question.timestamp);
    }
  };

  // Next / Submit button
  const nextBtn = document.getElementById('btn-quiz-next');
  const isLast = (activeQuizQuestionIdx + 1 >= activeQuizData.questions.length);
  nextBtn.innerText = isLast ? 'Submit & View Results ➔' : 'Next Question ➔';
  nextBtn.onclick = () => {
    if (isLast) {
      submitQuizResults();
    } else {
      activeQuizQuestionIdx++;
      renderQuizQuestion();
    }
  };

  feedbackBox.classList.remove('hidden');
}

function submitQuizResults() {
  const total = activeQuizData.questions.length;
  const correctCount = activeQuizUserAnswers.filter(a => a.is_correct).length;
  const accuracy = total > 0 ? Math.round((correctCount / total) * 100) : 0;

  // Post results to backend
  fetch('/api/quiz/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      quiz_id: activeQuizData.quiz_id,
      job_id: activeQuizData.job_id,
      topic_id: activeQuizData.topic_id,
      answers: activeQuizUserAnswers
    })
  })
  .then(res => res.json())
  .catch(err => console.error('Failed to submit quiz score:', err));

  // Switch to Results View
  document.getElementById('quiz-question-view').classList.add('hidden');
  document.getElementById('quiz-feedback-box').classList.add('hidden');
  const resultsView = document.getElementById('quiz-results-view');
  resultsView.classList.remove('hidden');

  // Fill stats
  document.getElementById('results-score-num').innerText = `${accuracy}%`;
  document.getElementById('results-correct-count').innerText = correctCount;
  document.getElementById('results-incorrect-count').innerText = total - correctCount;

  const circle = document.getElementById('results-score-circle');
  const heading = document.getElementById('results-heading');
  const detail = document.getElementById('results-detail-text');
  const weakAlert = document.getElementById('quiz-weak-topic-alert');

  if (accuracy >= 80) {
    if (circle) circle.style.borderColor = '#10b981';
    heading.innerText = 'Outstanding Mastery! 🎉';
    detail.innerText = `You scored ${correctCount} of ${total} questions correctly. You have firmly grasped this lecture content!`;
    weakAlert.classList.add('hidden');
  } else if (accuracy >= 60) {
    if (circle) circle.style.borderColor = '#38bdf8';
    heading.innerText = 'Good Effort! 👍';
    detail.innerText = `You scored ${correctCount} of ${total} questions correctly. Solid foundation!`;
    weakAlert.classList.add('hidden');
  } else {
    if (circle) circle.style.borderColor = '#f43f5e';
    heading.innerText = 'Needs Review ⚠';
    detail.innerText = `You scored ${correctCount} of ${total} questions. Reviewing the topic segment is recommended before re-testing.`;
    weakAlert.classList.remove('hidden');
  }

  // Retake button
  const retakeBtn = document.getElementById('btn-retake-quiz');
  retakeBtn.onclick = () => {
    activeQuizQuestionIdx = 0;
    activeQuizUserAnswers = [];
    renderQuizQuestion();
  };
}

// ==========================================================================
// C. LEARNING ANALYTICS CONTROLLER
// ==========================================================================

function setupAnalytics() {
  // Any initial setup for analytics page
}

function loadAnalyticsDashboard() {
  fetch('/api/analytics/dashboard')
    .then(res => res.json())
    .then(data => {
      // 1. KPI Cards
      document.getElementById('kpi-total-videos').innerText = data.total_videos || 0;
      document.getElementById('kpi-topics-studied').innerText = data.total_topics_studied || 0;

      const mins = Math.round((data.total_study_time_seconds || 0) / 60);
      document.getElementById('kpi-study-time').innerText = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`;

      document.getElementById('kpi-quiz-accuracy').innerText = `${data.overall_accuracy || 0}%`;
      document.getElementById('kpi-quiz-attempts-sub').innerText = `${data.total_quiz_attempts || 0} Quiz Attempts`;

      document.getElementById('kpi-questions-asked').innerText = data.total_questions_asked || 0;
      document.getElementById('kpi-topics-completed').innerText = data.total_topics_completed || 0;

      // 2. Continue Learning Hero Card
      const contWrap = document.getElementById('analytics-continue-container');
      if (data.continue_learning && data.continue_learning.job_id) {
        contWrap.classList.remove('hidden');
        document.getElementById('continue-video-title').innerText = data.continue_learning.video_title || 'Recent Video';
        document.getElementById('continue-topic-name').innerText = data.continue_learning.last_topic_title || 'Introduction';
        document.getElementById('continue-timestamp').innerText = data.continue_learning.last_timestamp_formatted || '00:00';

        const btnCont = document.getElementById('btn-continue-watching');
        btnCont.onclick = () => {
          openJobFromHistory(data.continue_learning.job_id);
          setTimeout(() => {
            if (data.continue_learning.last_timestamp) {
              seekTo(data.continue_learning.last_timestamp);
            }
          }, 600);
        };
      } else {
        contWrap.classList.add('hidden');
      }

      // 3. Weak Topics Section
      renderWeakTopics(data.weak_topics || []);

      // 4. Topic Progress by Video Checklists
      renderVideoProgressChecklists(data.video_progress || []);

      // 5. Weekly Activity Chart
      renderActivityChart(data.weekly_activity || []);
    })
    .catch(err => {
      console.error('Failed to load analytics dashboard:', err);
    });
}

function renderWeakTopics(weakTopics) {
  const container = document.getElementById('analytics-weak-topics-container');
  const grid = document.getElementById('weak-topics-grid');
  if (!grid) return;
  grid.innerHTML = '';

  if (!weakTopics || weakTopics.length === 0) {
    grid.innerHTML = `
      <div class="empty-weak-state">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
          <polyline points="22 4 12 14.01 9 11.01"></polyline>
        </svg>
        <span>Outstanding! No weak topics detected. All your quiz accuracy scores are 60% or higher.</span>
      </div>
    `;
    return;
  }

  weakTopics.forEach(wt => {
    const card = document.createElement('div');
    card.className = 'weak-topic-card';
    card.innerHTML = `
      <div class="weak-card-top">
        <span class="weak-video-tag">🎬 ${escapeHtml(wt.video_title)}</span>
        <span class="weak-score-badge">Accuracy: ${wt.accuracy}%</span>
      </div>
      <h4 class="weak-card-title">${escapeHtml(wt.topic_title)}</h4>
      <p class="weak-recommendation">Recommendation: Review video from ${wt.start_formatted} to strengthen fundamental understanding.</p>
      <div class="weak-actions-row">
        <button class="btn btn-secondary btn-sm btn-weak-watch">
          ▶ Watch Segment (${wt.start_formatted})
        </button>
        <button class="btn btn-primary btn-sm btn-weak-quiz">
          📝 Retake Quiz
        </button>
      </div>
    `;

    card.querySelector('.btn-weak-watch').addEventListener('click', () => {
      openJobFromHistory(wt.job_id);
      setTimeout(() => {
        seekTo(wt.start_time || 0);
      }, 600);
    });

    card.querySelector('.btn-weak-quiz').addEventListener('click', () => {
      openTopicQuiz(wt.job_id, wt.topic_id);
    });

    grid.appendChild(card);
  });
}

function renderVideoProgressChecklists(videoProgress) {
  const container = document.getElementById('analytics-video-progress-list');
  if (!container) return;
  container.innerHTML = '';

  if (!videoProgress || videoProgress.length === 0) {
    container.innerHTML = `
      <div class="video-progress-empty" style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2.5rem 1rem; text-align: center; height: 100%;">
        <span style="font-size: 2.2rem; margin-bottom: 0.6rem; opacity: 0.85;">📚</span>
        <h4 style="font-size: 1.05rem; font-weight: 650; margin-bottom: 0.35rem;">No Video Topics Logged Yet</h4>
        <p class="text-muted text-sm" style="max-width: 340px; line-height: 1.55; margin: 0 auto;">Process a lecture video or launch AI Study Mode to track topic-by-topic checklists and mastery status.</p>
      </div>
    `;
    return;
  }

  videoProgress.forEach(vp => {
    const card = document.createElement('div');
    card.className = 'video-progress-card';

    const pct = vp.progress_pct || 0;
    const topicsHtml = (vp.topics || []).map(t => {
      const isDone = t.status === 'completed';
      const isProg = t.status === 'in_progress';
      const icon = isDone ? '<span class="chk-icon chk-done">✓</span>' : (isProg ? '<span class="chk-icon chk-prog">◐</span>' : '<span class="chk-icon chk-none">○</span>');
      return `
        <div class="topic-chk-item ${isDone ? 'done' : ''}">
          ${icon}
          <span class="topic-chk-title">${escapeHtml(t.title)}</span>
          <span class="topic-chk-time">${t.start_formatted} – ${t.end_formatted}</span>
        </div>
      `;
    }).join('');

    card.innerHTML = `
      <div class="vp-header">
        <div class="vp-title-group">
          <h4>${escapeHtml(vp.video_title)}</h4>
          <span class="text-muted text-xs">${vp.completed_topics || 0} of ${vp.total_topics || 0} Topics Completed</span>
        </div>
        <span class="vp-pct mono">${pct}%</span>
      </div>
      <div class="vp-progress-bar-bg">
        <div class="vp-progress-bar-fill" style="width: ${pct}%;"></div>
      </div>
      <div class="vp-topics-list">
        ${topicsHtml}
      </div>
    `;

    container.appendChild(card);
  });
}

function renderActivityChart(activity) {
  const container = document.getElementById('activity-chart-container');
  if (!container) return;
  container.innerHTML = '';

  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  let chartData = activity;
  if (!chartData || chartData.length === 0) {
    chartData = days.map(d => ({ day_name: d, minutes: 0 }));
  }

  const maxMins = Math.max(...chartData.map(a => a.minutes || 0), 30);
  const totalMins = chartData.reduce((sum, a) => sum + (a.minutes || 0), 0);
  const activeDays = chartData.filter(a => (a.minutes || 0) > 0).length;
  const avgMins = Math.round(totalMins / 7);

  const chart = document.createElement('div');
  chart.className = 'activity-chart-grid';

  chartData.forEach(a => {
    const barHeightPct = Math.round(((a.minutes || 0) / maxMins) * 100);
    const col = document.createElement('div');
    col.className = 'chart-col';
    col.innerHTML = `
      <div class="chart-bar-wrap" title="${a.day_name}: ${a.minutes} min">
        <span class="chart-val-label">${a.minutes > 0 ? a.minutes + 'm' : ''}</span>
        <div class="chart-bar-fill" style="height: ${Math.max(barHeightPct, 6)}%;"></div>
      </div>
      <span class="chart-day-label">${a.day_name}</span>
    `;
    chart.appendChild(col);
  });

  const summaryRow = document.createElement('div');
  summaryRow.className = 'activity-summary-row';
  summaryRow.innerHTML = `
    <div class="activity-summary-item">
      <span class="activity-sum-val">${totalMins}m</span>
      <span class="activity-sum-lbl">Total Studied</span>
    </div>
    <div class="activity-summary-item">
      <span class="activity-sum-val">${avgMins}m/day</span>
      <span class="activity-sum-lbl">Daily Average</span>
    </div>
    <div class="activity-summary-item">
      <span class="activity-sum-val">${activeDays}/7</span>
      <span class="activity-sum-lbl">Active Days</span>
    </div>
  `;

  container.appendChild(chart);
  container.appendChild(summaryRow);
}

// ==========================================================================
// D. ENHANCED VIDEO Q&A HELPERS
// ==========================================================================

function setupEnhancedQA() {
  // Attached on DOM ready
}

function renderQABubble(bubbleId, questionText, ans) {
  const bubble = document.getElementById(bubbleId);
  if (!bubble) return;

  const historyId = ans.history_id || 'null';
  const escapedQ = escapeHtml(questionText);
  const escapedAns = (ans.answer || '').replace(/\n\n/g, '<br><br>');

  bubble.innerHTML = `
    <div class="qa-q-text">Q: "${escapedQ}"</div>
    <div class="qa-a-text" id="ans-text-${bubbleId}">${escapedAns}</div>
    <div class="qa-bubble-actions">
      <button class="qa-jump-btn" onclick="seekTo(${ans.timestamp})">
        📍 Jump to ${ans.timestamp_formatted} in "${escapeHtml(ans.chapter_title)}"
      </button>
      <button class="btn btn-ghost-subtle btn-sm btn-qa-simplify" id="btn-simplify-${bubbleId}">
        💡 Explain Simply
      </button>
      <button class="btn btn-ghost-subtle btn-sm btn-qa-followup" id="btn-followup-${bubbleId}">
        💬 Follow-up
      </button>
    </div>
    <div class="qa-followup-box hidden" id="followup-box-${bubbleId}">
      <div class="qa-followup-input-wrap">
        <input type="text" class="qa-followup-input" id="input-followup-${bubbleId}" placeholder="Ask a follow-up about this topic...">
        <button class="btn btn-primary btn-sm" id="btn-send-followup-${bubbleId}">Send</button>
      </div>
      <div class="qa-followup-thread" id="thread-${bubbleId}"></div>
    </div>
  `;

  // Simplify Button
  const btnSimp = document.getElementById(`btn-simplify-${bubbleId}`);
  btnSimp.onclick = () => {
    btnSimp.disabled = true;
    btnSimp.innerText = 'Simplifying...';
    fetch('/api/qa/simplify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: currentJobId,
        history_id: historyId !== 'null' ? historyId : null,
        original_question: questionText,
        original_answer: ans.answer
      })
    })
    .then(res => res.json())
    .then(simRes => {
      btnSimp.style.display = 'none';
      const ansBox = document.getElementById(`ans-text-${bubbleId}`);
      const simpDiv = document.createElement('div');
      simpDiv.className = 'qa-simplified-card';
      simpDiv.innerHTML = `
        <div class="simplified-tag">🐣 SIMPLIFIED BEGINNER BREAKDOWN:</div>
        <p>${escapeHtml(simRes.simplified_answer)}</p>
      `;
      ansBox.appendChild(simpDiv);
    })
    .catch(err => {
      btnSimp.innerText = '💡 Explain Simply';
      btnSimp.disabled = false;
      alert('Could not simplify explanation: ' + err.message);
    });
  };

  // Follow-up Box Toggle
  const btnFollow = document.getElementById(`btn-followup-${bubbleId}`);
  const followBox = document.getElementById(`followup-box-${bubbleId}`);
  btnFollow.onclick = () => {
    followBox.classList.toggle('hidden');
    const finput = document.getElementById(`input-followup-${bubbleId}`);
    if (!followBox.classList.contains('hidden') && finput) {
      finput.focus();
    }
  };

  // Follow-up Submit
  const btnSend = document.getElementById(`btn-send-followup-${bubbleId}`);
  const fInput = document.getElementById(`input-followup-${bubbleId}`);
  const thread = document.getElementById(`thread-${bubbleId}`);

  const sendFollowup = () => {
    const fText = fInput.value.trim();
    if (!fText) return;

    const replyDiv = document.createElement('div');
    replyDiv.className = 'qa-reply-item';
    replyDiv.innerHTML = `
      <div class="qa-reply-q">↳ <em>"${escapeHtml(fText)}"</em></div>
      <div class="qa-reply-a text-muted">Reasoning with context...</div>
    `;
    thread.appendChild(replyDiv);
    fInput.value = '';

    fetch('/api/qa/followup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: currentJobId,
        parent_history_id: historyId !== 'null' ? historyId : null,
        parent_question: questionText,
        parent_answer: ans.answer,
        followup_question: fText
      })
    })
    .then(res => res.json())
    .then(fRes => {
      replyDiv.querySelector('.qa-reply-a').innerHTML = escapeHtml(fRes.answer).replace(/\n\n/g, '<br><br>');
      loadQAHistory(currentJobId);
    })
    .catch(err => {
      replyDiv.querySelector('.qa-reply-a').innerText = 'Error answering follow-up: ' + err.message;
    });
  };

  btnSend.onclick = sendFollowup;
  fInput.onkeydown = (e) => {
    if (e.key === 'Enter') sendFollowup();
  };
}

function loadQAHistory(jobId) {
  if (!jobId) return;

  fetch(`/api/qa/history/${jobId}`)
    .then(res => res.json())
    .then(data => {
      const history = data.history || [];
      const countEl = document.getElementById('qa-history-count');
      if (countEl) countEl.innerText = history.length;

      const list = document.getElementById('qa-history-list');
      if (!list) return;
      list.innerHTML = '';

      if (history.length === 0) {
        list.innerHTML = `<p class="text-muted text-sm" style="padding: 0.5rem 0;">No previous questions asked yet for this video.</p>`;
        return;
      }

      history.forEach(item => {
        const row = document.createElement('div');
        row.className = 'qa-history-item';
        row.innerHTML = `
          <div class="qa-hist-left">
            <span class="qa-hist-q">❓ ${escapeHtml(item.question)}</span>
            <span class="qa-hist-time text-muted">${item.timestamp_formatted || '00:00'} • ${escapeHtml(item.created_at || '')}</span>
          </div>
          <button class="btn btn-ghost-subtle btn-xs btn-hist-jump">📍 Jump</button>
        `;

        row.querySelector('.qa-hist-q').addEventListener('click', () => {
          askQuestion(item.question);
        });

        row.querySelector('.btn-hist-jump').addEventListener('click', (e) => {
          e.stopPropagation();
          if (item.timestamp !== undefined) {
            seekTo(item.timestamp);
          }
        });

        list.appendChild(row);
      });
    })
    .catch(err => console.error('Failed to load QA history:', err));
}

// ==========================================================================
// E. VIDEO WATCH TRACKER (HEARTBEAT)
// ==========================================================================

let lastReportedTime = 0;
let lastHeartbeatTimestamp = 0;

function setupWatchTracker() {
  if (!mainPlayer) return;

  mainPlayer.addEventListener('timeupdate', () => {
    if (!currentJobId) return;

    const now = Date.now();
    // Send event every 6 seconds while video plays
    if (now - lastHeartbeatTimestamp > 6000) {
      const curTime = mainPlayer.currentTime;
      const delta = Math.min(10, Math.max(1, Math.round(curTime - lastReportedTime)));
      lastReportedTime = curTime;
      lastHeartbeatTimestamp = now;

      let activeTopic = null;
      if (currentJobData && currentJobData.chapters) {
        activeTopic = currentJobData.chapters.find(c => curTime >= c.start_time && curTime <= c.end_time);
      }

      fetch('/api/learning/watch-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: currentJobId,
          current_time: curTime,
          duration_watched: delta,
          active_topic_id: activeTopic ? activeTopic.topic_id : null,
          active_topic_title: activeTopic ? activeTopic.title : null
        })
      }).catch(() => {});
    }
  });

  mainPlayer.addEventListener('pause', () => {
    if (!currentJobId) return;
    const curTime = mainPlayer.currentTime;
    lastReportedTime = curTime;

    let activeTopic = null;
    if (currentJobData && currentJobData.chapters) {
      activeTopic = currentJobData.chapters.find(c => curTime >= c.start_time && curTime <= c.end_time);
    }

    fetch('/api/learning/watch-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: currentJobId,
        current_time: curTime,
        duration_watched: 0,
        active_topic_id: activeTopic ? activeTopic.topic_id : null,
        active_topic_title: activeTopic ? activeTopic.title : null
      })
    }).catch(() => {});
  });
}

// =========================================================================
// FEATURE 1, 2, 3: TEMPORAL EVENTS, ANOMALY DETECTION & EVENT MCQS
// =========================================================================

function setupTemporalFeatures() {
  const btnHeaderEventsQuiz = document.getElementById('btn-open-events-quiz');
  if (btnHeaderEventsQuiz) {
    btnHeaderEventsQuiz.addEventListener('click', () => {
      openTemporalEventQuiz(currentJobId);
    });
  }

  const btnQuickEventsQuiz = document.getElementById('btn-quick-events-quiz');
  if (btnQuickEventsQuiz) {
    btnQuickEventsQuiz.addEventListener('click', () => {
      openTemporalEventQuiz(currentJobId);
    });
  }

  const btnStartTemporalQuiz = document.getElementById('btn-start-temporal-quiz');
  if (btnStartTemporalQuiz) {
    btnStartTemporalQuiz.addEventListener('click', () => {
      openTemporalEventQuiz(currentJobId);
    });
  }
}

function openTemporalEventQuiz(jobId) {
  if (!jobId) jobId = currentJobId;
  if (!jobId) {
    alert('Please open a video first.');
    return;
  }
  startQuizSession(`/api/quiz/temporal/${jobId}`, 'TEMPORAL VIDEO EVENT QUIZ');
}

function renderTemporalTracks(events, anomalies, totalDuration) {
  const eventsTrack = document.getElementById('events-timeline-track');
  const anomaliesTrack = document.getElementById('anomalies-timeline-track');
  const eventsCount = document.getElementById('track-events-count');
  const anomaliesCount = document.getElementById('track-anomalies-count');

  if (!eventsTrack || !anomaliesTrack) return;
  eventsTrack.innerHTML = '';
  anomaliesTrack.innerHTML = '';

  const dur = (totalDuration && totalDuration > 0) ? totalDuration : 1;
  const numEvents = events ? events.length : 0;
  const numAnomalies = anomalies ? anomalies.length : 0;

  if (eventsCount) eventsCount.innerText = `${numEvents} Events`;
  if (anomaliesCount) anomaliesCount.innerText = `${numAnomalies} Anomalies`;

  // Render Event Segments on Timeline Track
  if (events && events.length > 0) {
    events.forEach(e => {
      const eStart = parseFloat(e.start || 0);
      const eEnd = parseFloat(e.end || eStart + 1);
      const segDur = Math.max(0.5, eEnd - eStart);
      const pct = Math.max(1.5, (segDur / dur) * 100);

      const el = document.createElement('div');
      el.className = 'event-track-seg';
      el.style.width = `${pct}%`;
      el.style.backgroundColor = e.color || '#38bdf8';
      el.title = `${e.interval_formatted} — ${e.category}: ${e.description} (${e.confidence_pct})`;

      el.addEventListener('click', () => {
        seekTo(eStart);
        switchTab('events-tab');
      });

      eventsTrack.appendChild(el);
    });
  } else {
    eventsTrack.innerHTML = `<span style="font-size:0.7rem; color:var(--text-muted); padding-left:8px;">No temporal events detected</span>`;
  }

  // Render Anomalies on Anomaly Timeline Track
  if (anomalies && anomalies.length > 0) {
    anomalies.forEach(a => {
      const aStart = parseFloat(a.timestamp || 0);
      const aEnd = parseFloat(a.end_timestamp || aStart + 1);
      const aDur = Math.max(0.5, aEnd - aStart);
      const leftPct = (aStart / dur) * 100;
      const widthPct = Math.max(2.0, (aDur / dur) * 100);

      const el = document.createElement('div');
      el.className = 'anomaly-track-seg';
      el.style.position = 'absolute';
      el.style.left = `${leftPct}%`;
      el.style.width = `${widthPct}%`;
      el.style.backgroundColor = a.severity === 'High' ? '#f43f5e' : '#fbbf24';
      el.style.height = `${Math.round(a.score * 100)}%`;
      el.title = `⚠ ${a.interval_formatted} — Unusual Activity (Score: ${a.score}): ${a.explanation}`;

      el.addEventListener('click', () => {
        seekTo(aStart);
        switchTab('anomalies-tab');
      });

      anomaliesTrack.appendChild(el);
    });
  } else {
    anomaliesTrack.innerHTML = `<span style="font-size:0.7rem; color:#34d399; padding-left:8px;">✓ All video segments consistent with learned steady-state baseline</span>`;
  }
}

function renderTemporalEvents(events, totalDuration) {
  const container = document.getElementById('temporal-events-container');
  const tabCount = document.getElementById('tab-events-count');
  const statCount = document.getElementById('events-stat-count');
  const statConf = document.getElementById('events-stat-conf');

  if (!container) return;
  container.innerHTML = '';

  const numEvents = events ? events.length : 0;
  if (tabCount) tabCount.innerText = numEvents;
  if (statCount) statCount.innerText = numEvents;

  if (!events || events.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No temporal events detected yet. Processing sequence model...</p>
      </div>
    `;
    return;
  }

  // Compute average confidence
  const confScores = events.map(e => parseFloat(e.confidence || 0.85));
  const avgConf = Math.round((confScores.reduce((a, b) => a + b, 0) / confScores.length) * 100);
  if (statConf) statConf.innerText = `${avgConf}%`;

  events.forEach((ev, idx) => {
    const card = document.createElement('div');
    card.className = 'temporal-event-card';
    card.id = `temporal-event-${ev.id || (idx + 1)}`;

    card.innerHTML = `
      <div class="temporal-card-header">
        <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
          <span class="event-category-badge" style="background:${ev.color}1f; color:${ev.color}; border-color:${ev.color}40;">
            <span>${ev.icon || '⏱️'}</span>
            <span>${escapeHtml(ev.category || 'Event')}</span>
          </span>
          <span class="event-time-pill" onclick="seekTo(${ev.start})" title="Jump to ${ev.interval_formatted}">
            ▶ ${ev.interval_formatted || formatSeconds(ev.start)}
          </span>
        </div>
        <span class="confidence-pill">
          ✓ ${ev.confidence_pct || '90%'} Confidence
        </span>
      </div>
      <h4 class="temporal-card-title">${escapeHtml(ev.title || 'Temporal Event')}</h4>
      <p class="temporal-card-desc">${escapeHtml(ev.description || '')}</p>
      <div class="temporal-card-actions">
        <button class="btn btn-primary btn-sm" onclick="seekTo(${ev.start})">
          ▶ Seek to Moment (${ev.start_formatted})
        </button>
        <button class="btn btn-secondary btn-sm" onclick="askTemporalQuestion('What happened around ${ev.start_formatted}?')">
          💬 Ask About This Event
        </button>
      </div>
    `;

    container.appendChild(card);
  });
}

function renderAnomalies(anomalies, timeline, summary, totalDuration) {
  const container = document.getElementById('anomalies-list-container');
  const gridContainer = document.getElementById('anomaly-timeline-grid');
  const tabCount = document.getElementById('tab-anomalies-count');
  const statCount = document.getElementById('anomaly-stat-count');
  const statPeak = document.getElementById('anomaly-stat-peak');
  const statBase = document.getElementById('anomaly-stat-baseline');
  const statThresh = document.getElementById('anomaly-stat-threshold');

  if (tabCount) tabCount.innerText = (anomalies ? anomalies.length : 0);
  if (statCount) statCount.innerText = (anomalies ? anomalies.length : 0);
  if (statPeak && summary) statPeak.innerText = summary.max_score ? summary.max_score.toFixed(2) : '0.00';
  if (statBase && summary) statBase.innerText = summary.baseline_error ? summary.baseline_error.toFixed(3) : '0.000';
  if (statThresh && summary) statThresh.innerText = summary.threshold ? summary.threshold.toFixed(3) : '0.000';

  // Render Time Slice Grid
  if (gridContainer && timeline && timeline.length > 0) {
    gridContainer.innerHTML = '';
    timeline.forEach(point => {
      const slice = document.createElement('div');
      slice.className = 'timeline-slice-block';
      slice.title = `${point.time_formatted}: ${point.status} (Score: ${point.score}, MSE: ${point.reconstruction_error})`;

      const fill = document.createElement('div');
      fill.className = 'slice-bar-fill';
      const fillHeight = Math.max(15, Math.round(point.score * 100));
      fill.style.height = `${fillHeight}%`;

      if (point.is_anomaly) {
        fill.style.background = point.score >= 0.8 ? '#f43f5e' : '#fbbf24';
      } else {
        fill.style.background = 'rgba(52, 211, 153, 0.4)';
      }

      slice.appendChild(fill);
      slice.addEventListener('click', () => {
        seekTo(point.timestamp);
      });

      gridContainer.appendChild(slice);
    });
  }

  // Render Anomalies Cards List
  if (!container) return;
  container.innerHTML = '';

  if (!anomalies || anomalies.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>✓ No unusual activity or high reconstruction errors detected. Video matches learned steady-state representation.</p>
      </div>
    `;
    return;
  }

  anomalies.forEach((a, idx) => {
    const card = document.createElement('div');
    card.className = 'anomaly-card';

    card.innerHTML = `
      <div class="anomaly-card-header">
        <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
          <span class="severity-pill ${a.severity}">
            <span>⚠</span>
            <span>${a.severity} Deviation</span>
          </span>
          <span class="event-time-pill" onclick="seekTo(${a.timestamp})" title="Seek to ${a.interval_formatted}">
            ⏱️ ${a.interval_formatted}
          </span>
        </div>
        <span class="anomaly-score-badge">Reconstruction Score: ${a.score} (${a.score_pct})</span>
      </div>
      <p class="anomaly-desc">${escapeHtml(a.explanation)}</p>
      <div style="display:flex; gap:0.5rem; align-items:center; margin-top:0.25rem;">
        <button class="btn btn-primary btn-sm" onclick="seekTo(${a.timestamp})">
          ▶ Jump to Anomaly Moment (${a.timestamp_formatted})
        </button>
      </div>
    `;

    container.appendChild(card);
  });
}

function renderEventMCQs(jobId, events) {
  const feed = document.getElementById('event-mcqs-feed');
  if (!feed) return;
  feed.innerHTML = `
    <div style="padding: 1.5rem; text-align: center; color: var(--text-secondary);">
      <div class="loading-spinner" style="margin: 0 auto 0.75rem auto;"></div>
      <p>Grounding interactive MCQs in detected video events...</p>
    </div>
  `;

  if (!jobId) return;

  fetch(`/api/quiz/temporal/${jobId}`)
    .then(res => res.json())
    .then(data => {
      const questions = data.questions || [];
      if (questions.length === 0) {
        feed.innerHTML = `<div class="empty-state"><p>No event MCQs generated yet.</p></div>`;
        return;
      }

      feed.innerHTML = '';
      questions.forEach((q, idx) => {
        const card = document.createElement('div');
        card.className = 'mcq-preview-card';

        const correctLetter = (q.correct_answer || 'A').toUpperCase();
        const letters = ['A', 'B', 'C', 'D'];
        const optsHtml = letters.map(l => {
          const isCorrect = (l === correctLetter);
          const optText = q[`option_${l.toLowerCase()}`] || (q.options ? q.options[l] : '') || '';
          return `
            <div class="mcq-opt-preview-item ${isCorrect ? 'correct' : ''}">
              <span class="mcq-opt-badge">${l}</span>
              <span>${escapeHtml(optText)}</span>
              ${isCorrect ? '<span style="margin-left:auto; color:#34d399; font-weight:700;">✓ Correct</span>' : ''}
            </div>
          `;
        }).join('');

        const timeFmt = q.source_time_fmt || formatSeconds(q.source_timestamp || 0);

        card.innerHTML = `
          <div class="mcq-card-head">
            <span class="mcq-num-pill">Question ${idx + 1}</span>
            <span class="event-time-pill" onclick="seekTo(${q.source_timestamp || 0})">
              ⏱️ Relevant Moment: ${timeFmt}
            </span>
          </div>
          <h4 class="mcq-question-title">${escapeHtml(q.question)}</h4>
          <div class="mcq-opts-list">
            ${optsHtml}
          </div>
          <div class="mcq-explanation-box">
            <span><strong>Explanation:</strong> ${escapeHtml(q.explanation || '')}</span>
            <button class="btn btn-secondary btn-sm" onclick="seekTo(${q.source_timestamp || 0})">
              ▶ Watch Moment (${timeFmt})
            </button>
          </div>
        `;

        feed.appendChild(card);
      });
    })
    .catch(err => {
      feed.innerHTML = `<div class="empty-state"><p>Could not load event MCQs: ${escapeHtml(err.message)}</p></div>`;
    });
}

function askTemporalQuestion(questionText) {
  const input = document.getElementById('qa-question-input');
  if (input) input.value = questionText;
  switchTab('qa-tab');
  const btn = document.getElementById('btn-submit-qa');
  if (btn) btn.click();
}


