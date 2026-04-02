from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

VALID_COMMANDS = {"moveright", "moveleft", "jump", "wait", "spin", "dash", "glow", "float"}

pattern_move  = re.compile(r'move(Right|Left)\((\d+)\)', re.IGNORECASE)
pattern_jump  = re.compile(r'jump\(\)',                  re.IGNORECASE)
pattern_wait  = re.compile(r'wait\((\d+)\)',             re.IGNORECASE)
pattern_spin  = re.compile(r'spin\(\)',                  re.IGNORECASE)
pattern_dash  = re.compile(r'dash\(\)',                  re.IGNORECASE)
pattern_glow  = re.compile(r'glow\(\)',                  re.IGNORECASE)
pattern_float = re.compile(r'float\(\)',                 re.IGNORECASE)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run():
    code = request.get_json().get('code', '')
    lines = code.strip().split(';')
    actions = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if match := pattern_move.match(line):
            direction, steps = match.groups()
            actions.append({"type": "move", "direction": direction.lower(), "steps": int(steps)})
        elif pattern_jump.match(line):
            actions.append({"type": "jump"})
        elif match := pattern_wait.match(line):
            actions.append({"type": "wait", "time": int(match.group(1))})
        elif pattern_spin.match(line):
            actions.append({"type": "spin"})
        elif pattern_dash.match(line):
            actions.append({"type": "dash"})
        elif pattern_glow.match(line):
            actions.append({"type": "glow"})
        elif pattern_float.match(line):
            actions.append({"type": "float"})
        else:
            return jsonify({"error": f"Invalid command: {line}"})

    return jsonify({"actions": actions})


@app.route('/compile', methods=['POST'])
def compile_phases():
    """Return all 6 compiler phases for the given code."""
    code = request.get_json().get('code', '')
    lines = [l.strip() for l in code.strip().split('\n') if l.strip()]

    # ── Phase 1: Lexical Analysis ─────────────────────────────────────────────
    token_pattern = re.compile(r'([a-zA-Z_]\w*)|(\d+)|([();,])')
    tokens = []
    errors = []
    for line in lines:
        line_tokens = []
        for m in token_pattern.finditer(line):
            val = m.group()
            if m.group(1):   # identifier / keyword
                kind = "KEYWORD" if val.lower() in VALID_COMMANDS else "IDENTIFIER"
            elif m.group(2): kind = "NUMBER"
            else:            kind = "PUNCTUATION"
            line_tokens.append({"value": val, "type": kind})
        tokens.append({"line": line, "tokens": line_tokens})

    # ── Phase 2: Syntax Analysis ──────────────────────────────────────────────
    parse_tree = []
    for entry in tokens:
        line = entry["line"]
        node = {"statement": line, "valid": False, "structure": ""}
        if (pattern_move.match(line) or pattern_jump.match(line) or
                pattern_wait.match(line) or pattern_spin.match(line) or
                pattern_dash.match(line) or pattern_glow.match(line) or
                pattern_float.match(line)):
            node["valid"] = True
            fn = re.match(r'(\w+)\((.*)\)', line)
            if fn:
                node["structure"] = f"FunctionCall → name='{fn.group(1)}' args=[{fn.group(2)}]"
        else:
            node["structure"] = "SyntaxError: unrecognised statement"
            errors.append(line)
        parse_tree.append(node)

    # ── Phase 3: Semantic Analysis ────────────────────────────────────────────
    semantic = []
    for node in parse_tree:
        line = node["statement"]
        info = {"statement": line, "ok": node["valid"], "note": ""}
        if not node["valid"]:
            info["note"] = "Unknown command — not in symbol table"
        else:
            m = pattern_move.match(line)
            if m:
                steps = int(m.group(2))
                info["note"] = f"move({m.group(1)}, steps={steps}) — type: void, args valid" if steps > 0 else "Warning: steps=0 has no effect"
            elif pattern_jump.match(line):
                info["note"] = "jump() — type: void, no args required"
            elif (wm := pattern_wait.match(line)):
                t = int(wm.group(1))
                info["note"] = f"wait({t}s) — type: void" if t > 0 else "Warning: wait(0) has no effect"
            else:
                info["note"] = "Command recognised — type: void"
        semantic.append(info)

    # ── Phase 4: Intermediate Code Generation ────────────────────────────────
    ir = []
    for node in parse_tree:
        if not node["valid"]:
            ir.append(f"; ERROR: {node['statement']}")
            continue
        line = node["statement"]
        if m := pattern_move.match(line):
            d, s = m.group(1).upper(), m.group(2)
            ir.append(f"MOVE {d}, {s}")
        elif pattern_jump.match(line):
            ir.append("JUMP 60")
        elif (wm := pattern_wait.match(line)):
            ir.append(f"WAIT {wm.group(1)}")
        elif pattern_spin.match(line):
            ir.append("ROTATE 360")
        elif pattern_dash.match(line):
            ir.append("MOVE RIGHT, 80")
        elif pattern_glow.match(line):
            ir.append("EFFECT GLOW")
        elif pattern_float.match(line):
            ir.append("EFFECT FLOAT")

    # ── Phase 5: Code Optimisation ────────────────────────────────────────────
    optimised = []
    i = 0
    while i < len(ir):
        # Fold consecutive same-direction MOVEs
        if ir[i].startswith("MOVE") and i + 1 < len(ir) and ir[i + 1].startswith("MOVE"):
            parts_a = ir[i].split()
            parts_b = ir[i + 1].split()
            if len(parts_a) == 3 and len(parts_b) == 3 and parts_a[1] == parts_b[1]:
                merged = f"MOVE {parts_a[1]} {int(parts_a[2].rstrip(',')) + int(parts_b[2].rstrip(','))}  ; folded"
                optimised.append(merged)
                i += 2
                continue
        # Drop WAIT 0
        if ir[i] == "WAIT 0":
            optimised.append("; WAIT 0 removed (no-op)")
            i += 1
            continue
        optimised.append(ir[i])
        i += 1

    # ── Phase 6: Code Generation ──────────────────────────────────────────────
    codegen = []
    for instr in optimised:
        if instr.startswith(";"):
            codegen.append({"asm": instr, "note": "comment / optimised away"})
            continue
        parts = instr.split()
        op = parts[0]
        if op == "MOVE":
            direction = parts[1].rstrip(',')
            amount    = parts[2].rstrip(';').rstrip(',')
            codegen.append({"asm": instr, "note": f"frog.x {'+ ' if direction=='RIGHT' else '- '}{amount}px"})
        elif op == "JUMP":
            codegen.append({"asm": instr, "note": "frog.y -= 60px then restore"})
        elif op == "WAIT":
            codegen.append({"asm": instr, "note": f"setTimeout({parts[1]}000ms)"})
        elif op == "ROTATE":
            codegen.append({"asm": instr, "note": "CSS transform: rotate(360deg)"})
        elif op == "EFFECT":
            fx = parts[1].lower()
            codegen.append({"asm": instr, "note": f"CSS effect: {fx}"})
        else:
            codegen.append({"asm": instr, "note": ""})

    return jsonify({
        "phase1_lexer":    tokens,
        "phase2_parser":   parse_tree,
        "phase3_semantic": semantic,
        "phase4_ir":       ir,
        "phase5_optimised": optimised,
        "phase6_codegen":  codegen,
        "errors":          errors
    })


if __name__ == '__main__':
    app.run(debug=True)
