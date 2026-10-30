"""User-configured local validation, fixed at server startup, never a shell RPC."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import subprocess
import time
from .cpp import SafeError


class Validator:
    def __init__(self, profile, log_root):
        self.profile = str(Path(profile).resolve())
        data = json.loads(Path(profile).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or set(data) - {"commands", "timeout_seconds"}:
            raise SafeError("验证配置只允许 commands 和 timeout_seconds。")
        self.commands = data.get("commands", [])
        self.timeout = data.get("timeout_seconds", 120)
        if not isinstance(self.commands, list) or not 1 <= len(self.commands) <= 8:
            raise SafeError("需要1至8条预先配置的验证命令。")
        if any(not isinstance(c, list) or not c or any(not isinstance(a, str) or "\0" in a for a in c) for c in self.commands):
            raise SafeError("验证命令必须是参数数组；不使用 shell。")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 600:
            raise SafeError("验证超时为1至600秒。")
        self.log_root = Path(log_root)
        self.log_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _failure_detail(log, max_bytes=4096, max_chars=1200):
        """A bounded log tail lets the caller repair the actual failed check.

        Keep complete output on disk. Do not require a second log-reading round
        trip just to learn the failed assertion, and never echo an unbounded log.
        """
        with log.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes))
            raw = stream.read(max_bytes)
        text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = "".join(c for c in text if c in "\n\t" or c.isprintable()).strip()
        truncated = size > max_bytes or len(text) > max_chars
        return ("[日志尾部，已截断]\n" if truncated else "") + text[-max_chars:]

    def run(self, root):
        results=[]
        start=time.perf_counter()
        folder=self.log_root/str(time.time_ns());folder.mkdir()
        for i,command in enumerate(self.commands):
            args=[a.replace("{project}",str(root)).replace("{python}",__import__('sys').executable) for a in command]
            log=folder/(str(i)+".log")
            try:
                # A file bounds in-memory output; the user decides retention.
                with log.open('wb') as stream:
                    result=subprocess.run(args,cwd=root,stdout=stream,stderr=subprocess.STDOUT,
                         timeout=self.timeout,check=False,shell=False,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                code=result.returncode
            except (OSError,subprocess.TimeoutExpired) as exc:
                with log.open('ab') as stream:stream.write(str(exc).encode('utf-8'))
                code=-1
            results.append({"command":args,"returncode":code,"log":str(log)})
            if code:
                summary={"status":"failed","steps":results,"elapsed_ms":round((time.perf_counter()-start)*1000,3)}
                (folder/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                raise SafeError("编译/测试失败，源码事务将回滚（显式validate不写源码）；完整日志："
                                + str(log) + "\n验证输出：\n" + self._failure_detail(log))
        summary={"status":"passed","steps":results,"elapsed_ms":round((time.perf_counter()-start)*1000,3)}
        (folder/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        return summary
