"""Owned process tree: closing the Windows job stops all calculation children."""

from __future__ import annotations

import os


class ProcessTree:
    def __init__(self, process):
        self.process = process
        self.job = None
        if os.name == "nt":
            import win32api
            import win32job

            self.job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation
            )
            info["BasicLimitInformation"][
                "LimitFlags"
            ] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation, info
            )
            handle = win32api.OpenProcess(0x0100 | 0x0001, False, process.pid)
            try:
                win32job.AssignProcessToJobObject(self.job, handle)
            except Exception:
                self.job.Close()
                self.job = None
                process.kill()
                process.wait()
                raise
            finally:
                handle.Close()

    def close(self):
        if self.job is not None:
            self.job.Close()
            self.job = None
        elif os.name != "nt":
            import signal

            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
