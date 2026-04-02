const frog      = document.getElementById("frog");
const game      = document.getElementById("gameArea");
const status    = document.getElementById("status");
const codeInput = document.getElementById("codeInput");
const tokens    = document.getElementById("tokens");
const parseTree = document.getElementById("parseTree");

let x = 200, y = 300;
let activePhase = 0;
let phaseData   = null;

// ── frog helpers ─────────────────────────────────────────────────────────────
function clamp() {
  x = Math.max(0, Math.min(x, game.clientWidth  - 50));
  y = Math.max(0, Math.min(y, game.clientHeight - 50));
}
function update() { clamp(); frog.style.left = x + "px"; frog.style.top = y + "px"; }

// ── run code (existing workflow untouched) ────────────────────────────────────
function runCode() {
  status.innerText = "Running...";
  tokens.innerText = "";
  parseTree.innerText = "";

  const cmds = codeInput.value.split("\n").filter(l => l.trim());
  let delay = 0;

  cmds.forEach((c, i) => {
    tokens.innerText    += c.replace(/[();]/g, "") + " | ";
    parseTree.innerText += `Command ${i + 1}: ${c}\n`;
    setTimeout(() => exec(c), delay);
    delay += 600;
  });

  setTimeout(() => { status.innerText = "Ready"; }, delay);

  // also fetch compiler phases from backend
  fetchPhases(codeInput.value);
}

function exec(c) {
  if (c.startsWith("moveRight")) x += 40;
  if (c.startsWith("moveLeft"))  x -= 40;
  if (c.startsWith("jump")) {
    y -= 60;
    setTimeout(() => { y += 60; update(); }, 300);
  }
  if (c.startsWith("glow"))  frog.style.filter    = "drop-shadow(0 0 15px lime)";
  if (c.startsWith("spin"))  frog.style.transform = "rotate(360deg)";
  if (c.startsWith("dash"))  x += 80;
  if (c.startsWith("float")) frog.style.transform = "translateY(-20px)";
  setTimeout(() => { frog.style.filter = ""; frog.style.transform = ""; }, 400);
  update();
}

function addCommand(c)    { codeInput.value += c + "\n"; }
function undoLastCommand(){ let l = codeInput.value.trim().split("\n"); l.pop(); codeInput.value = l.join("\n") + "\n"; }
function clearCode()      { codeInput.value = ""; }

update();

// ── compiler phases ───────────────────────────────────────────────────────────
const PHASE_DESCS = [
  "Phase 1 — Lexical Analysis: The source code is broken into the smallest meaningful units called tokens (keywords, numbers, punctuation).",
  "Phase 2 — Syntax Analysis: Tokens are arranged into a parse tree that checks whether the grammar rules are followed.",
  "Phase 3 — Semantic Analysis: The parse tree is checked for meaning — correct argument types, known commands, and logical validity.",
  "Phase 4 — Intermediate Code Generation: The validated code is translated into a simple, machine-independent instruction set (IR).",
  "Phase 5 — Code Optimisation: Redundant or inefficient IR instructions are merged or removed to produce leaner code.",
  "Phase 6 — Code Generation: The optimised IR is mapped to final executable instructions that drive the frog's actions."
];

function fetchPhases(code) {
  fetch("/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code })
  })
  .then(r => r.json())
  .then(data => {
    phaseData = data;
    // auto-open the panel if it's collapsed
    const panel = document.getElementById("phases-panel");
    if (panel.classList.contains("hidden")) togglePhases();
    renderPhase(activePhase);
  })
  .catch(() => {});
}

function togglePhases() {
  const panel = document.getElementById("phases-panel");
  const arrow = document.getElementById("phases-arrow");
  panel.classList.toggle("hidden");
  arrow.textContent = panel.classList.contains("hidden") ? "▼" : "▲";
}

function showPhase(idx) {
  activePhase = idx;
  document.querySelectorAll(".phase-tab").forEach((t, i) =>
    t.classList.toggle("active", i === idx)
  );
  renderPhase(idx);
}

function renderPhase(idx) {
  const desc    = document.getElementById("phase-desc");
  const content = document.getElementById("phase-content");
  desc.textContent = PHASE_DESCS[idx];

  if (!phaseData) {
    content.innerHTML = '<p class="phase-hint">Run your code to see the compiler phases.</p>';
    return;
  }

  let html = "";

  if (idx === 0) {
    // Lexer — token table per line
    phaseData.phase1_lexer.forEach(entry => {
      html += `<div class="phase-line"><span class="phase-src">${esc(entry.line)}</span><div class="token-row">`;
      entry.tokens.forEach(t => {
        html += `<span class="token token-${t.type.toLowerCase()}">${esc(t.value)}<small>${t.type}</small></span>`;
      });
      html += `</div></div>`;
    });

  } else if (idx === 1) {
    // Parser — tree nodes
    phaseData.phase2_parser.forEach(node => {
      const cls = node.valid ? "node-ok" : "node-err";
      html += `<div class="parse-node ${cls}">
        <span class="node-stmt">${esc(node.statement)}</span>
        <span class="node-struct">${esc(node.structure)}</span>
      </div>`;
    });

  } else if (idx === 2) {
    // Semantic
    phaseData.phase3_semantic.forEach(s => {
      const cls = s.ok ? "sem-ok" : "sem-err";
      html += `<div class="sem-row ${cls}">
        <code>${esc(s.statement)}</code>
        <span>${esc(s.note)}</span>
      </div>`;
    });

  } else if (idx === 3) {
    // IR
    html = `<pre class="ir-block">${phaseData.phase4_ir.map(esc).join("\n")}</pre>`;

  } else if (idx === 4) {
    // Optimised
    const orig = phaseData.phase4_ir;
    const opt  = phaseData.phase5_optimised;
    html += `<div class="opt-compare">`;
    html += `<div><strong>Before</strong><pre>${orig.map(esc).join("\n")}</pre></div>`;
    html += `<div><strong>After</strong><pre>${opt.map(l => l.includes("folded") || l.startsWith(";") ? `<mark>${esc(l)}</mark>` : esc(l)).join("\n")}</pre></div>`;
    html += `</div>`;

  } else if (idx === 5) {
    // Codegen
    phaseData.phase6_codegen.forEach(row => {
      html += `<div class="cg-row">
        <code class="cg-asm">${esc(row.asm)}</code>
        <span class="cg-note">${esc(row.note)}</span>
      </div>`;
    });
  }

  content.innerHTML = html || '<p class="phase-hint">Nothing to show.</p>';
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
