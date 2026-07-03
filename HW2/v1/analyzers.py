"""分析引擎。把交接時會踩到的問題叫做「地雷」(Landmine)，不同 Detector 偵測不同類型。"""
import ast, os, re
from abc import ABC, abstractmethod
from models import Landmine, FileReport

def _is_main_guard(node):
    try:
        t = node.test
        return isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"
    except AttributeError:
        return False

class BaseDetector(ABC):
    @property
    @abstractmethod
    def name(self): ...
    @abstractmethod
    def detect(self, source, tree, filepath): ...

class TodoDetector(BaseDetector):
    """找出 TODO / FIXME / HACK / XXX 標記。"""
    PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", re.IGNORECASE)

    @property
    def name(self):
        return "todo"

    def detect(self, source, tree, filepath):
        mines = []
        for i, line in enumerate(source.splitlines(), 1):
            m = self.PATTERN.search(line)
            if m:
                tag, desc = m.group(1).upper(), m.group(2).strip() or "(no description)"
                mines.append(Landmine(kind="todo", filepath=filepath, line=i,
                    severity="high" if tag in ("FIXME", "HACK") else "medium",
                    message=f"{tag}: {desc}",
                    suggested_question=f"Line {i} 有個 {tag}，這個後來解決了嗎？還是可以先忽略？"))
        return mines

class CodeSmellDetector(BaseDetector):
    """偵測缺 docstring、命名問題、過長函式、過高複雜度。"""
    SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*_{0,2}$")
    PASCAL = re.compile(r"^_?[A-Z][a-zA-Z0-9]*$")

    def __init__(self, max_complexity=10, max_function_length=50):
        self._max_cc, self._max_fl = max_complexity, max_function_length

    @property
    def name(self):
        return "code_smell"

    def detect(self, source, tree, filepath):
        mines, max_cc, max_fl = [], self._max_cc, self._max_fl
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_") and not self._has_doc(node):
                    mines.append(Landmine(kind="missing_docstring", filepath=filepath, line=node.lineno,
                        severity="medium", message=f"Function '{node.name}' 沒有 docstring",
                        suggested_question=f"'{node.name}' 的用途跟參數意義是什麼？"))
                if not self.SNAKE.match(node.name):
                    mines.append(Landmine(kind="naming", filepath=filepath, line=node.lineno, severity="low",
                        message=f"Function '{node.name}' 不是 snake_case",
                        suggested_question=f"'{node.name}' 命名有特殊原因嗎？"))
                end = getattr(node, "end_lineno", node.lineno)
                if end - node.lineno + 1 > max_fl:
                    mines.append(Landmine(kind="long_func", filepath=filepath, line=node.lineno, severity="high",
                        message=f"Function '{node.name}' 有 {end - node.lineno + 1} 行，太長了",
                        suggested_question=f"'{node.name}' 太長了，有辦法拆嗎？"))
                cc = 1
                for ch in ast.walk(node):
                    if isinstance(ch, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
                        cc += 1
                    elif isinstance(ch, (ast.And, ast.Or, ast.comprehension)):
                        cc += 1
                if cc > max_cc:
                    mines.append(Landmine(kind="high_complexity", filepath=filepath, line=node.lineno, severity="high",
                        message=f"Function '{node.name}' 圈複雜度 {cc}（超過 {max_cc}）",
                        suggested_question=f"'{node.name}' 邏輯很複雜，有什麼 edge case 要注意？"))
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_") and not self._has_doc(node):
                    mines.append(Landmine(kind="missing_docstring", filepath=filepath, line=node.lineno,
                        severity="medium", message=f"Class '{node.name}' 沒有 docstring",
                        suggested_question=f"'{node.name}' 的職責是什麼？什麼時候該用它？"))
                if not self.PASCAL.match(node.name):
                    mines.append(Landmine(kind="naming", filepath=filepath, line=node.lineno, severity="low",
                        message=f"Class '{node.name}' 不是 PascalCase",
                        suggested_question=f"'{node.name}' 命名有特殊原因嗎？"))
        return mines

    def _has_doc(self, node):
        return node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, (ast.Constant, ast.Str))

class DependencyMapper:
    """解析 import 關係，拓撲排序產生建議閱讀順序。"""
    def map_project(self, py_files, base_dir):
        mod_map = {}
        for fp in py_files:
            mod = os.path.relpath(fp, base_dir).replace(os.sep, ".").removesuffix(".py")
            if mod.endswith(".__init__"):
                mod = mod[:-9]
            mod_map[mod] = fp
        graph = {f: [] for f in py_files}
        for fpath in py_files:
            try:
                tree = ast.parse(open(fpath, encoding="utf-8").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Import):
                    targets = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    targets = [node.module]
                for t in targets:
                    if t in mod_map and mod_map[t] != fpath and mod_map[t] not in graph[fpath]:
                        graph[fpath].append(mod_map[t])
        return graph, self._topo_sort(graph), [f for f in py_files if self._has_main(f)]

    def _topo_sort(self, graph):
        in_deg = {n: sum(1 for d in deps if d in graph) for n, deps in graph.items()}
        queue, result = sorted(n for n in in_deg if in_deg[n] == 0), []
        while queue:
            cur = queue.pop(0)
            result.append(cur)
            for nd, deps in graph.items():
                if cur in deps and nd not in result:
                    in_deg[nd] -= 1
                    if in_deg[nd] == 0:
                        queue.append(nd)
            queue.sort()
        return result + sorted(set(graph) - set(result))

    def _has_main(self, fpath):
        try:
            tree = ast.parse(open(fpath, encoding="utf-8").read())
            return any(_is_main_guard(n) for n in ast.walk(tree) if isinstance(n, ast.If))
        except (SyntaxError, OSError):
            return False

class ScanEngine:
    def __init__(self, detectors=None, config=None):
        if detectors is not None:
            self._detectors = detectors
        else:
            t = config.thresholds if config else {}
            self._detectors = [TodoDetector(), CodeSmellDetector(
                max_complexity=t.get("max_complexity", 10),
                max_function_length=t.get("max_function_length", 50))]
        self._mapper = DependencyMapper()

    def scan_file(self, filepath):
        source = open(filepath, "r", encoding="utf-8").read()
        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as e:
            return FileReport(filepath=filepath,
                landmines=[Landmine(kind="syntax_error", filepath=filepath, line=e.lineno or 0,
                    message=f"SyntaxError: {e.msg}", severity="high",
                    suggested_question="這個檔案有語法錯誤，是還沒寫完嗎？")],
                metadata={"parse_error": True})
        code_lines = [l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]
        mines = [m for det in self._detectors for m in det.detect(source, tree, filepath)]
        return FileReport(filepath=filepath, line_count=len(code_lines),
            function_count=sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
            class_count=sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef)),
            has_entry_point=any(_is_main_guard(n) for n in ast.walk(tree) if isinstance(n, ast.If)),
            landmines=mines)

    def scan_path(self, path):
        py_files = self._collect(path)
        reports = [self.scan_file(f) for f in py_files]
        base = path if os.path.isdir(path) else os.path.dirname(path) or "."
        graph, order, entries = self._mapper.map_project(py_files, base)
        return reports, graph, order, entries

    def _collect(self, path):
        if os.path.isfile(path):
            return [path] if path.endswith(".py") else []
        out = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            out.extend(os.path.join(root, fn) for fn in sorted(files) if fn.endswith(".py"))
        return out
