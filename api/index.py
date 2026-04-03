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

            line_tokens.append({
                "value": val,
                "type": kind
            })

        tokens.append({
            "line": line,
            "tokens": line_tokens
        })

    parse_tree = []

    for entry in tokens:

        line = entry["line"]

        node = {
            "statement": line,
            "valid": False,
            "structure": ""
        }

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

        info = {
            "statement": line,
            "ok": node["valid"],
            "note": ""
        }

        if not node["valid"]:

            info["note"] = "Unknown command — not in symbol table"

        else:

            m = pattern_move.match(line)

            if m:

                steps = int(m.group(2))

                info["note"] = f"move({m.group(1)}, steps={steps}) — type: void, args valid"

            elif pattern_jump.match(line):

                info["note"] = "jump() — type: void"

            elif (wm := pattern_wait.match(line)):

                t = int(wm.group(1))

                info["note"] = f"wait({t}s) — type: void"

            else:

                info["note"] = "Command recognised — type: void"

        semantic.append(info)

    return jsonify({
        "phase1_lexer": tokens,
        "phase2_parser": parse_tree,
        "phase3_semantic": semantic,
        "errors": errors
    })


# Local run (ignored by Vercel)
if __name__ == "__main__":
    app.run(debug=True)