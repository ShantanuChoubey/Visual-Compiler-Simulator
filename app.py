from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run():
    code = request.get_json().get('code', '')
    lines = code.strip().split(';')
    actions = []

    # Define regex patterns for commands
    pattern_move = re.compile(r'move(Right|Left)\((\d+)\)', re.IGNORECASE)
    pattern_jump = re.compile(r'jump\(\)', re.IGNORECASE)
    pattern_wait = re.compile(r'wait\((\d+)\)', re.IGNORECASE)
    pattern_spin = re.compile(r'spin\(\)', re.IGNORECASE)
    pattern_dash = re.compile(r'dash\(\)', re.IGNORECASE)
    pattern_glow = re.compile(r'glow\(\)', re.IGNORECASE)
    pattern_float = re.compile(r'float\(\)', re.IGNORECASE)

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

if __name__ == '__main__':
    app.run(debug=True)
