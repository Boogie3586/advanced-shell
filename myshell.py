#!/usr/bin/env python3
"""
myshell.py — Deliverable 1 (improved)

Features:
- Built-ins: cd, pwd, exit, echo, clear, ls, cat, mkdir, rmdir, rm, touch, kill
- Foreground and background execution of external commands
- Job control: jobs, fg <jobid>, bg <jobid>
- Tracks process status; handles SIGCHLD to update job table
- Uses subprocess.Popen with new process groups so signals can be delivered to whole job
Notes:
- Unix-only (uses os.setpgrp, signals, waitpid, ...). Tested on Linux/macOS.
"""

import os
import sys
import shlex
import signal
import subprocess
import time
from collections import OrderedDict
import getpass

# Config
DONE_ENTRY_TTL = 60.0  # seconds to keep Done/Exited job entries before pruning

# Global job table: job_id -> {pid, proc (Popen), cmdline, status, start_time, exitcode}
# status values: "Running", "Stopped", "Exited(<code>)", "Signaled(<sig>)", "Done"
jobs = OrderedDict()
next_job_id = 1

# Map pid -> job_id for quick lookup
pid_to_jid = {}

# Foreground PID (pid of the currently running foreground process)
foreground_pid = None

# ---- Job helpers ----
def _get_next_job_id():
    global next_job_id
    jid = next_job_id
    next_job_id += 1
    return jid

def add_job(proc: subprocess.Popen, cmdline: str, status="Running"):
    """Add a background job to the table and return its job id."""
    jid = _get_next_job_id()
    jobs[jid] = {
        "pid": proc.pid,
        "proc": proc,
        "cmdline": cmdline,
        "status": status,
        "start_time": time.time(),
        "exitcode": None,
    }
    pid_to_jid[proc.pid] = jid
    return jid

def remove_job_by_pid(pid):
    jid = pid_to_jid.pop(pid, None)
    if jid is not None:
        jobs.pop(jid, None)

def update_job_status(pid, status, exitcode=None):
    jid = pid_to_jid.get(pid)
    if jid is not None and jid in jobs:
        jobs[jid]["status"] = status
        if exitcode is not None:
            jobs[jid]["exitcode"] = exitcode

def mark_job_done(pid, exitcode=None):
    """Mark job done/Exited/Signaled as appropriate but keep entry for TTL."""
    jid = pid_to_jid.get(pid)
    if jid is not None and jid in jobs:
        if exitcode is not None:
            jobs[jid]["status"] = f"Exited({exitcode})"
            jobs[jid]["exitcode"] = exitcode
        else:
            # If caller didn't supply exitcode, leave to other handlers
            jobs[jid]["status"] = "Done"
        # remove pid->jid mapping so operations like fg/bg won't find it as running
        pid_to_jid.pop(pid, None)

def find_job_by_jid(jid):
    return jobs.get(jid)

# ---- Signal handlers ----
def sigchld_handler(signum, frame):
    """
    Reap children and update job table.
    Uses os.waitpid in a loop with WNOHANG|WUNTRACED|WCONTINUED.
    """
    try:
        while True:
            # -1: any child. Flags: WNOHANG so we don't block; get stopped/continued children too.
            pid, status = os.waitpid(-1, os.WNOHANG | os.WUNTRACED | os.WCONTINUED)
            if pid == 0:
                break
            if pid < 0:
                break
            # Interpret status
            if os.WIFEXITED(status):
                exitcode = os.WEXITSTATUS(status)
                update_job_status(pid, f"Exited({exitcode})", exitcode=exitcode)
                mark_job_done(pid, exitcode=exitcode)
            elif os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
                update_job_status(pid, f"Signaled({sig})")
                mark_job_done(pid, exitcode=None)
            elif os.WIFSTOPPED(status):
                sig = os.WSTOPSIG(status)
                update_job_status(pid, "Stopped")
            elif os.WIFCONTINUED(status):
                update_job_status(pid, "Running")
    except ChildProcessError:
        # no child processes
        pass
    except Exception:
        # keep handler robust; avoid printing from signal handler
        pass

# ignore signals that would interfere with terminal control
signal.signal(signal.SIGCHLD, sigchld_handler)
signal.signal(signal.SIGTTOU, signal.SIG_IGN)
signal.signal(signal.SIGTTIN, signal.SIG_IGN)

# Ctrl-C forwarding to foreground job
def sigint_handler(signum, frame):
    global foreground_pid
    if foreground_pid:
        try:
            os.killpg(os.getpgid(foreground_pid), signal.SIGINT)
        except ProcessLookupError:
            pass
    else:
        # no foreground job; newline for prompt
        print()

signal.signal(signal.SIGINT, sigint_handler)

