"""The platform's virtual filesystem as a deepagents backend.

Team folders, memory files (AGENTS.md per tier) and skills (SKILL.md per scope) live in
one namespace. Every operation is checked against the invoker's access to the mount,
like a Drive-style ACL, so the agent can reach exactly what the invoker can.

The backend also feeds provenance to the run context: reading a file lowers the run label
to that mount's readers, and loading AGENTS.md or SKILL.md records an instruction segment
authored by whoever wrote the file.
"""

from __future__ import annotations

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import create_file_data, perform_string_replacement, slice_read_response
from wcmatch import glob as wcglob

from .run_context import RunContext, Segment

INSTRUCTION_FILES = ("AGENTS.md", "SKILL.md")


class ScopedBackend(BackendProtocol):
    def __init__(self, rc: RunContext) -> None:
        self.rc = rc
        self.w = rc.world

    # ---- access ------------------------------------------------------
    def _can(self, path: str) -> bool:
        return self.rc.invoker in self.w.readers_of_path(path)

    def _visible(self) -> dict[str, str]:
        return {p: f.content for p, f in self.w.files.items() if self._can(p)}

    def _note_read(self, path: str) -> None:
        f = self.w.files[path]
        readers = self.w.readers_of_path(path)
        self.rc.observe(readers)
        if path.endswith(INSTRUCTION_FILES):
            kind = "memory" if path.endswith("AGENTS.md") else "skill"
            self.rc.add_segment(Segment(f.content, kind, frozenset([f.author]), instruction=True))
        self.rc.step("read_file", f"{path}\n{f.content}", readers)

    # ---- reads -------------------------------------------------------
    def ls(self, path: str) -> LsResult:
        base = path.rstrip("/") + "/"
        seen: dict[str, bool] = {}
        for p in self._visible():
            if not p.startswith(base):
                continue
            rest = p[len(base):]
            head, sep, _ = rest.partition("/")
            seen[base + head + ("/" if sep else "")] = bool(sep)
        return LsResult(entries=[{"path": p, "is_dir": d} for p, d in sorted(seen.items())])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        if file_path not in self.w.files or not self._can(file_path):
            return ReadResult(error=f"File '{file_path}' not found")
        self._note_read(file_path)
        return slice_read_response(create_file_data(self.w.files[file_path].content), offset, limit)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None, *,
             max_count: int | None = None) -> GrepResult:
        base = (path or "/").rstrip("/") + "/"
        matches: list[GrepMatch] = []
        for p, content in self._visible().items():
            if not p.startswith(base) or (glob and not wcglob.globmatch(p, glob, flags=wcglob.GLOBSTAR)):
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if pattern in line:
                    matches.append({"path": p, "line": i, "text": line})
                    self.rc.observe(self.w.readers_of_path(p))
        if max_count is not None:
            matches = matches[:max_count]
        return GrepResult(matches=matches)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        base = (path or "/").rstrip("/") + "/"
        pat = pattern if pattern.startswith("/") else base + pattern
        hits = [{"path": p} for p in sorted(self._visible()) if wcglob.globmatch(p, pat, flags=wcglob.GLOBSTAR)]
        return GlobResult(matches=hits)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        out = []
        for p in paths:
            if p not in self.w.files:
                out.append(FileDownloadResponse(path=p, error="file_not_found"))
            elif not self._can(p):
                out.append(FileDownloadResponse(path=p, error="permission_denied"))
            else:
                self._note_read(p)
                out.append(FileDownloadResponse(path=p, content=self.w.files[p].content.encode()))
        return out

    # ---- writes ------------------------------------------------------
    def _commit(self, path: str, content: str) -> None:
        self.w.put_file(path, content, self.rc.invoker)  # written under the invoker's identity
        self.w.record_sink(f"vfs:{path}", content, self.w.readers_of_path(path))

    def write(self, file_path: str, content: str) -> WriteResult:
        if self.w.mount_of(file_path) is None or not self._can(file_path):
            return WriteResult(error=f"permission denied: {file_path}")
        self._commit(file_path, content)
        return WriteResult(path=file_path)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        if file_path not in self.w.files or not self._can(file_path):
            return EditResult(error=f"Error: File '{file_path}' not found")
        res = perform_string_replacement(self.w.files[file_path].content, old_string, new_string, replace_all)
        if isinstance(res, str):
            return EditResult(error=res)
        new_content, n = res
        self._commit(file_path, new_content)
        return EditResult(path=file_path, occurrences=int(n))

    def delete(self, file_path: str) -> DeleteResult:
        if file_path not in self.w.files or not self._can(file_path):
            return DeleteResult(error=f"File '{file_path}' not found")
        del self.w.files[file_path]
        return DeleteResult(path=file_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        out = []
        for p, data in files:
            r = self.write(p, data.decode(errors="replace"))
            out.append(FileUploadResponse(path=p, error="permission_denied" if r.error else None))
        return out
