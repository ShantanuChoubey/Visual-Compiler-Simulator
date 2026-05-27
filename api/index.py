from flask import Flask, render_template, request, jsonify
import re, os, math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

# ── C keyword / type sets ─────────────────────────────────────────────────────
C_KEYWORDS = {
    "int","float","char","double","long","short","unsigned","signed","void",
    "if","else","while","for","do","return","break","continue","switch","case",
    "default","struct","typedef","sizeof","const","static","extern","include"
}
C_TYPES = {"int","float","char","double","long","short","unsigned","signed","void"}

# ── Lexer ─────────────────────────────────────────────────────────────────────
TOKEN_RE = re.compile(
    r'(?P<COMMENT>//[^\n]*|/\*.*?\*/)'
    r'|(?P<INCLUDE>#\s*include\s*[<"][^>"]*[>"])'   # full #include <...>
    r'|(?P<PREPROC>#\s*\w+(?:\s+\S+)*)'
    r'|(?P<STRING>"(?:[^"\\]|\\.)*")'
    r"|(?P<CHAR>'(?:[^'\\]|\\.)*')"
    r'|(?P<FLOAT>\d+\.\d*|\.\d+)'
    r'|(?P<NUMBER>\d+)'
    r'|(?P<IDENT>[a-zA-Z_]\w*)'
    r'|(?P<OP>&&|\|\||[+\-*/%=<>!&|]{1,2})'
    r'|(?P<PUNCT>[(){}\[\];,.])',
    re.DOTALL
)

def classify(kind, val):
    if kind == "IDENT":
        return "KEYWORD" if val in C_KEYWORDS else "IDENTIFIER"
    if kind in ("INCLUDE", "PREPROC"):
        return "PREPROCESSOR"
    return kind

def lex_line(line):
    toks = []
    for m in TOKEN_RE.finditer(line):
        kind = m.lastgroup
        val  = m.group()
        toks.append({"value": val, "type": classify(kind, val)})
    return toks


