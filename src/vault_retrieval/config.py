import fnmatch
import json
import os
import re
import stat
from pathlib import Path

from .common import VaultError, canonical, digest

FORMATS = {".md", ".markdown", ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".odp", ".odt"}
ROLES = {"raw", "glossary", "study", "structured", "generated", "inbox", "scaffold"}
CODE_MARKERS = {".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "CMakeLists.txt"}
DEFAULT_DENY = [
    "**/.github",
    "**/.obsidian",
    "**/.cache",
    "**/src",
    "**/code",
    "**/tests",
    "**/data",
    "**/datasets",
    "**/.venv",
    "**/venv",
    "**/.idea",
    "**/.vscode",
    "**/build",
    "**/dist",
    "**/caches",
    "**/README*",
    "**/CONTRIBUTING*",
    "**/AGENTS.md",
    "**/~$*",
    ".obsidian",
    ".git",
    ".env*",
    "**/.env*",
    "**/*.key",
    "**/*.pem",
    "**/node_modules",
    "**/__pycache__",
]


def path_is_file_like(path):
    return bool(path.suffix)


def under(path, root):
    return path == root or root in path.parents


class Config:
    def __init__(self, data):
        self.data = data
        self.task_attachments = set()
        for key in ("vault", "state", "roots", "exclude", "outputs", "processing_log"):
            if key not in data:
                raise VaultError("invalid_config", f"Missing {key}; see examples/config.json.")
        self.vault = Path(data["vault"]).expanduser().resolve(strict=True)
        self.state = Path(data["state"]).expanduser().resolve()
        if under(self.state, self.vault) or under(self.vault, self.state):
            raise VaultError("invalid_config", "State and vault directories must be disjoint.")
        if not data["roots"] or not isinstance(data["exclude"], list):
            raise VaultError("invalid_config", "Explicit roots and exclusion list are required.")
        self.roots = list(data["roots"])
        for rule in data.get("input_rules", []):
            if (
                not isinstance(rule, dict)
                or not isinstance(rule.get("pattern"), str)
                or not isinstance(rule.get("formats"), list)
                or not rule["formats"]
                or any(ext not in FORMATS for ext in rule["formats"])
            ):
                raise VaultError(
                    "invalid_config", "Input rules need a relative pattern and known formats."
                )
            self.relative(rule["pattern"])
        if data.get("discover_future_cs"):
            for semester in self.vault.iterdir():
                if (
                    semester.is_dir()
                    and not semester.is_symlink()
                    and re.fullmatch(r"(?:Fall|Spring|Summer|Winter)_\d{4}", semester.name)
                ):
                    for course in semester.iterdir():
                        if (
                            course.is_dir()
                            and not course.is_symlink()
                            and re.fullmatch(r"CS\d+", course.name)
                        ):
                            name = str(course.relative_to(self.vault))
                            if not any(r["path"] == name for r in self.roots):
                                self.roots.append(
                                    {"path": name, "role": "study", "project": course.name}
                                )
        for root in self.roots:
            if root.get("role") not in ROLES or not root.get("project"):
                raise VaultError(
                    "invalid_config", "Each root needs path, project, and a known role."
                )
            self.relative(root["path"])
        for path in data["outputs"] + data.get("companion_roots", []) + [data["processing_log"]]:
            self.relative(path)
        self.outputs = list(data["outputs"])
        if data.get("discover_future_cs"):
            for root in self.roots:
                if re.fullmatch(r"CS\d+", Path(root["path"]).name):
                    self.outputs.extend(root["path"] + "/" + name for name in ("Notes", "Concepts"))
        lifecycle = data.get("task_lifecycle")
        if lifecycle:
            try:
                tasks = json.loads(self.read(lifecycle)).get("attachments", [])
                self.task_attachments = {a["source"] for a in tasks}
            except (OSError, ValueError, KeyError) as exc:
                raise VaultError(
                    "invalid_config", "Cannot read task attachment exclusions."
                ) from exc
        self.revision = digest(
            canonical(
                {
                    **data,
                    "roots": self.roots,
                    "outputs": sorted(set(self.outputs)),
                    "task_attachments": sorted(self.task_attachments),
                }
            ).encode()
        )

    @classmethod
    def load(cls, path):
        try:
            raw = Path(path).expanduser().read_text()
        except FileNotFoundError as exc:
            raise VaultError(
                "config_not_found",
                "The --config file does not exist. Copy examples/live-config.proposed.json "
                "to config.local.json, review its scope, then set enabled to true before indexing. "
                "Validate with: vault --config config.local.json validate",
            ) from exc
        except OSError as exc:
            raise VaultError(
                "config_unreadable",
                "Cannot read the --config file; check its path and permissions.",
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VaultError("invalid_config", "The --config file is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise VaultError("invalid_config", "The --config file must contain a JSON object.")
        return cls(data)

    def relative(self, name):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise VaultError("excluded", "Paths must be vault-relative without traversal.")
        return path

    def denied(self, name):
        parts = Path(name).parts
        prefixes = [str(Path(*parts[:i])) for i in range(1, len(parts) + 1)]
        sensitive = re.search(
            r"(?:resume|résumé|contract|employment|offer[ _-]letter|\bnda\b|agreement)",
            Path(name).name,
            re.I,
        )
        if sensitive or name in self.task_attachments:
            return True
        return any(
            fnmatch.fnmatchcase(prefix.casefold(), pat.casefold())
            for prefix in prefixes
            for pat in DEFAULT_DENY + self.data["exclude"]
        )

    def classify(self, name):
        path = self.relative(name)
        matches = [r for r in self.roots if under(path, Path(r["path"]))]
        if not matches:
            raise VaultError("excluded", "Path is outside configured roots.")
        root = max(matches, key=lambda r: len(Path(r["path"]).parts))
        role = root["role"]
        if "Raw" in path.parts:
            role = "raw"
        if name in self.data.get("glossary", []):
            role = "glossary"
        if any(under(path, Path(out)) for out in self.outputs):
            role = "generated"
        if name == self.data["processing_log"]:
            role = "scaffold"
        return role, root["project"]

    def admitted_input(self, name):
        """Admit configured input shapes for extraction, never for authorship or writes."""
        self.check(name)
        return name in self.data.get("glossary", []) or any(
            fnmatch.fnmatchcase(name, rule["pattern"])
            and Path(name).suffix.lower() in rule["formats"]
            for rule in self.data.get("input_rules", [])
        )

    def check(self, name, write=False):
        rel = self.relative(name)
        operational = (
            name in self.data.get("operational_files", []) or name == self.data["processing_log"]
        )
        if not operational:
            self.classify(name)
        if (
            not operational
            and path_is_file_like(rel)
            and not (self.vault / rel).is_dir()
            and rel.suffix.lower() not in FORMATS
        ):
            raise VaultError("excluded", "Only approved study-document formats may be read.")
        if not operational and self.denied(name):
            raise VaultError("excluded", "Path matches an exclusion.")
        path = self.vault / rel
        # Conservative policy: reject all symlink components, even internal aliases.
        current = self.vault
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise VaultError("excluded", "Symlink paths are not admitted.")
        for parent in [path.parent, *path.parent.parents]:
            if not under(parent, self.vault):
                break
            cs_exception = self.data.get("cs_study_exception", False) and any(
                re.fullmatch(r"CS\d+", part) for part in rel.parts
            )
            if not cs_exception and any((parent / marker).exists() for marker in CODE_MARKERS):
                raise VaultError("excluded", "Code-project trees are protected.")
        if not under(path.resolve(), self.vault):
            raise VaultError("excluded", "Resolved path escapes the vault.")
        if write:
            is_log = name == self.data["processing_log"]
            companion = any(under(rel, Path(root)) for root in self.data.get("companion_roots", []))
            role = "scaffold" if is_log else self.classify(name)[0]
            if (
                (path.suffix.lower() != ".md" and not (is_log and path.suffix.lower() == ".json"))
                or (not is_log and not companion and role not in {"generated", "structured"})
                or path.name in {"AGENTS.md", "CONTEXT.md"}
            ):
                raise VaultError(
                    "excluded",
                    "Only derived/structured Markdown and the processing log are writable.",
                )
            if (
                not path.exists()
                and not is_log
                and not companion
                and not any(under(rel, Path(out)) for out in self.outputs)
            ):
                raise VaultError("excluded", "New notes require a designated output folder.")
        return path

    def open_parent(self, name, write=False, create=False):
        self.check(name, write=write)
        rel = self.relative(name)
        fd = os.open(self.vault, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in rel.parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            return fd, rel.name
        except BaseException:
            os.close(fd)
            raise

    def read(self, name):
        parent, leaf = self.open_parent(name)
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise VaultError(
                        "excluded", "Only ordinary, non-hardlinked files are admitted."
                    )
                data = stream.read()
                after = os.fstat(stream.fileno())
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise VaultError("stale", "Source changed during reading; retry.")
                return data
        finally:
            os.close(parent)

    def inventory(self):
        found = set()
        for root in self.roots:
            try:
                base = self.check(root["path"])
            except VaultError:
                continue
            if not base.exists():
                continue
            candidates = [base] if base.is_file() else None
            if candidates is None:
                candidates = []

                def failed(error):
                    raise VaultError(
                        "scan_failed", "Inventory could not read a configured directory."
                    ) from error

                for directory, dirs, files in os.walk(base, followlinks=False, onerror=failed):
                    allowed = []
                    for d in dirs:
                        try:
                            self.check(str((Path(directory) / d).relative_to(self.vault)))
                            allowed.append(d)
                        except VaultError:
                            pass
                    dirs[:] = allowed
                    candidates.extend(Path(directory) / f for f in files)
            for path in candidates:
                name = str(path.relative_to(self.vault))
                if path.suffix.lower() not in FORMATS:
                    continue
                try:
                    self.check(name)
                    found.add(name)
                except VaultError:
                    pass
        return sorted(found)