# Ctrl-Z (SIGTSTP) forwarding
def sigtstp_handler(signum, frame):
    global foreground_pid
    if foreground_pid:
        try:
            os.killpg(os.getpgid(foreground_pid), signal.SIGTSTP)
        except ProcessLookupError:
            pass
    else:
        print()

signal.signal(signal.SIGTSTP, sigtstp_handler)

# ---- Builtin implementations ----
def builtin_cd(args):
    target = args[0] if args else os.environ.get("HOME", "/")
    try:
        os.chdir(os.path.expanduser(target))
    except Exception as e:
        print(f"cd: {e}")

def builtin_pwd(args):
    print(os.getcwd())

def builtin_exit(args):
    print("Exiting shell.")
    # terminate background jobs
    for jid, job in list(jobs.items()):
        pid = job["pid"]
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            pass
    sys.exit(0)

def builtin_echo(args):
    print(" ".join(args))

def builtin_clear(args):
    print("\033[H\033[J", end="")

def builtin_ls(args):
    target = args[0] if args else "."
    try:
        names = os.listdir(target)
        names.sort()
        for n in names:
            print(n)
    except Exception as e:
        print(f"ls: {e}")

def builtin_cat(args):
    if not args:
        print("cat: missing filename")
        return
    for filename in args:
        try:
            with open(filename, "r") as f:
                sys.stdout.write(f.read())
        except Exception as e:
            print(f"cat: {filename}: {e}")

def builtin_mkdir(args):
    if not args:
        print("mkdir: missing directory")
        return
    for d in args:
        try:
            os.makedirs(d, exist_ok=False)
        except Exception as e:
            print(f"mkdir: {d}: {e}")

def builtin_rmdir(args):
    if not args:
        print("rmdir: missing directory")
        return
    for d in args:
        try:
            os.rmdir(d)
        except Exception as e:
            print(f"rmdir: {d}: {e}")

def builtin_rm(args):
    if not args:
        print("rm: missing filename")
        return
    for f in args:
        try:
            if os.path.isdir(f):
                print(f"rm: {f}: is a directory")
            else:
                os.remove(f)
        except Exception as e:
            print(f"rm: {f}: {e}")

def builtin_touch(args):
    if not args:
        print("touch: missing filename")
        return
    for fname in args:
        try:
            fd = open(fname, "a")
            fd.close()
            os.utime(fname, None)
        except Exception as e:
            print(f"touch: {fname}: {e}")

def builtin_kill(args):
    if not args:
        print("kill: missing pid/job")
        return
    for token in args:
        try:
            # job syntax: %<jobid>
            if token.startswith("%"):
                # job id
                jid = int(token[1:])
                job = find_job_by_jid(jid)
                if not job:
                    print(f"kill: % {jid}: no such job")
                    continue
                pid = job["pid"]
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception as e:
                    print(f"kill: {e}")
            else:
                # numeric pid
                pid = int(token)
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception as e:
                    print(f"kill: {e}")
        except ValueError:
            print(f"kill: invalid pid/job: {token}")

def builtin_jobs(args):
    now = time.time()
    for jid, job in jobs.items():
        status = job["status"]
        age = int(now - job["start_time"])
        exitcode = job.get("exitcode")
        print(f"[{jid}] {job['pid']} {status}\t{job['cmdline']} (age {age}s)")

def builtin_fg(args):
    """
    Bring job to foreground. Usage: fg <jobid>
    If missing jobid, try last job.
    """
    global foreground_pid
    if args:
        try:
            jid = int(args[0])
        except ValueError:
            print("fg: bad job id")
            return
    else:
        if not jobs:
            print("fg: no current job")
            return
        jid = next(reversed(jobs))  # last inserted
    job = find_job_by_jid(jid)
    if not job:
        print(f"fg: job {jid} not found")
        return
    pid = job["pid"]
    proc = job["proc"]
    # send SIGCONT to the process group
    try:
        os.killpg(os.getpgid(pid), signal.SIGCONT)
    except Exception:
        pass
    job["status"] = "Running"
    foreground_pid = pid
    try:
        # Wait until process exits or is stopped; let sigchld_handler update statuses too.
        while True:
            try:
                wpid, status = os.waitpid(pid, os.WUNTRACED)
            except InterruptedError:
                continue
            if wpid == 0:
                continue
            if os.WIFSTOPPED(status):
                job["status"] = "Stopped"
                # re-add pid->jid mapping (if it was removed earlier)
                pid_to_jid[pid] = jid
                print(f"\n[{jid}] {pid} Stopped")
                break
            elif os.WIFEXITED(status):
                exitcode = os.WEXITSTATUS(status)
                job["status"] = f"Exited({exitcode})"
                job["exitcode"] = exitcode
                # cleanup mapping
                pid_to_jid.pop(pid, None)
                break
            elif os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
                job["status"] = f"Signaled({sig})"
                pid_to_jid.pop(pid, None)
                break
    except Exception:
        pass
    foreground_pid = None

