const status      = document.getElementById("status");
const codeInput   = document.getElementById("codeInput");
const programOut  = document.getElementById("programOutput");
const traceList   = document.getElementById("traceList");

let activePhase = 0;
let phaseData   = null;

// ── example C program ─────────────────────────────────────────────────────────
const EXAMPLE = `#include <stdio.h>

int main() {
    int x = 10;
    int y = 20;
    int sum = x + y;

    if (sum > 25) {
        printf("Sum is %d\\n", sum);
    }

    int i = 0;
    while (i < 3) {
        printf("i = %d\\n", i);
        i++;
    }

    return 0;
}`;

function loadExample() {
    codeInput.value = EXAMPLE;
}

function clearCode() {
    codeInput.value = "";
    programOut.textContent = "Run your C code to see output here.";
    traceList.innerHTML = "";
    phaseData = null;
    const panel = document.getElementById("phases-panel");
    if (!panel.classList.contains("hidden")) togglePhases();
}

// ── run ───────────────────────────────────────────────────────────────────────
function runCode() {
    const code = codeInput.value.trim();
    if (!code) return;

    status.innerText = "Running...";
    programOut.textContent = "";
    traceList.innerHTML = "";

    // run + compile in parallel
    Promise.all([
        fetch("/run",     { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({code}) }).then(r=>r.json()),
        fetch("/compile", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({code}) }).then(r=>r.json())
    ]).then(([runData, compileData]) => {
        // render execution output
        renderRun(runData);
        // render phases
        phaseData = compileData;
        const panel = document.getElementById("phases-panel");
        if (panel.classList.contains("hidden")) togglePhases();
        renderPhase(activePhase);
        status.innerText = runData.errors && runData.errors.length ? "Errors" : "Done";
    }).catch(err => {
        status.innerText = "Error";
        programOut.textContent = "Request failed: " + err;
    });
}

function renderRun(data) {
    if (data.errors && data.errors.length) {
        programOut.textContent = data.errors.join("\n");
    } else if (data.output && data.output.length) {
        programOut.textContent = data.output.join("\n");
    } else {
        programOut.textContent = "(no output)";
    }

    traceList.innerHTML = "";
    if (data.trace) {
        data.trace.forEach(t => {
            const row = document.createElement("div");
            row.className = "trace-row";
            const vars = Object.entries(t.vars).map(([k,v]) => `${k}=${v}`).join("  ");
            row.innerHTML = `<span class="trace-step">Step ${t.step}</span>`
                          + `<span class="trace-line">Line ${t.line}</span>`
                          + `<span class="trace-note">${esc(t.note)}</span>`
                          + (vars ? `<span class="trace-vars">${esc(vars)}</span>` : "");
            traceList.appendChild(row);
        });
    }
}