# ── C interpreter ─────────────────────────────────────────────────────────────
def interpret_c(code):
    output, trace, errors = [], [], []
    env   = {}
    step  = [0]

    def snap(lineno, note):
        step[0] += 1
        trace.append({"step": step[0], "line": lineno + 1,
                       "vars": dict(env), "note": note})

    def eval_expr(expr):
        expr = expr.strip().rstrip(";")
        def repl(m):
            n = m.group()
            if n in env: return str(env[n])
            if n in C_KEYWORDS: return n
            return n
        safe = re.sub(r'[a-zA-Z_]\w*', repl, expr)
        safe = safe.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
        try:
            return eval(safe, {"__builtins__": {}})
        except Exception:
            return None

    lines = code.split("\n")
    MAX   = 500

    def run_block(stmts, idx):
        """Execute statements[idx:] until we hit an unmatched } or end."""
        while idx < len(stmts) and step[0] < MAX:
            lineno, s = stmts[idx]
            if s is None or s in ("{",):
                idx += 1; continue
            if s == "}":
                return idx + 1

            # skip preprocessor / function signatures (not control flow keywords)
            if s.startswith("#"):
                idx += 1; continue
            if re.match(r'^\w[\w\s\*]*\w\s*\(.*\)\s*\{?$', s) and not re.match(r'^(if|while|for|else)\b', s):
                idx += 1; continue

            # var decl with init
            m = re.match(r'^(?:int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
            if m:
                val = eval_expr(m.group(2))
                if val is not None: env[m.group(1)] = val
                snap(lineno, f"{m.group(1)} = {val}")
                idx += 1; continue

            # bare decl
            m = re.match(r'^(?:int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*;?$', s)
            if m:
                env[m.group(1)] = 0
                snap(lineno, f"{m.group(1)} declared = 0")
                idx += 1; continue

            # ++/--
            m = re.match(r'^([a-zA-Z_]\w*)(\+\+|--).*', s.rstrip(";"))
            if m:
                name, op = m.group(1), m.group(2)
                if name in env:
                    env[name] += 1 if op == "++" else -1
                    snap(lineno, f"{name}{op} → {env[name]}")
                idx += 1; continue

            # compound assign
            m = re.match(r'^([a-zA-Z_]\w*)\s*([+\-*/])=\s*(.+);?$', s)
            if m:
                name, op, expr = m.group(1), m.group(2), m.group(3)
                if name in env:
                    rhs = eval_expr(expr)
                    if rhs is not None:
                        if op=="+": env[name]+=rhs
                        elif op=="-": env[name]-=rhs
                        elif op=="*": env[name]*=rhs
                        elif op=="/": env[name]/=rhs
                        snap(lineno, f"{name} {op}= {rhs} → {env[name]}")
                idx += 1; continue

            # plain assignment
            m = re.match(r'^([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
            if m and not s.startswith("if") and not s.startswith("while"):
                val = eval_expr(m.group(2))
                if val is not None:
                    env[m.group(1)] = val
                    snap(lineno, f"{m.group(1)} = {val}")
                idx += 1; continue

            # printf
            m = re.match(r'^printf\s*\(\s*"([^"]*)"\s*(?:,\s*(.*))?\s*\)\s*;?$', s)
            if m:
                fmt, args_str = m.group(1), m.group(2) or ""
                args = [eval_expr(a.strip()) for a in args_str.split(",") if a.strip()] if args_str else []
                try:
                    result = fmt.replace("\\n","").replace("%d","{:.0f}").replace("%f","{}").replace("%c","{}").replace("%s","{}").replace("%i","{:.0f}")
                    result = result.format(*[a for a in args])
                except Exception:
                    result = fmt
                output.append(result)
                snap(lineno, f'printf → "{result}"')
                idx += 1; continue

            # if
            m = re.match(r'^if\s*\((.+)\)\s*\{?$', s)
            if m:
                cond = eval_expr(m.group(1))
                snap(lineno, f"if ({m.group(1)}) → {bool(cond)}")
                idx += 1
                # find the then-block
                if idx < len(stmts) and stmts[idx][1] in (None, "{"):
                    idx += 1
                if cond:
                    idx = run_block(stmts, idx)
                else:
                    # skip until matching }
                    depth = 1
                    while idx < len(stmts) and depth > 0:
                        _, ss = stmts[idx]
                        if ss:
                            depth += ss.count("{") - ss.count("}")
                        idx += 1
                continue

            # while
            m = re.match(r'^while\s*\((.+)\)\s*\{?$', s)
            if m:
                cond_expr = m.group(1)
                # collect body statements between the braces
                body_stmts = []
                # start AFTER the while line
                scan = idx + 1
                # skip a standalone { line if present
                if scan < len(stmts) and stmts[scan][1] in (None, "{"):
                    scan += 1
                depth = 1
                while scan < len(stmts) and depth > 0:
                    _, ss = stmts[scan]
                    if ss is None:
                        scan += 1; continue
                    if ss == "{": depth += 1
                    elif ss == "}": depth -= 1
                    if depth > 0:
                        body_stmts.append(stmts[scan])
                    scan += 1
                after = scan
                iters = 0
                while eval_expr(cond_expr) and step[0] < MAX and iters < 100:
                    snap(lineno, f"while ({cond_expr}) → True")
                    run_block(body_stmts, 0)
                    iters += 1
                snap(lineno, f"while ({cond_expr}) → False, exit loop")
                idx = after; continue

            # for
            m = re.match(r'^for\s*\((.+);(.+);(.+)\)\s*\{?$', s)
            if m:
                init_s, cond_s, upd_s = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                # execute init
                init_m = re.match(r'^(?:int\s+)?([a-zA-Z_]\w*)\s*=\s*(.+)$', init_s)
                if init_m:
                    val = eval_expr(init_m.group(2))
                    if val is not None: env[init_m.group(1)] = val
                body_start = idx + 1
                if body_start < len(stmts) and stmts[body_start][1] in (None, "{"):
                    body_start += 1
                body_stmts = []
                depth = 1; scan = body_start
                while scan < len(stmts) and depth > 0:
                    _, ss = stmts[scan]
                    if ss == "}": depth -= 1
                    elif ss == "{": depth += 1
                    if depth > 0: body_stmts.append(stmts[scan])
                    scan += 1
                after = scan
                iters = 0
                while eval_expr(cond_s) and step[0] < MAX and iters < 100:
                    snap(lineno, f"for cond ({cond_s}) → True")
                    run_block(body_stmts, 0)
                    # update
                    upd_m = re.match(r'^([a-zA-Z_]\w*)(\+\+|--)$', upd_s)
                    if upd_m:
                        n = upd_m.group(1)
                        if n in env: env[n] += 1 if upd_m.group(2)=="++" else -1
                    iters += 1
                snap(lineno, f"for cond ({cond_s}) → False, exit loop")
                idx = after; continue

            # return
            m = re.match(r'^return\s+(.*);?$', s)
            if m:
                val = eval_expr(m.group(1))
                snap(lineno, f"return {val}")
                return len(stmts)

            snap(lineno, s[:60])
            idx += 1

        return idx

    raw = [(i, l.strip() if l.strip() else None) for i, l in enumerate(lines)]
    stmts = [(i, s) for i, s in raw]
    run_block(stmts, 0)

    if step[0] >= MAX:
        errors.append("Execution stopped: too many steps (possible infinite loop)")

    return output, trace, errors


# ── Parse tree helpers ────────────────────────────────────────────────────────
def make_node(label, kind, children=None):
    return {"label": label, "kind": kind, "children": children or []}

def parse_expr_node(expr):
    expr = expr.strip().rstrip(";")
    if not expr:
        return make_node("", "Expr")
    # binary ops lowest → highest precedence (right-to-left scan)
    for op in ["||", "&&", "==", "!=", "<=", ">=", "<", ">", "+", "-", "*", "/"]:
        depth = 0
        for idx in range(len(expr)-1, -1, -1):
            c = expr[idx]
            if c in ")}]": depth += 1
            elif c in "({[": depth -= 1
            elif depth == 0 and expr[idx:idx+len(op)] == op:
                # make sure it's not part of a longer op
                before = expr[idx-1] if idx > 0 else ""
                if before in "=!<>&|": continue
                left  = expr[:idx].strip()
                right = expr[idx+len(op):].strip()
                if left and right:
                    return make_node(op, "BinaryOp",
                                     [parse_expr_node(left), parse_expr_node(right)])
    # function call
    fc = re.match(r'^([a-zA-Z_]\w*)\s*\((.*)\)$', expr, re.DOTALL)
    if fc:
        args = [parse_expr_node(a.strip()) for a in fc.group(2).split(",") if a.strip()]
        return make_node(fc.group(1)+"()", "FuncCall", args)
    # literals / identifiers
    if re.match(r'^\d+\.?\d*$', expr):
        return make_node(expr, "Number")
    if expr.startswith('"') or expr.startswith("'"):
        return make_node(expr, "String")
    if re.match(r'^[a-zA-Z_]\w*$', expr):
        return make_node(expr, "Identifier")
    return make_node(expr, "Expr")

def parse_stmt_node(s):
    s = s.strip()
    if not s: return None
    if s in ("{","}"): return None

    if re.match(r'^#\s*include', s):
        return make_node(s, "Preprocessor")
    if re.match(r'^#', s):
        return make_node(s, "Preprocessor")

    # function definition
    fn = re.match(r'^((?:int|void|float|char|double)\s+)([a-zA-Z_]\w*)\s*\((.*)\)\s*\{?$', s)
    if fn:
        params = []
        for p in fn.group(3).split(","):
            p = p.strip()
            if not p: continue
            pm = re.match(r'([\w\s\*]+)\s+([a-zA-Z_]\w*)', p)
            if pm:
                params.append(make_node(pm.group(2), "Param",
                    [make_node(pm.group(1).strip(), "Type")]))
            else:
                params.append(make_node(p, "Param"))
        return make_node(f"FunctionDef: {fn.group(2)}", "FunctionDef", [
            make_node(fn.group(1).strip(), "ReturnType"),
            make_node("params", "ParamList", params),
        ])

    # var decl with init
    m = re.match(r'^(int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
    if m:
        return make_node(f"VarDecl: {m.group(2)}", "VarDecl", [
            make_node(m.group(1), "Type"),
            make_node(m.group(2), "Identifier"),
            make_node("=", "Assign", [parse_expr_node(m.group(3).rstrip(";"))])
        ])

    # bare decl
    m = re.match(r'^(int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*;?$', s)
    if m:
        return make_node(f"VarDecl: {m.group(2)}", "VarDecl", [
            make_node(m.group(1), "Type"),
            make_node(m.group(2), "Identifier"),
        ])

    # ++/--
    m = re.match(r'^([a-zA-Z_]\w*)(\+\+|--).*', s.rstrip(";"))
    if m:
        return make_node(f"UnaryOp: {m.group(2)}", "UnaryOp",
                         [make_node(m.group(1), "Identifier")])

    # compound assign
    m = re.match(r'^([a-zA-Z_]\w*)\s*([+\-*/])=\s*(.+);?$', s)
    if m:
        return make_node("CompoundAssign", "Assignment", [
            make_node(m.group(1), "Identifier"),
            make_node(m.group(2)+"=", "Op"),
            parse_expr_node(m.group(3).rstrip(";"))
        ])

    # plain assignment
    m = re.match(r'^([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
    if m and not s.startswith("if") and not s.startswith("while"):
        return make_node("Assignment", "Assignment", [
            make_node(m.group(1), "Identifier"),
            make_node("=", "Op"),
            parse_expr_node(m.group(2).rstrip(";"))
        ])

    # if
    m = re.match(r'^if\s*\((.+)\)', s)
    if m:
        return make_node("IfStatement", "IfStatement", [
            make_node("condition", "Condition", [parse_expr_node(m.group(1))]),
            make_node("then { ... }", "ThenBlock"),
        ])

    # else
    if s.startswith("else"):
        return make_node("ElseClause", "ElseClause",
                         [make_node("else { ... }", "ElseBlock")])

    # while
    m = re.match(r'^while\s*\((.+)\)', s)
    if m:
        return make_node("WhileLoop", "WhileLoop", [
            make_node("condition", "Condition", [parse_expr_node(m.group(1))]),
            make_node("body { ... }", "LoopBody"),
        ])

    # for
    m = re.match(r'^for\s*\((.+);(.+);(.+)\)', s)
    if m:
        return make_node("ForLoop", "ForLoop", [
            make_node("init",      "ForInit",   [parse_expr_node(m.group(1).strip())]),
            make_node("condition", "Condition", [parse_expr_node(m.group(2).strip())]),
            make_node("update",    "ForUpdate", [parse_expr_node(m.group(3).strip())]),
            make_node("body { ... }", "LoopBody"),
        ])

    # printf
    m = re.match(r'^printf\s*\(\s*(".*?")\s*(?:,\s*(.*))?\s*\)\s*;?$', s)
    if m:
        arg_nodes = [make_node(m.group(1), "FormatString")]
        if m.group(2):
            for a in m.group(2).split(","):
                a = a.strip()
                if a: arg_nodes.append(parse_expr_node(a))
        return make_node("FuncCall: printf", "FuncCall", arg_nodes)

    # return
    m = re.match(r'^return\s+(.*);?$', s)
    if m:
        return make_node("ReturnStatement", "ReturnStatement",
                         [parse_expr_node(m.group(1).rstrip(";"))])

    return make_node(s[:50], "Unknown")


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run():
    code = request.get_json().get('code', '')
    out, trace, errs = interpret_c(code)
    return jsonify({"output": out, "trace": trace, "errors": errs})

@app.route('/compile', methods=['POST'])
def compile_phases():
    code     = request.get_json().get('code', '')
    src_lines = code.split('\n')
    errors   = []

    # ── Phase 1: Lexical Analysis ─────────────────────────────────────────
    phase1 = []
    for line in src_lines:
        toks = lex_line(line)
        if toks:
            phase1.append({"line": line, "tokens": toks})

    # ── Phase 2: Syntax Analysis — nested parse tree ──────────────────────
    # Build a flat list of (lineno, stripped) for phases 3/4
    flat = []
    for i, line in enumerate(src_lines):
        s = line.strip()
        if s and not s.startswith("//"):
            flat.append((i, s))

    # Build nested tree: group statements inside { } blocks
    def build_tree(items, pos):
        children = []
        while pos < len(items):
            lineno, s = items[pos]
            if s == "}":
                return children, pos + 1
            node = parse_stmt_node(s)
            pos += 1
            if node is None:
                continue
            # if next line opens a block, recurse
            if pos < len(items) and items[pos][1] == "{":
                pos += 1  # consume {
                block_children, pos = build_tree(items, pos)
                node["children"] = node["children"] + block_children
            children.append(node)
        return children, pos

    top_children, _ = build_tree(flat, 0)
    phase2_tree = make_node("Program", "Program", [
        make_node("TranslationUnit", "TranslationUnit", top_children)
    ])

    # flat list for phases 3/4
    phase2_flat = []
    brace_depth = 0
    for lineno, s in flat:
        brace_depth += s.count("{") - s.count("}")
        node = parse_stmt_node(s)
        valid = node is not None and node["kind"] != "Unknown"
        phase2_flat.append({
            "line": s,
            "valid": valid,
            "structure": node["kind"] if node else "Unknown",
            "depth": max(0, brace_depth)
        })
        if not valid and s not in ("{", "}"):
            errors.append(s)

    # ── Phase 3: Semantic Analysis ────────────────────────────────────────
    phase3 = []
    sym_table = {}

    for node in phase2_flat:
        s    = node["line"]
        info = {"statement": s, "ok": node["valid"], "note": ""}

        if s in ("{", "}"):
            info["ok"] = True
            info["note"] = "Block delimiter"
            phase3.append(info); continue

        if s.startswith("#"):
            info["note"] = "Preprocessor — not type-checked"
            phase3.append(info); continue

        # function declaration
        fn = re.match(r'^(int|void|float|char|double)\s+([a-zA-Z_]\w*)\s*\(', s)
        if fn:
            sym_table[fn.group(2)] = fn.group(1)
            info["note"] = f"Function '{fn.group(2)}' → return type {fn.group(1)}"
            phase3.append(info); continue

        # var declaration
        decl = re.match(r'^(int|float|double|char|long|short)\s+([a-zA-Z_]\w*)', s)
        if decl:
            dtype, name = decl.group(1), decl.group(2)
            sym_table[name] = dtype
            info["note"] = f"'{name}' → {dtype} added to symbol table"
            phase3.append(info); continue

        # assignment — check declared
        assign = re.match(r'^([a-zA-Z_]\w*)\s*[+\-*/]?=', s)
        if assign:
            name = assign.group(1)
            if name in sym_table:
                info["note"] = f"'{name}' is {sym_table[name]} — type check ✓"
            else:
                info["ok"] = False
                info["note"] = f"Warning: '{name}' used before declaration"
            phase3.append(info); continue

        # printf format check
        if s.startswith("printf"):
            fmt_m = re.search(r'"([^"]*)"', s)
            if fmt_m:
                specs     = re.findall(r'%[dfisc]', fmt_m.group(1))
                args_part = s[s.find(",")+1:s.rfind(")")] if "," in s else ""
                arg_count = len([a for a in args_part.split(",") if a.strip()])
                if len(specs) != arg_count:
                    info["ok"] = False
                    info["note"] = f"printf: {len(specs)} specifier(s) but {arg_count} arg(s) — mismatch"
                else:
                    info["note"] = f"printf: {len(specs)} specifier(s) match {arg_count} arg(s) ✓"
            phase3.append(info); continue

        # if/while/for condition — check identifiers used
        cond_m = re.match(r'^(?:if|while|for)\s*\((.+)\)', s)
        if cond_m:
            idents = re.findall(r'[a-zA-Z_]\w*', cond_m.group(1))
            undecl = [i for i in idents if i not in sym_table and i not in C_KEYWORDS]
            if undecl:
                info["ok"] = False
                info["note"] = f"Undeclared identifier(s) in condition: {', '.join(undecl)}"
            else:
                info["note"] = f"Condition identifiers type-checked ✓"
            phase3.append(info); continue

        info["note"] = node["structure"]
        phase3.append(info)

    # ── Phase 4: IR Generation ────────────────────────────────────────────
    ir   = []
    tmp  = [0]
    lbl  = [0]
    def new_tmp(): tmp[0] += 1; return f"t{tmp[0]}"
    def new_lbl(): lbl[0] += 1; return f"L{lbl[0]}"

    for node in phase2_flat:
        s = node["line"]
        if not node["valid"] or s in ("{", "}"): continue
        if s.startswith("#"): continue

        # function def
        fn = re.match(r'^((?:int|void|float|char|double)\s+)([a-zA-Z_]\w*)\s*\((.*)\)\s*\{?$', s)
        if fn:
            ir.append(f"FUNC_BEGIN {fn.group(2)}")
            continue

        # var decl with init
        m = re.match(r'^(?:int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
        if m:
            name, expr = m.group(1), m.group(2).rstrip(";")
            ir.append(f"ALLOC {name}")
            # try constant folding inline
            try:
                val = eval(expr, {"__builtins__": {}})
                ir.append(f"STORE {name}, {val}  ; const")
            except Exception:
                t = new_tmp()
                ir.append(f"{t} = {expr}")
                ir.append(f"STORE {name}, {t}")
            continue

        # bare decl
        m = re.match(r'^(?:int|float|double|char|long|short)\s+([a-zA-Z_]\w*)\s*;?$', s)
        if m:
            ir.append(f"ALLOC {m.group(1)}")
            ir.append(f"STORE {m.group(1)}, 0  ; default")
            continue

        # ++/--
        m = re.match(r'^([a-zA-Z_]\w*)(\+\+|--).*', s.rstrip(";"))
        if m:
            op = "ADD" if m.group(2) == "++" else "SUB"
            ir.append(f"STORE {m.group(1)}, {op}({m.group(1)}, 1)")
            continue

        # compound assign
        m = re.match(r'^([a-zA-Z_]\w*)\s*([+\-*/])=\s*(.+);?$', s)
        if m:
            t = new_tmp()
            ir.append(f"{t} = {m.group(1)} {m.group(2)} {m.group(3).rstrip(';')}")
            ir.append(f"STORE {m.group(1)}, {t}")
            continue

        # plain assign
        m = re.match(r'^([a-zA-Z_]\w*)\s*=\s*(.+);?$', s)
        if m and not s.startswith("if") and not s.startswith("while"):
            t = new_tmp()
            ir.append(f"{t} = {m.group(2).rstrip(';')}")
            ir.append(f"STORE {m.group(1)}, {t}")
            continue

        # if
        m = re.match(r'^if\s*\((.+)\)', s)
        if m:
            L_else, L_end = new_lbl(), new_lbl()
            ir.append(f"IF_FALSE ({m.group(1)}) GOTO {L_else}")
            ir.append(f"; [then block]")
            ir.append(f"GOTO {L_end}")
            ir.append(f"{L_else}:  ; else / end-if")
            ir.append(f"{L_end}:")
            continue

        # while
        m = re.match(r'^while\s*\((.+)\)', s)
        if m:
            L_top, L_exit = new_lbl(), new_lbl()
            ir.append(f"{L_top}:  ; loop header")
            ir.append(f"IF_FALSE ({m.group(1)}) GOTO {L_exit}")
            ir.append(f"; [loop body]")
            ir.append(f"GOTO {L_top}")
            ir.append(f"{L_exit}:  ; loop exit")
            continue

        # for
        m = re.match(r'^for\s*\((.+);(.+);(.+)\)', s)
        if m:
            init, cond, upd = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            L_top, L_exit = new_lbl(), new_lbl()
            ir.append(f"; for init: {init}")
            ir.append(f"{L_top}:  ; for header")
            ir.append(f"IF_FALSE ({cond}) GOTO {L_exit}")
            ir.append(f"; [loop body]")
            ir.append(f"; for update: {upd}")
            ir.append(f"GOTO {L_top}")
            ir.append(f"{L_exit}:  ; for exit")
            continue

        # printf
        m = re.match(r'^printf\s*\((.+)\)\s*;?$', s)
        if m:
            ir.append(f"PARAM {m.group(1)}")
            ir.append(f"CALL printf")
            continue

        # return
        m = re.match(r'^return\s+(.*);?$', s)
        if m:
            ir.append(f"RETURN {m.group(1).rstrip(';')}")
            continue

        ir.append(f"; {s}")

    # ── Phase 5: Optimisation ─────────────────────────────────────────────
    optimised = []
    i = 0
    while i < len(ir):
        line = ir[i]

        # constant folding: t1 = 3 + 4  →  t1 = 7
        fold = re.match(r'^(t\d+)\s*=\s*(\d+\.?\d*)\s*([+\-*/])\s*(\d+\.?\d*)$', line)
        if fold:
            try:
                result = eval(f"{fold.group(2)}{fold.group(3)}{fold.group(4)}")
                result = int(result) if float(result) == int(result) else result
                optimised.append(f"{fold.group(1)} = {result}  ; folded: {fold.group(2)}{fold.group(3)}{fold.group(4)}")
                i += 1; continue
            except Exception:
                pass

        # dead STORE elimination: two identical consecutive STOREs
        if line.startswith("STORE") and i+1 < len(ir) and ir[i+1] == line:
            optimised.append(line)
            optimised.append(f"; ↑ duplicate STORE removed")
            i += 2; continue

        # remove STORE x, 0  ; default  immediately followed by STORE x, <val>
        m0 = re.match(r'^STORE (\w+), 0\s*;.*default', line)
        if m0 and i+1 < len(ir):
            m1 = re.match(rf'^STORE {m0.group(1)},', ir[i+1])
            if m1:
                optimised.append(f"; STORE {m0.group(1)}, 0 removed (overwritten next)")
                i += 1; continue

        optimised.append(line)
        i += 1

    # ── Phase 6: Code Generation ──────────────────────────────────────────
    codegen = []
    reg = [0]
    def new_reg(): reg[0] += 1; return f"R{reg[0]}"

    for instr in optimised:
        if instr.startswith(";"):
            codegen.append({"asm": instr, "note": "comment / annotation"}); continue

        if instr.startswith("FUNC_BEGIN"):
            fn_name = instr.split()[1]
            codegen.append({"asm": "PUSH  BP",        "note": "save caller base pointer"})
            codegen.append({"asm": "MOV   BP, SP",    "note": f"set stack frame for {fn_name}"})
            continue

        if instr.startswith("ALLOC"):
            name = instr.split()[1]
            codegen.append({"asm": f"SUB   SP, 4",    "note": f"reserve 4 bytes for '{name}'"})
            continue

        m = re.match(r'^STORE (\w+),\s*(.+?)(?:\s*;.*)?$', instr)
        if m:
            name, val = m.group(1), m.group(2).strip()
            r = new_reg()
            codegen.append({"asm": f"MOV   {r}, {val}",      "note": f"load value {val}"})
            codegen.append({"asm": f"MOV   [{name}], {r}",   "note": f"store into '{name}'"})
            continue

        m = re.match(r'^(t\d+)\s*=\s*(.+?)\s*([+\-*/])\s*(.+?)(?:\s*;.*)?$', instr)
        if m:
            t, lhs, op, rhs = m.group(1), m.group(2).strip(), m.group(3), m.group(4).strip()
            r1, r2, r3 = new_reg(), new_reg(), new_reg()
            op_map = {"+":"ADD","-":"SUB","*":"MUL","/":"DIV"}
            codegen.append({"asm": f"MOV   {r1}, {lhs}",                    "note": "load LHS"})
            codegen.append({"asm": f"MOV   {r2}, {rhs}",                    "note": "load RHS"})
            codegen.append({"asm": f"{op_map.get(op,'OP')}   {r3}, {r1}, {r2}", "note": f"compute {lhs} {op} {rhs} → {t}"})
            continue

        if instr.startswith("IF_FALSE"):
            m = re.match(r'^IF_FALSE \((.+)\) GOTO (\w+)', instr)
            if m:
                cond, lbl_name = m.group(1), m.group(2)
                codegen.append({"asm": f"CMP   {cond}",       "note": "evaluate condition"})
                codegen.append({"asm": f"JZ    {lbl_name}",   "note": f"jump if false → {lbl_name}"})
            continue

        if instr.startswith("GOTO"):
            lbl_name = instr.split()[1]
            codegen.append({"asm": f"JMP   {lbl_name}", "note": "unconditional jump"})
            continue

        if re.match(r'^L\d+:', instr):
            label_clean = re.match(r'^(L\d+)', instr).group(1)
            codegen.append({"asm": f"{label_clean}:", "note": "label"})
            continue

        if instr.startswith("PARAM"):
            codegen.append({"asm": f"PUSH  {instr[6:]}", "note": "push argument onto stack"})
            continue

        if instr.startswith("CALL printf"):
            codegen.append({"asm": "CALL  printf",  "note": "call C standard library printf"})
            codegen.append({"asm": "ADD   SP, n",   "note": "clean up pushed args"})
            continue

        if instr.startswith("RETURN"):
            val = instr[7:].strip()
            r = new_reg()
            codegen.append({"asm": f"MOV   {r}, {val}",  "note": "load return value"})
            codegen.append({"asm": f"MOV   EAX, {r}",    "note": "return value in EAX"})
            codegen.append({"asm": "POP   BP",            "note": "restore base pointer"})
            codegen.append({"asm": "RET",                 "note": "return to caller"})
            continue

        codegen.append({"asm": instr, "note": ""})

    return jsonify({
        "phase1_lexer":     phase1,
        "phase2_tree":      phase2_tree,
        "phase3_semantic":  phase3,
        "phase4_ir":        ir,
        "phase5_optimised": optimised,
        "phase6_codegen":   codegen,
        "errors":           errors
    })

if __name__ == "__main__":
    app.run(debug=True)