def builtin_bg(args):
    """
    Resume a stopped job in background. Usage: bg <jobid>
    """
    if args:
        try:
            jid = int(args[0])
        except ValueError:
            print("bg: bad job id")
            return
    else:
        if not jobs:
            print("bg: no current job")
            return
        jid = next(reversed(jobs))
    job = find_job_by_jid(jid)
    if not job:
        print(f"bg: job {jid} not found")
        return
    pid = job["pid"]
    try:
        os.killpg(os.getpgid(pid), signal.SIGCONT)
        job["status"] = "Running"
        # ensure pid->jid mapping exists
        pid_to_jid[pid] = jid
        print(f"[{jid}] {pid} continued in background")
    except Exception as e:
        print(f"bg: {e}")

# builtins dispatch table
builtins = {
    "cd": builtin_cd,
    "pwd": builtin_pwd,
    "exit": builtin_exit,
    "echo": builtin_echo,
    "clear": builtin_clear,
    "ls": builtin_ls,
    "cat": builtin_cat,
    "mkdir": builtin_mkdir,
    "rmdir": builtin_rmdir,
    "rm": builtin_rm,
    "touch": builtin_touch,
    "kill": builtin_kill,
    "jobs": builtin_jobs,
    "fg": builtin_fg,
    "bg": builtin_bg,
}

# ---- Command execution ----
def launch_external(tokens, background=False):
    """
    Launch external command. If background True, do not wait; store job.
    Use preexec_fn=os.setpgrp to create new process group so signals target job only.
    """
    cmdline = " ".join(tokens)
    try:
        proc = subprocess.Popen(tokens, preexec_fn=os.setpgrp)
    except FileNotFoundError:
        print(f"{tokens[0]}: command not found")
        return None
    except Exception as e:
        print(f"Error launching {tokens[0]}: {e}")
        return None

    if background:
        jid = add_job(proc, cmdline, status="Running")
        print(f"[{jid}] {proc.pid}")
        return proc
    else:
        # Foreground: wait until process exits or is stopped
        global foreground_pid
        foreground_pid = proc.pid
        try:
            while True:
                try:
                    wpid, status = os.waitpid(proc.pid, os.WUNTRACED)
                except InterruptedError:
                    continue
                if wpid == 0:
                    continue
                if os.WIFSTOPPED(status):
                    # stopped; create a job entry
                    jid = add_job(proc, cmdline, status="Stopped")
                    print(f"\n[{jid}] {proc.pid} Stopped")
                    break
                elif os.WIFEXITED(status):
                    break
                elif os.WIFSIGNALED(status):
                    break
        except Exception:
            pass
        foreground_pid = None
        return proc

def prune_done_jobs():
    """Remove Done/Exited entries older than TTL."""
    now = time.time()
    to_remove = []
    for jid, job in list(jobs.items()):
        status = job["status"]
        if status.startswith("Exited") or status.startswith("Signaled") or status == "Done":
            age = now - job["start_time"]
            if age > DONE_ENTRY_TTL:
                to_remove.append(jid)
    for jid in to_remove:
        jobs.pop(jid, None)

def parse_and_execute(line):
    line = line.strip()
    if not line:
        return
    try:
        tokens = shlex.split(line)
    except ValueError as e:
        print(f"Parsing error: {e}")
        return

    if not tokens:
        return

    # background handling: support 'cmd &' and 'cmd&'
    background = False
    if tokens[-1] == "&":
        background = True
        tokens = tokens[:-1]
    else:
        # check trailing & on last token (e.g., sleep 5&)
        last = tokens[-1]
        if last.endswith("&") and last != "&":
            tokens[-1] = last[:-1]
            background = True

    cmd = tokens[0]

    # built-in?
    if cmd in builtins:
        try:
            builtins[cmd](tokens[1:])
        except Exception as e:
            print(f"{cmd}: error: {e}")
        return

    # external
    launch_external(tokens, background=background)

# ---- REPL ----
def prompt():
    user = getpass.getuser() if hasattr(getpass, "getuser") else os.environ.get("USER", "")
    cwd = os.getcwd()
    base = os.path.basename(cwd) or "/"
    return f"{user}:{base}$ "

def main():
    print("myshell — Deliverable 1 shell (type 'exit' to quit).")
    try:
        while True:
            try:
                line = input(prompt())
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                # newline printed by signal handler or here
                print()
                continue
            parse_and_execute(line)
            # prune old Done entries
            prune_done_jobs()
    except SystemExit:
        pass
    except Exception as e:
        print("Shell error:", e)

if __name__ == "__main__":
    main()