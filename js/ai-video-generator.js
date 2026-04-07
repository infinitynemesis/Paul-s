/**
 * AI Video Generator Agent
 * A multi-stage pipeline that orchestrates AI-powered video generation.
 */

(function () {
  'use strict';

  // ── State ──
  const state = {
    isGenerating: false,
    isPlaying: false,
    currentStep: -1,
    playbackTime: 0,
    playbackDuration: 30,
    scenes: [],
    script: '',
    sceneImages: [], // {img: HTMLImageElement} per scene when real API used
    audioBlob: null,
    audioUrl: null,
    videoBlob: null,
    projects: JSON.parse(localStorage.getItem('videogen_projects') || '[]'),
    settings: JSON.parse(localStorage.getItem('videogen_settings') || '{}'),
    animationFrame: null,
    playerInterval: null,
  };

  // ── Real API Calls (OpenAI) ──
  // All three keys can be the same OpenAI key, or different keys per service.
  const api = {
    async chat(prompt, key) {
      const res = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${key}`,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [
            {
              role: 'system',
              content:
                'You are a professional video script writer. Respond ONLY with valid JSON (no markdown, no code fences) matching this schema: {"title": string, "scenes": [{"id": number, "type": string, "title": string, "description": string, "duration": number, "narration": string, "visual_prompt": string}]}',
            },
            { role: 'user', content: prompt },
          ],
          temperature: 0.8,
          response_format: { type: 'json_object' },
        }),
      });
      if (!res.ok) throw new Error(`Chat API ${res.status}: ${(await res.text()).slice(0, 200)}`);
      const data = await res.json();
      return JSON.parse(data.choices[0].message.content);
    },

    async image(prompt, key) {
      const res = await fetch('https://api.openai.com/v1/images/generations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${key}`,
        },
        body: JSON.stringify({
          model: 'gpt-image-1',
          prompt: prompt.slice(0, 1000),
          size: '1536x1024',
          n: 1,
        }),
      });
      if (!res.ok) throw new Error(`Image API ${res.status}: ${(await res.text()).slice(0, 200)}`);
      const data = await res.json();
      const b64 = data.data[0].b64_json;
      return 'data:image/png;base64,' + b64;
    },

    async tts(text, key) {
      const res = await fetch('https://api.openai.com/v1/audio/speech', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${key}`,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini-tts',
          voice: 'alloy',
          input: text.slice(0, 4000),
          format: 'mp3',
        }),
      });
      if (!res.ok) throw new Error(`TTS API ${res.status}: ${(await res.text()).slice(0, 200)}`);
      return await res.blob();
    },
  };

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  function isDemoMode() {
    return state.settings.demoMode !== false;
  }

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    generateBtn: $('#generateBtn'),
    promptInput: $('#promptInput'),
    videoDuration: $('#videoDuration'),
    videoStyle: $('#videoStyle'),
    videoResolution: $('#videoResolution'),
    pipelineSection: $('#pipelineSection'),
    previewSection: $('#previewSection'),
    agentLogSection: $('#agentLogSection'),
    logEntries: $('#logEntries'),
    progressFill: $('#progressFill'),
    progressText: $('#progressText'),
    videoCanvas: $('#videoCanvas'),
    playPauseBtn: $('#playPauseBtn'),
    timelineProgress: $('#timelineProgress'),
    playerTime: $('#playerTime'),
    videoDetails: $('#videoDetails'),
    projectsGrid: $('#projectsGrid'),
    demoMode: $('#demoMode'),
    saveSettingsBtn: $('#saveSettingsBtn'),
    statusDot: $('.status-dot'),
    agentStatusText: $('.agent-status span:last-child'),
    regenerateBtn: $('#regenerateBtn'),
    downloadBtn: $('#downloadBtn'),
    clearLogBtn: $('#clearLogBtn'),
  };

  // ── Utilities ──
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function timestamp() {
    return new Date().toLocaleTimeString('en-US', { hour12: false });
  }

  function log(msg, type = '') {
    const entry = document.createElement('div');
    entry.className = `log-entry${type ? ' log-' + type : ''}`;
    entry.innerHTML = `<span class="log-time">[${timestamp()}]</span><span class="log-msg">${msg}</span>`;
    dom.logEntries.appendChild(entry);
    dom.logEntries.scrollTop = dom.logEntries.scrollHeight;
  }

  async function typeText(element, text, speed = 12) {
    const cursor = document.createElement('span');
    cursor.className = 'typing-cursor';
    element.appendChild(cursor);
    for (let i = 0; i < text.length; i++) {
      if (text[i] === '\n') {
        element.insertBefore(document.createElement('br'), cursor);
      } else {
        element.insertBefore(document.createTextNode(text[i]), cursor);
      }
      if (i % 3 === 0) await sleep(speed);
    }
    cursor.remove();
  }

  function setStepState(stepId, s) {
    const el = $(`#step-${stepId}`);
    el.classList.remove('active', 'completed', 'error');
    if (s) el.classList.add(s);
    const statusEl = el.querySelector('.step-status');
    if (s === 'active') statusEl.textContent = 'Processing...';
    else if (s === 'completed') statusEl.textContent = 'Completed';
    else if (s === 'error') statusEl.textContent = 'Error';
  }

  function expandStep(stepId) {
    $$('.pipeline-step').forEach((el) => el.classList.remove('expanded'));
    $(`#step-${stepId}`).classList.add('expanded');
  }

  function updateProgress(pct) {
    dom.progressFill.style.width = pct + '%';
    dom.progressText.textContent = Math.round(pct) + '%';
  }

  function setAgentStatus(text, processing = false) {
    dom.agentStatusText.textContent = text;
    dom.statusDot.classList.toggle('processing', processing);
  }

  // ── Canvas Drawing Helpers ──
  const colors = {
    cinematic: ['#1a1a2e', '#16213e', '#0f3460', '#e94560'],
    animated: ['#6c5ce7', '#a29bfe', '#fd79a8', '#ffeaa7'],
    documentary: ['#2d3436', '#636e72', '#b2bec3', '#dfe6e9'],
    commercial: ['#00b894', '#00cec9', '#0984e3', '#6c5ce7'],
    educational: ['#fdcb6e', '#e17055', '#d63031', '#e84393'],
    'social-media': ['#fd79a8', '#e84393', '#6c5ce7', '#a29bfe'],
  };

  function drawSceneFrame(ctx, w, h, sceneData, t) {
    const palette = colors[sceneData.style] || colors.animated;

    // Background gradient
    const grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, palette[0]);
    grad.addColorStop(1, palette[1]);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Animated shapes
    const time = t || Date.now() / 1000;
    for (let i = 0; i < sceneData.elements; i++) {
      const seed = sceneData.seed + i * 137;
      const x = ((Math.sin(time * 0.5 + seed) + 1) / 2) * w;
      const y = ((Math.cos(time * 0.3 + seed * 0.7) + 1) / 2) * h;
      const size = 20 + (seed % 80);
      const alpha = 0.15 + (seed % 30) / 100;

      ctx.fillStyle =
        palette[(i + 2) % palette.length] +
        Math.round(alpha * 255)
          .toString(16)
          .padStart(2, '0');

      if (i % 3 === 0) {
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
      } else if (i % 3 === 1) {
        ctx.fillRect(x - size / 2, y - size / 2, size, size);
      } else {
        ctx.beginPath();
        ctx.moveTo(x, y - size);
        ctx.lineTo(x + size, y + size);
        ctx.lineTo(x - size, y + size);
        ctx.closePath();
        ctx.fill();
      }
    }

    // Scene title
    if (sceneData.title) {
      ctx.fillStyle = 'rgba(0,0,0,0.5)';
      ctx.fillRect(0, h - 60, w, 60);
      ctx.fillStyle = '#ffffff';
      ctx.font = `bold ${Math.max(14, w / 30)}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText(sceneData.title, w / 2, h - 25);
    }
  }

  function drawWaveform(canvas) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = '#7c5cfc';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let x = 0; x < w; x++) {
      const y =
        h / 2 +
        Math.sin(x * 0.05) * (h / 4) * Math.sin(x * 0.01) +
        Math.sin(x * 0.13) * (h / 6);
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // ── Demo Script Data ──
  function generateScript(prompt, style, duration) {
    const numScenes = Math.max(3, Math.floor(duration / 10));
    const topics = prompt.split(/[,.]/).filter((t) => t.trim().length > 3);
    const mainTopic = topics[0] || prompt;

    const script = {
      title: `Video: ${mainTopic.trim().substring(0, 50)}`,
      narrator: 'Professional Voiceover',
      scenes: [],
    };

    const sceneTypes = [
      'Introduction',
      'Key Concept',
      'Deep Dive',
      'Demonstration',
      'Summary',
      'Call to Action',
    ];

    for (let i = 0; i < numScenes; i++) {
      script.scenes.push({
        id: i + 1,
        type: sceneTypes[i % sceneTypes.length],
        title: `Scene ${i + 1}: ${sceneTypes[i % sceneTypes.length]}`,
        description: `Visuals depicting ${mainTopic.trim()} - ${sceneTypes[i % sceneTypes.length].toLowerCase()} segment with ${style} style elements.`,
        duration: Math.round(duration / numScenes),
        narration: `This segment covers the ${sceneTypes[i % sceneTypes.length].toLowerCase()} aspects of ${mainTopic.trim().substring(0, 30)}.`,
        style: style,
        elements: 5 + Math.floor(Math.random() * 10),
        seed: Math.floor(Math.random() * 10000),
      });
    }

    return script;
  }

  // ── Pipeline Steps ──
  async function runPipeline(prompt, duration, style, resolution) {
    state.isGenerating = true;
    dom.generateBtn.disabled = true;
    dom.pipelineSection.style.display = '';
    dom.agentLogSection.style.display = '';
    dom.previewSection.style.display = 'none';
    dom.logEntries.innerHTML = '';

    setAgentStatus('Processing...', true);
    log('Agent initialized. Starting video generation pipeline.', 'info');
    log(`Prompt: "${prompt.substring(0, 80)}..."`, 'info');
    log(`Config: ${duration}s, ${style}, ${resolution}`, 'info');

    state.playbackDuration = parseInt(duration);

    const steps = ['script', 'storyboard', 'scenes', 'audio', 'assembly'];

    try {
      for (let i = 0; i < steps.length; i++) {
        state.currentStep = i;
        updateProgress((i / steps.length) * 100);
        setStepState(steps[i], 'active');
        expandStep(steps[i]);

        switch (steps[i]) {
          case 'script':
            await stepScript(prompt, style, duration);
            break;
          case 'storyboard':
            await stepStoryboard();
            break;
          case 'scenes':
            await stepScenes(style);
            break;
          case 'audio':
            await stepAudio();
            break;
          case 'assembly':
            await stepAssembly(resolution);
            break;
        }

        setStepState(steps[i], 'completed');
      }

      updateProgress(100);
      log('Pipeline completed successfully!', 'success');
      setAgentStatus('Agent Ready');

      showPreview(duration, style, resolution);
      saveProject(prompt, duration, style, resolution);
    } catch (err) {
      log(`Error: ${err.message}`, 'error');
      setStepState(steps[state.currentStep], 'error');
      setAgentStatus('Error');
    } finally {
      state.isGenerating = false;
      dom.generateBtn.disabled = false;
    }
  }

  async function stepScript(prompt, style, duration) {
    log('Generating script from prompt...', 'info');
    const output = $('#scriptOutput');
    output.innerHTML = '';

    let script;
    const key = state.settings.textApiKey;

    if (!isDemoMode() && key) {
      log('Calling OpenAI chat API for script...', 'info');
      try {
        const fullPrompt = `Create a ${duration}-second ${style}-style video script. User request: "${prompt}". Generate ${Math.max(3, Math.floor(duration / 10))} scenes. Each scene must include a vivid visual_prompt suitable for an image generator.`;
        const apiScript = await api.chat(fullPrompt, key);
        // Normalize to internal scene format
        script = {
          title: apiScript.title || `Video: ${prompt.slice(0, 50)}`,
          scenes: (apiScript.scenes || []).map((s, i) => ({
            id: s.id || i + 1,
            type: s.type || 'Scene',
            title: s.title || `Scene ${i + 1}`,
            description: s.description || '',
            duration: s.duration || Math.round(duration / apiScript.scenes.length),
            narration: s.narration || '',
            visual_prompt: s.visual_prompt || s.description || '',
            style,
            elements: 8,
            seed: Math.floor(Math.random() * 10000),
          })),
        };
        log(`Real script received: ${script.scenes.length} scenes`, 'success');
      } catch (e) {
        log(`Script API failed, using demo: ${e.message}`, 'warn');
        script = generateScript(prompt, style, parseInt(duration));
      }
    } else {
      await sleep(800);
      script = generateScript(prompt, style, parseInt(duration));
    }
    state.script = script;

    const text = `Title: ${script.title}\nStyle: ${style}\nDuration: ${duration}s\nScenes: ${script.scenes.length}\n\n` +
      script.scenes.map(
        (s) => `[Scene ${s.id}] ${s.type} (${s.duration}s)\n${s.description}\nNarration: "${s.narration}"`
      ).join('\n\n');

    await typeText(output, text);
    log(`Script generated: ${script.scenes.length} scenes`, 'success');
  }

  async function stepStoryboard() {
    log('Creating storyboard layout...', 'info');
    const output = $('#storyboardOutput');
    output.innerHTML = '';

    await sleep(600);

    let html = '<div class="scene-canvas-grid">';
    for (const scene of state.script.scenes) {
      const canvasId = `storyboard-${scene.id}`;
      html += `<div class="scene-thumb"><canvas id="${canvasId}" width="400" height="225"></canvas><div class="scene-label">${scene.title}</div></div>`;
    }
    html += '</div>';
    output.innerHTML = html;

    // Draw storyboard thumbnails
    for (const scene of state.script.scenes) {
      const canvas = $(`#storyboard-${scene.id}`);
      if (canvas) {
        drawSceneFrame(canvas.getContext('2d'), 400, 225, scene, scene.seed);
      }
      await sleep(400);
    }

    log(`Storyboard created with ${state.script.scenes.length} frames`, 'success');
  }

  async function stepScenes(style) {
    log('Generating scene visuals...', 'info');
    const output = $('#scenesOutput');
    output.innerHTML = '';

    state.scenes = [];
    state.sceneImages = [];

    const key = state.settings.imageApiKey;
    const useReal = !isDemoMode() && key;

    for (const scene of state.script.scenes) {
      const card = document.createElement('div');
      card.className = 'scene-card';
      card.innerHTML = `<h4>${scene.title}</h4><p>${scene.description}</p><p><span class="spinner"></span>${useReal ? 'Calling image API...' : 'Generating frames...'}</p>`;
      output.appendChild(card);

      let img = null;
      if (useReal) {
        try {
          const visual = scene.visual_prompt || scene.description || scene.title;
          const dataUrl = await api.image(`${visual}. Style: ${style}, cinematic, high quality.`, key);
          img = await loadImage(dataUrl);
          log(`Scene ${scene.id} image generated`, 'success');

          // Show thumbnail
          const thumb = document.createElement('img');
          thumb.src = dataUrl;
          thumb.style.cssText = 'width:100%;max-width:400px;border-radius:8px;margin-top:10px;';
          card.appendChild(thumb);
        } catch (e) {
          log(`Scene ${scene.id} image failed: ${e.message}`, 'warn');
        }
      } else {
        await sleep(700);
      }

      state.scenes.push(scene);
      state.sceneImages.push(img);
      card.querySelector('p:nth-of-type(2)').innerHTML =
        `<span style="color:var(--success);">&#10003;</span> ${img ? 'Image generated' : scene.elements + ' procedural frames'}`;
    }

    log(`All ${state.scenes.length} scenes generated`, 'success');
  }

  async function stepAudio() {
    log('Generating voiceover and background audio...', 'info');
    const output = $('#audioOutput');
    output.innerHTML = '';

    // Cleanup prior audio
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioBlob = null;
    state.audioUrl = null;

    const key = state.settings.ttsApiKey;
    const useReal = !isDemoMode() && key;

    if (useReal) {
      const fullText = state.script.scenes.map((s) => s.narration).filter(Boolean).join(' ');
      log('Calling OpenAI TTS API...', 'info');
      try {
        const blob = await api.tts(fullText, key);
        state.audioBlob = blob;
        state.audioUrl = URL.createObjectURL(blob);

        const audio = document.createElement('audio');
        audio.controls = true;
        audio.src = state.audioUrl;
        audio.style.cssText = 'width:100%;margin-top:12px;';
        output.appendChild(audio);
        log('TTS audio generated', 'success');
      } catch (e) {
        log(`TTS failed: ${e.message}`, 'warn');
      }
    } else {
      await sleep(500);
      await typeText(output, 'Synthesizing narrator voiceover...\nAnalyzing speech pacing and timing...\n');
      await sleep(600);
      const waveContainer = document.createElement('div');
      waveContainer.className = 'waveform-container';
      const wCanvas = document.createElement('canvas');
      wCanvas.width = 800;
      wCanvas.height = 60;
      waveContainer.appendChild(wCanvas);
      output.appendChild(waveContainer);
      drawWaveform(wCanvas);
      await sleep(400);
    }

    const info = document.createElement('p');
    info.style.marginTop = '12px';
    info.textContent = `Audio track: ${state.playbackDuration}s narration`;
    output.appendChild(info);

    log('Audio step complete', 'success');
  }

  async function stepAssembly(resolution) {
    log('Assembling final video...', 'info');
    const output = $('#assemblyOutput');
    output.innerHTML = '';

    state.videoBlob = null;

    const canRecord = typeof MediaRecorder !== 'undefined' && dom.videoCanvas.captureStream;

    if (canRecord) {
      try {
        const status = document.createElement('p');
        status.innerHTML = '<span class="spinner"></span>Recording video via MediaRecorder...';
        output.appendChild(status);

        const fps = 30;
        const stream = dom.videoCanvas.captureStream(fps);

        // Mix audio if available
        let audioEl = null;
        if (state.audioUrl) {
          try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const ac = new AudioCtx();
            audioEl = new Audio(state.audioUrl);
            audioEl.crossOrigin = 'anonymous';
            const src = ac.createMediaElementSource(audioEl);
            const dest = ac.createMediaStreamDestination();
            src.connect(dest);
            src.connect(ac.destination);
            dest.stream.getAudioTracks().forEach((t) => stream.addTrack(t));
          } catch (e) {
            log(`Audio mux skipped: ${e.message}`, 'warn');
          }
        }

        const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
          ? 'video/webm;codecs=vp9,opus'
          : 'video/webm';
        const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 4_000_000 });
        const chunks = [];
        recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

        const finished = new Promise((resolve) => (recorder.onstop = resolve));
        recorder.start();
        if (audioEl) audioEl.play().catch(() => {});

        // Render scenes timed to playbackDuration
        const totalMs = state.playbackDuration * 1000;
        const sceneMs = totalMs / state.scenes.length;
        const startedAt = performance.now();

        await new Promise((resolve) => {
          function tick() {
            const elapsed = performance.now() - startedAt;
            if (elapsed >= totalMs) return resolve();
            renderPlayerFrame(elapsed / 1000);
            requestAnimationFrame(tick);
          }
          tick();
        });

        recorder.stop();
        if (audioEl) audioEl.pause();
        await finished;

        state.videoBlob = new Blob(chunks, { type: 'video/webm' });
        status.innerHTML = `<span style="color:var(--success);">&#10003;</span> Video recorded (${(state.videoBlob.size / 1024 / 1024).toFixed(2)} MB)`;
        log(`Video assembled: ${(state.videoBlob.size / 1024 / 1024).toFixed(2)} MB WebM`, 'success');
      } catch (e) {
        log(`Recording failed: ${e.message}`, 'error');
      }
    } else {
      const tasks = [
        'Compositing scene layers...',
        'Applying transitions and effects...',
        'Synchronizing audio tracks...',
        `Encoding at ${resolution}...`,
        'Finalizing output...',
      ];
      for (const task of tasks) {
        const p = document.createElement('p');
        p.innerHTML = `<span class="spinner"></span>${task}`;
        output.appendChild(p);
        await sleep(600);
        p.innerHTML = `<span style="color:var(--success);">&#10003;</span> ${task.replace('...', ' — done')}`;
      }
      log(`Video assembled at ${resolution} (simulated)`, 'success');
    }
  }

  // ── Preview ──
  function showPreview(duration, style, resolution) {
    dom.previewSection.style.display = '';

    const durationNum = parseInt(duration);
    state.playbackTime = 0;
    state.isPlaying = false;
    dom.playerTime.textContent = `0:00 / 0:${String(durationNum).padStart(2, '0')}`;
    dom.timelineProgress.style.width = '0%';
    dom.playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';

    // Draw first frame
    renderPlayerFrame(0);

    // Details
    dom.videoDetails.innerHTML = `
      <div class="detail-item"><span class="detail-label">Duration</span><span class="detail-value">${durationNum}s</span></div>
      <div class="detail-item"><span class="detail-label">Style</span><span class="detail-value">${style}</span></div>
      <div class="detail-item"><span class="detail-label">Resolution</span><span class="detail-value">${resolution}</span></div>
      <div class="detail-item"><span class="detail-label">Scenes</span><span class="detail-value">${state.scenes.length}</span></div>
      <div class="detail-item"><span class="detail-label">Format</span><span class="detail-value">MP4 (H.264)</span></div>
      <div class="detail-item"><span class="detail-label">FPS</span><span class="detail-value">30</span></div>
    `;

    dom.previewSection.scrollIntoView({ behavior: 'smooth' });
  }

  function renderPlayerFrame(time) {
    const ctx = dom.videoCanvas.getContext('2d');
    const w = dom.videoCanvas.width;
    const h = dom.videoCanvas.height;

    if (!state.scenes.length) return;

    // Determine current scene
    const sceneDur = state.playbackDuration / state.scenes.length;
    const sceneIdx = Math.min(
      Math.floor(time / sceneDur),
      state.scenes.length - 1
    );
    const scene = state.scenes[sceneIdx];
    const realImg = state.sceneImages[sceneIdx];

    if (realImg) {
      // Cover-fit the generated image
      const ir = realImg.width / realImg.height;
      const cr = w / h;
      let dw, dh, dx, dy;
      if (ir > cr) {
        dh = h;
        dw = h * ir;
        dx = (w - dw) / 2;
        dy = 0;
      } else {
        dw = w;
        dh = w / ir;
        dx = 0;
        dy = (h - dh) / 2;
      }
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(realImg, dx, dy, dw, dh);

      // Subtle Ken Burns zoom for life
      const sceneDur2 = state.playbackDuration / state.scenes.length;
      const localT = (time % sceneDur2) / sceneDur2;
      const zoom = 1 + localT * 0.05;
      // (zoom is visual flourish; skip transform reset for simplicity)
      void zoom;
    } else {
      drawSceneFrame(ctx, w, h, scene, time);
    }

    // Progress overlay
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillRect(20, 20, 200, 30);
    ctx.fillStyle = '#fff';
    ctx.font = '13px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`Scene ${sceneIdx + 1} / ${state.scenes.length}`, 30, 40);
  }

  function togglePlayback() {
    if (state.isPlaying) {
      pausePlayback();
    } else {
      startPlayback();
    }
  }

  function startPlayback() {
    state.isPlaying = true;
    dom.playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';

    const startReal = Date.now() - state.playbackTime * 1000;

    function frame() {
      if (!state.isPlaying) return;
      const elapsed = (Date.now() - startReal) / 1000;
      if (elapsed >= state.playbackDuration) {
        state.playbackTime = 0;
        pausePlayback();
        return;
      }
      state.playbackTime = elapsed;
      renderPlayerFrame(elapsed);

      const pct = (elapsed / state.playbackDuration) * 100;
      dom.timelineProgress.style.width = pct + '%';

      const mins = Math.floor(elapsed / 60);
      const secs = Math.floor(elapsed % 60);
      const totalMins = Math.floor(state.playbackDuration / 60);
      const totalSecs = state.playbackDuration % 60;
      dom.playerTime.textContent = `${mins}:${String(secs).padStart(2, '0')} / ${totalMins}:${String(totalSecs).padStart(2, '0')}`;

      state.animationFrame = requestAnimationFrame(frame);
    }

    state.animationFrame = requestAnimationFrame(frame);
  }

  function pausePlayback() {
    state.isPlaying = false;
    dom.playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
    if (state.animationFrame) cancelAnimationFrame(state.animationFrame);
  }

  // ── Projects ──
  function saveProject(prompt, duration, style, resolution) {
    const project = {
      id: Date.now(),
      prompt: prompt.substring(0, 100),
      duration,
      style,
      resolution,
      scenes: state.scenes,
      date: new Date().toLocaleDateString(),
    };
    state.projects.unshift(project);
    if (state.projects.length > 20) state.projects.pop();
    localStorage.setItem('videogen_projects', JSON.stringify(state.projects));
    renderProjects();
  }

  function renderProjects() {
    if (!state.projects.length) {
      dom.projectsGrid.innerHTML =
        '<div class="empty-state"><i class="fas fa-film"></i><h3>No projects yet</h3><p>Generate your first video to see it here</p></div>';
      return;
    }
    dom.projectsGrid.innerHTML = state.projects
      .map(
        (p) => `
      <div class="project-card" data-id="${p.id}">
        <div class="project-thumb"><canvas id="proj-${p.id}" width="400" height="225"></canvas></div>
        <div class="project-card-body">
          <h4>${p.prompt}</h4>
          <p>${p.date} &middot; ${p.duration}s &middot; ${p.style} &middot; ${p.resolution}</p>
        </div>
      </div>`
      )
      .join('');

    // Draw thumbnails
    state.projects.forEach((p) => {
      if (p.scenes && p.scenes[0]) {
        const c = $(`#proj-${p.id}`);
        if (c) drawSceneFrame(c.getContext('2d'), 400, 225, p.scenes[0], p.scenes[0].seed);
      }
    });
  }

  // ── Navigation ──
  function switchView(viewName) {
    $$('.view').forEach((v) => v.classList.remove('active'));
    $$('.nav-item').forEach((n) => n.classList.remove('active'));
    $(`#${viewName}View`).classList.add('active');
    $(`.nav-item[data-view="${viewName}"]`).classList.add('active');
  }

  // ── Event Listeners ──
  function init() {
    // Nav
    $$('.nav-item').forEach((btn) =>
      btn.addEventListener('click', () => switchView(btn.dataset.view))
    );

    // Generate
    dom.generateBtn.addEventListener('click', () => {
      const prompt = dom.promptInput.value.trim();
      if (!prompt) {
        dom.promptInput.focus();
        dom.promptInput.style.borderColor = '#fc5c6c';
        setTimeout(() => (dom.promptInput.style.borderColor = ''), 1500);
        return;
      }
      if (state.isGenerating) return;
      runPipeline(
        prompt,
        dom.videoDuration.value,
        dom.videoStyle.value,
        dom.videoResolution.value
      );
    });

    // Pipeline step toggles
    $$('.step-header').forEach((header) =>
      header.addEventListener('click', () => {
        header.closest('.pipeline-step').classList.toggle('expanded');
      })
    );

    // Player
    dom.playPauseBtn.addEventListener('click', togglePlayback);

    // Timeline seek
    $('.timeline-bar').addEventListener('click', (e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      state.playbackTime = pct * state.playbackDuration;
      renderPlayerFrame(state.playbackTime);
      dom.timelineProgress.style.width = pct * 100 + '%';
      if (state.isPlaying) {
        pausePlayback();
        startPlayback();
      }
    });

    // Regenerate
    dom.regenerateBtn.addEventListener('click', () => {
      if (state.isGenerating) return;
      const prompt = dom.promptInput.value.trim();
      if (!prompt) return;
      dom.previewSection.style.display = 'none';
      runPipeline(
        prompt,
        dom.videoDuration.value,
        dom.videoStyle.value,
        dom.videoResolution.value
      );
    });

    // Download (real video if available, otherwise PNG frame)
    dom.downloadBtn.addEventListener('click', () => {
      if (state.videoBlob) {
        const url = URL.createObjectURL(state.videoBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ai-video-${Date.now()}.webm`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        log('Video downloaded', 'success');
      } else {
        dom.videoCanvas.toBlob((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'ai-generated-video-frame.png';
          a.click();
          URL.revokeObjectURL(url);
        });
      }
    });

    // Clear log
    dom.clearLogBtn.addEventListener('click', () => {
      dom.logEntries.innerHTML = '';
    });

    // Save settings
    dom.saveSettingsBtn.addEventListener('click', () => {
      state.settings = {
        textApiKey: $('#textApiKey').value,
        imageApiKey: $('#imageApiKey').value,
        ttsApiKey: $('#ttsApiKey').value,
        demoMode: dom.demoMode.checked,
      };
      localStorage.setItem('videogen_settings', JSON.stringify(state.settings));
      log('Settings saved', 'success');
    });

    // Load settings
    if (state.settings.textApiKey) $('#textApiKey').value = state.settings.textApiKey;
    if (state.settings.imageApiKey) $('#imageApiKey').value = state.settings.imageApiKey;
    if (state.settings.ttsApiKey) $('#ttsApiKey').value = state.settings.ttsApiKey;
    if (state.settings.demoMode !== undefined) dom.demoMode.checked = state.settings.demoMode;

    // Keyboard shortcut
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.ctrlKey) dom.generateBtn.click();
    });

    // Render projects
    renderProjects();
  }

  init();
})();
