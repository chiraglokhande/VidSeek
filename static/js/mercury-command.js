/**
 * Mercury Command Interactive Showcase & UI Controller
 * Powers accordion selection, command preview state switches, ticker animations, and audio/video controls.
 */

(function () {
  'use strict';

  const showcaseData = [
    {
      id: 'insights',
      prompt: 'Show lecture structure and topic boundaries for Java Programming',
      title: 'Topic Boundaries & Semantic Cohesion',
      actionLabel: 'View in Theater',
      actionTarget: 'theater',
      contentHtml: `
        <div class="flex flex-col gap-s12 p-s16 h-full justify-between">
          <div class="flex items-center justify-between text-sm">
            <span class="text-text-subdued font-mono">Semantic TextTiling Dips</span>
            <span class="badge-pill bg-purple-magic-400-alpha-3 text-purple-base-200">4 Topics Detected</span>
          </div>
          <div class="grid grid-cols-4 gap-s8 py-s12">
            <div class="flex flex-col gap-s4 p-s12 rounded-xl bg-surface-default border border-border-frosted">
              <span class="text-xs text-text-subdued font-mono">00:00</span>
              <span class="text-sm font-medium text-text-default truncate">Intro to Java</span>
              <span class="text-xs text-emerald-400">98% confidence</span>
            </div>
            <div class="flex flex-col gap-s4 p-s12 rounded-xl bg-surface-default border border-border-frosted">
              <span class="text-xs text-text-subdued font-mono">00:15</span>
              <span class="text-sm font-medium text-text-default truncate">Variables & Data</span>
              <span class="text-xs text-emerald-400">95% confidence</span>
            </div>
            <div class="flex flex-col gap-s4 p-s12 rounded-xl bg-surface-default border border-border-frosted">
              <span class="text-xs text-text-subdued font-mono">00:26</span>
              <span class="text-sm font-medium text-text-default truncate">Control Flow</span>
              <span class="text-xs text-emerald-400">92% confidence</span>
            </div>
            <div class="flex flex-col gap-s4 p-s12 rounded-xl bg-surface-default border border-border-frosted">
              <span class="text-xs text-text-subdued font-mono">00:35</span>
              <span class="text-sm font-medium text-text-default truncate">Methods & Returns</span>
              <span class="text-xs text-emerald-400">97% confidence</span>
            </div>
          </div>
          <div class="flex items-center justify-between pt-s8 border-t border-border-frosted text-xs text-text-subdued">
            <span>Audio: 16kHz PCM mono</span>
            <span>Segmentation: FFmpeg fast copy</span>
          </div>
        </div>
      `
    },
    {
      id: 'chapters',
      prompt: 'Divide this 42-minute video into topic-wise clips and generate thumbnails',
      title: 'Lossless FFmpeg Video Slices',
      actionLabel: 'Explore Chapters',
      actionTarget: 'chapters-tab',
      contentHtml: `
        <div class="flex flex-col gap-s12 p-s16 h-full justify-between">
          <div class="flex items-center justify-between text-sm">
            <span class="text-text-subdued font-mono">Output: MP4 Stream-Copy</span>
            <span class="badge-pill bg-blue-magic-400-alpha-3 text-blue-base-200">Zero Re-encoding Loss</span>
          </div>
          <div class="grid grid-cols-2 gap-s12 py-s8">
            <div class="flex items-center gap-s12 p-s12 rounded-xl bg-surface-default border border-border-frosted hover:border-purple-base-500 transition-colors">
              <div class="w-16 h-12 rounded-lg bg-neutral-base-800 flex items-center justify-center text-text-subdued">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              </div>
              <div class="flex flex-col min-w-0">
                <span class="text-sm font-medium text-text-default truncate">Part 1: Overview</span>
                <span class="text-xs text-text-subdued font-mono">00:00 - 00:15 • 15s</span>
              </div>
            </div>
            <div class="flex items-center gap-s12 p-s12 rounded-xl bg-surface-default border border-border-frosted hover:border-purple-base-500 transition-colors">
              <div class="w-16 h-12 rounded-lg bg-neutral-base-800 flex items-center justify-center text-text-subdued">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              </div>
              <div class="flex flex-col min-w-0">
                <span class="text-sm font-medium text-text-default truncate">Part 2: Variables</span>
                <span class="text-xs text-text-subdued font-mono">00:15 - 00:26 • 11s</span>
              </div>
            </div>
          </div>
          <div class="flex items-center justify-between pt-s8 border-t border-border-frosted text-xs text-text-subdued">
            <span>Ready for instant download</span>
            <span class="text-emerald-400">✓ 4 standalone clips ready</span>
          </div>
        </div>
      `
    },
    {
      id: 'qa',
      prompt: 'Where does the instructor explain the difference between for-loop and while-loop?',
      title: 'Timestamp Citation & Q&A Jump',
      actionLabel: 'Ask Video Question',
      actionTarget: 'qa-tab',
      contentHtml: `
        <div class="flex flex-col gap-s12 p-s16 h-full justify-between">
          <div class="flex items-center justify-between text-sm">
            <span class="text-text-subdued font-mono">Grounded Video Citation</span>
            <span class="badge-pill bg-purple-magic-400-alpha-3 text-purple-base-200">Exact Match</span>
          </div>
          <div class="p-s12 rounded-xl bg-surface-default border border-border-frosted flex flex-col gap-s8">
            <div class="flex items-center gap-s8">
              <span class="inline-flex items-center px-s8 py-s2 rounded-md bg-purple-base-600/30 text-purple-base-200 text-xs font-mono font-semibold">00:28</span>
              <span class="text-xs text-text-subdued">Topic: Control Flow & Iteration</span>
            </div>
            <p class="text-sm text-text-default leading-relaxed">
              "For loops are used when the number of iterations is known beforehand, whereas while loops continue executing until a dynamic condition evaluates to false."
            </p>
          </div>
          <div class="flex items-center justify-between pt-s8 border-t border-border-frosted text-xs text-text-subdued">
            <span>Confidence: 99.2%</span>
            <span class="text-purple-magic-400 font-medium">Click timestamp to seek video</span>
          </div>
        </div>
      `
    },
    {
      id: 'quiz',
      prompt: 'Create a 5-question mastery quiz for Topic 2 and generate summary notes',
      title: 'Automated Concept Quiz & Flashcards',
      actionLabel: 'Take Lecture Quiz',
      actionTarget: 'quiz-modal',
      contentHtml: `
        <div class="flex flex-col gap-s12 p-s16 h-full justify-between">
          <div class="flex items-center justify-between text-sm">
            <span class="text-text-subdued font-mono">Lecture Mastery Assessment</span>
            <span class="badge-pill bg-orange-magic-400-alpha-3 text-orange-base-200">Question 1 of 5</span>
          </div>
          <div class="flex flex-col gap-s8 py-s4">
            <p class="text-sm font-medium text-text-default">Which keyword in Java is used to declare a variable whose value cannot be altered?</p>
            <div class="grid grid-cols-2 gap-s8 pt-s4">
              <div class="px-s12 py-s8 rounded-lg bg-surface-default border border-border-frosted text-xs text-text-subdued">A. static</div>
              <div class="px-s12 py-s8 rounded-lg bg-purple-magic-400-alpha-3 border border-purple-base-500 text-xs text-purple-base-200 font-medium">B. final ✓</div>
              <div class="px-s12 py-s8 rounded-lg bg-surface-default border border-border-frosted text-xs text-text-subdued">C. const</div>
              <div class="px-s12 py-s8 rounded-lg bg-surface-default border border-border-frosted text-xs text-text-subdued">D. immutable</div>
            </div>
          </div>
          <div class="flex items-center justify-between pt-s8 border-t border-border-frosted text-xs text-text-subdued">
            <span class="text-emerald-400 font-medium">+15 Mastery Points</span>
            <span>Instant explanation video jump available</span>
          </div>
        </div>
      `
    }
  ];

  function setupAccordion() {
    const accordionButtons = document.querySelectorAll('[data-command-accordion-btn]');
    const promptBubble = document.getElementById('command-preview-prompt-text');
    const cardTitle = document.getElementById('command-preview-card-title');
    const cardContent = document.getElementById('command-preview-content');
    const actionBtn = document.getElementById('command-preview-action-btn');
    const cardContainer = document.getElementById('command-preview-card');

    if (!accordionButtons.length || !promptBubble || !cardContent) return;

    let activeIndex = 0;

    function selectTab(index, userClick = false) {
      if (index < 0 || index >= showcaseData.length) return;
      activeIndex = index;
      const data = showcaseData[index];

      // Update buttons state
      accordionButtons.forEach((btn, idx) => {
        const itemWrap = btn.closest('[data-command-accordion-item]');
        const icon = btn.querySelector('.command-acc-icon');
        const content = itemWrap ? itemWrap.querySelector('[data-command-accordion-content]') : null;

        if (idx === index) {
          btn.setAttribute('data-state', 'open');
          if (itemWrap) itemWrap.setAttribute('data-state', 'open');
          if (content) {
            content.style.maxHeight = content.scrollHeight + 'px';
            content.style.opacity = '1';
          }
          if (icon) icon.classList.add('rotate-45');
        } else {
          btn.setAttribute('data-state', 'closed');
          if (itemWrap) itemWrap.setAttribute('data-state', 'closed');
          if (content) {
            content.style.maxHeight = '0px';
            content.style.opacity = '0';
          }
          if (icon) icon.classList.remove('rotate-45');
        }
      });

      // Animate card content out and in
      if (cardContainer) {
        cardContainer.style.animation = 'none';
        void cardContainer.offsetHeight; // trigger reflow
        cardContainer.style.animation = 'command-asset-child-enter 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards';
      }

      promptBubble.textContent = data.prompt;
      if (cardTitle) cardTitle.textContent = data.title;
      cardContent.innerHTML = data.contentHtml;
      if (actionBtn) {
        actionBtn.innerHTML = `<span>${data.actionLabel}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
        actionBtn.onclick = function (e) {
          e.preventDefault();
          handlePreviewAction(data.actionTarget);
        };
      }
    }

    accordionButtons.forEach((btn, idx) => {
      btn.addEventListener('click', () => {
        selectTab(idx, true);
      });
    });

    // Initialize first tab
    selectTab(0);
  }

  function handlePreviewAction(target) {
    if (target === 'theater') {
      const sampleBtn = document.getElementById('btn-load-sample');
      if (sampleBtn) sampleBtn.click();
    } else if (target === 'quiz-modal') {
      const quizBtn = document.getElementById('btn-open-full-quiz');
      if (quizBtn && !quizBtn.disabled) {
        quizBtn.click();
      } else {
        const sampleBtn = document.getElementById('btn-load-sample');
        if (sampleBtn) sampleBtn.click();
      }
    } else {
      const sampleBtn = document.getElementById('btn-load-sample');
      if (sampleBtn) sampleBtn.click();
      setTimeout(() => {
        const tabBtn = document.querySelector(`[data-tab="${target}"]`);
        if (tabBtn) tabBtn.click();
      }, 1000);
    }
  }

  function setupMarquee() {
    // Smooth infinite marquee ticker
    const marqueeTrack = document.getElementById('mercury-marquee-track');
    if (!marqueeTrack) return;

    // Clone child elements for seamless infinite loop
    const clone = marqueeTrack.cloneNode(true);
    clone.setAttribute('aria-hidden', 'true');
    marqueeTrack.parentElement.appendChild(clone);
  }

  function setupPromptEnhancements() {
    const input = document.getElementById('video-url-input');
    const heroInput = document.getElementById('mercury-hero-command-input');
    const executeBtn = document.getElementById('btn-mercury-execute-command');

    if (heroInput && input && executeBtn) {
      executeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const val = heroInput.value.trim();
        if (val) {
          input.value = val;
          const procBtn = document.getElementById('btn-process-url');
          if (procBtn) procBtn.click();
        } else {
          // If empty, trigger sample demo
          const sampleBtn = document.getElementById('btn-load-sample');
          if (sampleBtn) sampleBtn.click();
        }
      });

      heroInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          executeBtn.click();
        }
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    setupAccordion();
    setupMarquee();
    setupPromptEnhancements();
  });
})();