// ── compiler phases ───────────────────────────────────────────────────────────
const PHASE_DESCS = [
    "Phase 1 — Lexical Analysis: The C source is scanned character-by-character and broken into tokens: keywords, identifiers, numbers, operators, and punctuation.",
    "Phase 2 — Syntax Analysis: Tokens are matched against C grammar rules to build a parse tree, verifying structural correctness (declarations, control flow, blocks).",
    "Phase 3 — Semantic Analysis: The parse tree is checked for meaning — variable declarations, type compatibility, correct printf format specifiers, and undeclared identifiers.",
    "Phase 4 — Intermediate Code Generation: The validated AST is lowered into a simple 3-address IR (ALLOC, STORE, CALL, IF_FALSE, GOTO) independent of any target machine.",
    "Phase 5 — Code Optimisation: Constant folding, duplicate store elimination, and dead-code removal are applied to produce leaner IR.",
    "Phase 6 — Code Generation: The optimised IR is mapped to x86-style assembly instructions (MOV, ADD, SUB, CMP, JMP, CALL, RET)."
];

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
        content.innerHTML = '<p class="phase-hint">Run your C code to see the compiler phases.</p>';
        return;
    }

    let html = "";

    if (idx === 0) {
        phaseData.phase1_lexer.forEach(entry => {
            html += `<div class="phase-line"><span class="phase-src">${esc(entry.line)}</span><div class="token-row">`;
            entry.tokens.forEach(t => {
                html += `<span class="token token-${t.type.toLowerCase()}">${esc(t.value)}<small>${t.type}</small></span>`;
            });
            html += `</div></div>`;
        });

    } else if (idx === 1) {
        // Parse Tree — recursive visual tree
        if (!phaseData.phase2_tree) {
            html = '<p class="phase-hint">No tree data.</p>';
        } else {
            html = `<div class="parse-tree">${renderTreeNode(phaseData.phase2_tree, true)}</div>`;
        }

    } else if (idx === 2) {
        phaseData.phase3_semantic.forEach(s => {
            const cls = s.ok ? "sem-ok" : "sem-err";
            html += `<div class="sem-row ${cls}">
                <code>${esc(s.statement)}</code>
                <span>${esc(s.note)}</span>
            </div>`;
        });

    } else if (idx === 3) {
        html = `<pre class="ir-block">${phaseData.phase4_ir.map(esc).join("\n")}</pre>`;

    } else if (idx === 4) {
        const orig = phaseData.phase4_ir;
        const opt  = phaseData.phase5_optimised;
        html += `<div class="opt-compare">`;
        html += `<div><strong>Before</strong><pre>${orig.map(esc).join("\n")}</pre></div>`;
        html += `<div><strong>After</strong><pre>${opt.map(l =>
            l.includes("folded") || l.includes("removed") || l.startsWith(";")
                ? `<mark>${esc(l)}</mark>` : esc(l)
        ).join("\n")}</pre></div>`;
        html += `</div>`;

    } else if (idx === 5) {
        phaseData.phase6_codegen.forEach(row => {
            html += `<div class="cg-row">
                <code class="cg-asm">${esc(row.asm)}</code>
                <span class="cg-note">${esc(row.note)}</span>
            </div>`;
        });
    }

    content.innerHTML = html || '<p class="phase-hint">Nothing to show.</p>';
}

// ── parse tree renderer ───────────────────────────────────────────────────────
const NODE_COLOURS = {
    Program:        "#52b788",
    TranslationUnit:"#52b788",
    FunctionDef:    "#2563eb",
    ReturnType:     "#7c3aed",
    ParamList:      "#7c3aed",
    Param:          "#a78bfa",
    Body:           "#64748b",
    VarDecl:        "#0891b2",
    Type:           "#06b6d4",
    Identifier:     "#0ea5e9",
    Assign:         "#d97706",
    Assignment:     "#d97706",
    Op:             "#f59e0b",
    BinaryOp:       "#f59e0b",
    UnaryOp:        "#f59e0b",
    Number:         "#16a34a",
    String:         "#16a34a",
    FormatString:   "#16a34a",
    Expr:           "#64748b",
    IfStatement:    "#dc2626",
    Condition:      "#ef4444",
    ThenBlock:      "#fca5a5",
    ElseClause:     "#dc2626",
    ElseBlock:      "#fca5a5",
    WhileLoop:      "#7c3aed",
    ForLoop:        "#7c3aed",
    ForInit:        "#a78bfa",
    ForUpdate:      "#a78bfa",
    LoopBody:       "#c4b5fd",
    FuncCall:       "#0891b2",
    ReturnStatement:"#dc2626",
    Preprocessor:   "#94a3b8",
    Unknown:        "#ef4444",
};

function renderTreeNode(node, isRoot) {
    const colour = NODE_COLOURS[node.kind] || "#64748b";
    const hasChildren = node.children && node.children.length > 0;
    const childrenHtml = hasChildren
        ? `<div class="tree-children">${node.children.map(c => renderTreeNode(c, false)).join("")}</div>`
        : "";
    return `
        <div class="tree-node-wrap">
            <div class="tree-node" style="--nc:${colour}">
                <span class="tree-kind">${esc(node.kind)}</span>
                <span class="tree-label">${esc(node.label)}</span>
            </div>
            ${childrenHtml}
        </div>`;
}

function esc(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
