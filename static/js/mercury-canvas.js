/**
 * Mercury Command Signature Particle Ripple WebGL Canvas
 * Extracted and adapted directly from mercury.com/command
 * Features scroll-driven ripple propagation, mouse tracking, and theme-adaptive rendering.
 */

(function () {
  'use strict';

  function initMercuryCanvas() {
    const canvas = document.getElementById('mercury-hero-canvas');
    if (!canvas) return;

    const gl = canvas.getContext('webgl', { alpha: true, antialias: true, premultipliedAlpha: false });
    if (!gl) {
      console.warn('WebGL not supported for Mercury hero canvas, falling back to 2D canvas');
      initCanvas2DFallback(canvas);
      return;
    }

    // Vertex shader
    const vsSource = `
      attribute vec2 aOrigin;
      uniform float uElapsed;
      uniform float uScrollP;
      uniform float uWidth;
      uniform float uHeight;
      uniform float uPixelRatio;
      uniform vec2 uRippleCenter;
      uniform float uRippleFrequency;
      uniform float uRippleDecay;

      varying float vAlphaScale;

      const float DOT_RADIUS = 0.95;
      const float MIN_POINT_SIZE = 2.0;
      const float UNCOMPENSATED_MIN_POINT_SIZE = 1.0;
      const float RADIUS_SCALE_MIN = 0.35;
      const float RADIUS_SCALE_MAX = 2.4;
      const float RIPPLE_AMPLITUDE = 22.0;
      const float RIPPLE_SPEED = 0.55;

      void main() {
        vec2 originPx = aOrigin * vec2(uWidth, uHeight);
        vec2 center = uRippleCenter * vec2(uWidth, uHeight);
        vec2 delta = originPx - center;
        float distanceFromCenter = length(delta);

        // Wave modulated by time and scroll progress
        float wave = sin(distanceFromCenter * uRippleFrequency - (uElapsed * RIPPLE_SPEED + uScrollP * 6.28318));
        float attenuated = wave * exp(-distanceFromCenter * uRippleDecay);

        vec2 direction = distanceFromCenter > 0.001 ? delta / distanceFromCenter : vec2(0.0);
        float rampScale = clamp((attenuated + 1.0) * 0.5, 0.0, 1.0);
        float radius = DOT_RADIUS * (RADIUS_SCALE_MIN + rampScale * (RADIUS_SCALE_MAX - RADIUS_SCALE_MIN));

        vec2 point = originPx + direction * attenuated * RIPPLE_AMPLITUDE;

        // Convert to clip space [-1, 1]
        vec2 clipSpace = (point / vec2(uWidth, uHeight)) * 2.0 - 1.0;
        clipSpace.y = -clipSpace.y; // Flip Y for WebGL coordinates

        gl_Position = vec4(clipSpace, 0.0, 1.0);

        float rawPointSize = radius * 2.0 * uPixelRatio;
        float referenceSize = max(UNCOMPENSATED_MIN_POINT_SIZE, rawPointSize);
        float clampedSize = max(MIN_POINT_SIZE, rawPointSize);

        vAlphaScale = (referenceSize * referenceSize) / (clampedSize * clampedSize);
        gl_PointSize = clampedSize;
      }
    `;

    // Fragment shader
    const fsSource = `
      precision highp float;
      uniform vec3 uColor;
      varying float vAlphaScale;

      const float DOT_OPACITY = 0.88;

      void main() {
        vec2 coord = gl_PointCoord - vec2(0.5);
        float distanceFromCenter = length(coord);
        float circleAlpha = 1.0 - smoothstep(0.36, 0.5, distanceFromCenter);

        if (circleAlpha <= 0.0) {
          discard;
        }

        gl_FragColor = vec4(uColor, DOT_OPACITY * vAlphaScale * circleAlpha);
      }
    `;

    function createShader(gl, type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader compile error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    }

    const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);
    if (!vs || !fs) return;

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(program));
      return;
    }

    gl.useProgram(program);

    // Uniform locations
    const uElapsedLoc = gl.getUniformLocation(program, 'uElapsed');
    const uScrollPLoc = gl.getUniformLocation(program, 'uScrollP');
    const uWidthLoc = gl.getUniformLocation(program, 'uWidth');
    const uHeightLoc = gl.getUniformLocation(program, 'uHeight');
    const uPixelRatioLoc = gl.getUniformLocation(program, 'uPixelRatio');
    const uRippleCenterLoc = gl.getUniformLocation(program, 'uRippleCenter');
    const uRippleFrequencyLoc = gl.getUniformLocation(program, 'uRippleFrequency');
    const uRippleDecayLoc = gl.getUniformLocation(program, 'uRippleDecay');
    const uColorLoc = gl.getUniformLocation(program, 'uColor');

    // Generate procedural particle cloud matching Mercury
    const PARTICLE_COUNT = 6500;
    const origins = new Float32Array(PARTICLE_COUNT * 2);

    let seed = 284;
    function rand() {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      let x = rand();
      let y = rand();

      // Density curve bias towards middle and lower center
      if (rand() > 0.3) {
        x = 0.5 + (x - 0.5) * 0.85;
        y = 0.55 + (y - 0.5) * 0.8;
      }

      origins[i * 2] = x;
      origins[i * 2 + 1] = y;
    }

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, origins, gl.STATIC_DRAW);

    const aOriginLoc = gl.getAttribLocation(program, 'aOrigin');
    gl.enableVertexAttribArray(aOriginLoc);
    gl.vertexAttribPointer(aOriginLoc, 2, gl.FLOAT, false, 0, 0);

    // Blending
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    let startTime = performance.now();
    let currentRippleX = 0.5;
    let currentRippleY = 0.5;
    let targetRippleX = 0.5;
    let targetRippleY = 0.5;
    let scrollP = 0;
    let targetScrollP = 0;

    // Scroll listener for wave propagation across all pages (Home, History, Analytics, About)
    function updateScrollProgress() {
      const scrollHeight = Math.max(
        document.body.scrollHeight, document.documentElement.scrollHeight,
        document.body.offsetHeight, document.documentElement.offsetHeight,
        document.body.clientHeight, document.documentElement.clientHeight
      ) - window.innerHeight;
      const currentScroll = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
      targetScrollP = scrollHeight > 0 ? (currentScroll / scrollHeight) * 3.14159 : (currentScroll / 300);
    }

    window.addEventListener('scroll', updateScrollProgress, { passive: true });
    window.addEventListener('wheel', (e) => {
      targetScrollP += (e.deltaY * 0.001);
    }, { passive: true });

    // Mouse interactive ripple center across entire viewport
    window.addEventListener('mousemove', function (e) {
      targetRippleX = Math.max(0.02, Math.min(0.98, e.clientX / window.innerWidth));
      targetRippleY = Math.max(0.02, Math.min(0.98, e.clientY / window.innerHeight));
    }, { passive: true });

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = window.innerWidth;
      const height = window.innerHeight;

      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';

      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(uWidthLoc, width);
      gl.uniform1f(uHeightLoc, height);
      gl.uniform1f(uPixelRatioLoc, dpr);
      updateScrollProgress();
    }

    window.addEventListener('resize', resize);
    resize();

    // Canvas container fade in
    const canvasWrap = canvas.closest('[data-hero-canvas-wrap]');
    if (canvasWrap) {
      canvasWrap.style.opacity = '1';
    }

    // Set constant uniforms
    gl.uniform1f(uRippleFrequencyLoc, 0.038);
    gl.uniform1f(uRippleDecayLoc, 0.0016);

    let curR = 225 / 255;
    let curG = 226 / 255;
    let curB = 242 / 255;

    let animId;
    function render(now) {
      animId = requestAnimationFrame(render);
      const elapsed = (now - startTime) / 1000;

      // Smooth lerp to mouse position & scroll
      currentRippleX += (targetRippleX - currentRippleX) * 0.04;
      currentRippleY += (targetRippleY - currentRippleY) * 0.04;
      scrollP += (targetScrollP - scrollP) * 0.08;

      // Smooth animated color lerp between Dark & Light mode
      const isLight = document.documentElement.getAttribute('data-theme') === 'light';
      // In light mode: luminous vibrant indigo; In dark mode: pearlescent off-white
      const targetR = isLight ? (99 / 255) : (225 / 255);
      const targetG = isLight ? (102 / 255) : (226 / 255);
      const targetB = isLight ? (241 / 255) : (242 / 255);

      curR += (targetR - curR) * 0.08;
      curG += (targetG - curG) * 0.08;
      curB += (targetB - curB) * 0.08;

      gl.uniform3f(uColorLoc, curR, curG, curB);

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.uniform1f(uElapsedLoc, elapsed);
      gl.uniform1f(uScrollPLoc, scrollP);
      gl.uniform2f(uRippleCenterLoc, currentRippleX, currentRippleY);

      gl.drawArrays(gl.POINTS, 0, PARTICLE_COUNT);
    }

    animId = requestAnimationFrame(render);
  }

  function initCanvas2DFallback(canvas) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    });

    const dots = Array.from({ length: 400 }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: Math.random() * 1.5 + 0.5,
      alpha: Math.random() * 0.6 + 0.2,
      speed: Math.random() * 0.4 + 0.1
    }));

    function draw() {
      ctx.clearRect(0, 0, width, height);
      const isLight = document.documentElement.getAttribute('data-theme') === 'light';
      ctx.fillStyle = isLight ? 'rgba(99, 102, 241, 0.45)' : 'rgba(221, 221, 229, 0.6)';
      for (const d of dots) {
        d.y -= d.speed;
        if (d.y < 0) d.y = height;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
  }

  // Run on DOM loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMercuryCanvas);
  } else {
    initMercuryCanvas();
  }
})();
