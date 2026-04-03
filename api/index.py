from flask import Flask, render_template, request, jsonify
import re
import os

# Fix paths for Vercel serverless environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

VALID_COMMANDS = {"moveright", "moveleft", "jump", "wait", "spin", "dash", "glow", "float"}

pattern_move  = re.compile(r'move(Right|Left)\((\d+)\)', re.IGNORECASE)
pattern_jump  = re.compile(r'jump\(\)', re.IGNORECASE)
pattern_wait  = re.compile(r'wait\((\d+)\)', re.IGNORECASE)
pattern_spin  = re.compile(r'spin\(\)', re.IGNORECASE)
pattern_dash  = re.compile(r'dash\(\)', re.IGNORECASE)
pattern_glow  = re.compile(r'glow\(\)', re.IGNORECASE)
pattern_float = re.compile(r'float\(\)', re.IGNORECASE)


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

            actions.append({
                "type": "move",
                "direction": direction.lower(),
                "steps": int(steps)
            })

        elif pattern_jump.match(line):

            actions.append({"type": "jump"})

        elif match := pattern_wait.match(line):

            actions.append({
                "type": "wait",
                "time": int(match.group(1))
            })

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

    code = request.get_json().get('code', '')
    lines = [l.strip() for l in code.strip().split('\n') if l.strip()]

    token_pattern = re.compile(r'([a-zA-Z_]\w*)|(\d+)|([();,])')

    tokens = []
    errors = []

    for line in lines:

        line_tokens = []

        for m in token_pattern.finditer(line):

            val = m.group()

            if m.group(1):
                kind = "KEYWORD" if val.lower() in VALID_COMMANDS else "IDENTIFIER"
            elif m.group(2):
                kind = "NUMBER"
            else:
                kind = "PUNCTUATION"

            line_tokens.append({"value": val, "type": kind})

        tokens.append({"line": line, "tokens": line_tokens})

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

    semantic = []

    for node in parse_tree:

        line = node["statement"]

        info = {"statement": line, "ok": node["valid"], "note": ""}

        if not node["valid"]:
            info["note"] = "Unknown command — not in symbol table"

        else:

            if m := pattern_move.match(line):
                steps = int(m.group(2))
                info["note"] = f"move({m.group(1)}, steps={steps}) — type: void"

            elif pattern_jump.match(line):
                info["note"] = "jump() — type: void"

            elif (wm := pattern_wait.match(line)):
                info["note"] = f"wait({wm.group(1)}s) — type: void"

            else:
                info["note"] = "Command recognised — type: void"

        semantic.append(info)

    # -------- IR --------

    ir = []

    for node in parse_tree:

        if not node["valid"]:
            ir.append(f"; ERROR: {node['statement']}")
            continue

        line = node["statement"]

        if m := pattern_move.match(line):
            ir.append(f"MOVE {m.group(1).upper()}, {m.group(2)}")

        elif pattern_jump.match(line):
            ir.append("JUMP 60")

        elif wm := pattern_wait.match(line):
            ir.append(f"WAIT {wm.group(1)}")

        elif pattern_spin.match(line):
            ir.append("ROTATE 360")

        elif pattern_dash.match(line):
            ir.append("MOVE RIGHT, 80")

        elif pattern_glow.match(line):
            ir.append("EFFECT GLOW")

        elif pattern_float.match(line):
            ir.append("EFFECT FLOAT")

    # -------- Optimisation --------

    optimised = []
    i = 0

    while i < len(ir):

        if ir[i].startswith("MOVE") and i+1 < len(ir) and ir[i+1].startswith("MOVE"):

            a = ir[i].split()
            b = ir[i+1].split()

            if a[1] == b[1]:

                merged = f"MOVE {a[1]} {int(a[2].rstrip(',')) + int(b[2].rstrip(','))}"

                optimised.append(merged)
                i += 2
                continue

        if ir[i] == "WAIT 0":
            optimised.append("; WAIT 0 removed")
            i += 1
            continue

        optimised.append(ir[i])
        i += 1

    # -------- Codegen --------

    codegen = []

    for instr in optimised:

        if instr.startswith(";"):
            codegen.append({"asm": instr, "note": "optimised away"})
            continue

        parts = instr.split()
        op = parts[0]

        if op == "MOVE":
            codegen.append({"asm": instr, "note": f"frog move {parts[1]} {parts[2]}px"})

        elif op == "JUMP":
            codegen.append({"asm": instr, "note": "frog jump 60px"})

        elif op == "WAIT":
            codegen.append({"asm": instr, "note": f"delay {parts[1]}s"})

        elif op == "ROTATE":
            codegen.append({"asm": instr, "note": "rotate animation"})

        elif op == "EFFECT":
            codegen.append({"asm": instr, "note": f"effect {parts[1]}"})

        else:
            codegen.append({"asm": instr, "note": ""})

    return jsonify({
        "phase1_lexer": tokens,
        "phase2_parser": parse_tree,
        "phase3_semantic": semantic,
        "phase4_ir": ir,
        "phase5_optimised": optimised,
        "phase6_codegen": codegen,
        "errors": errors
    })

# Local run (ignored by Vercel)
if __name__ == "__main__":
    app.run(debug=True)