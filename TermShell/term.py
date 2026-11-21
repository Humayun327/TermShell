"""
termShell.py — pure-standard-library terminal for Windows.
No pip packages. Python 3.8+.

v1.6.0 — performance edition:
  PERF 1: shell=False fast path for simple commands (no cmd.exe spawn)
  PERF 2: prompt inputs cached (no syscalls per keystroke)
  PERF 3: plugin directory + hashes cached (no re-hash at startup)
  PERF 4: builtins dispatched before tool-registry probes
  PERF 5: live-sys refreshes processes every 3rd frame
  PERF 6: launch with `python -O -S termShell.py` for fastest startup
          (or a ts.bat wrapper: @echo off & python -O -S "%~dp0termShell.py" %*)
"""

import os
import sys
import json
import stat
import time
import shutil
import ctypes
import msvcrt
import hashlib
import platform
import socket
import ssl
import subprocess
import urllib.request
import urllib.error
from urllib.parse import urlparse

# ------------------------------------------------------------------ constants
APP_NAME    = "termShell"
APP_VERSION = "1.6.0"

HISTORY_FILE   = os.path.join(os.path.expanduser("~"), ".termshell_history")
THEME_FILE     = os.path.join(os.path.expanduser("~"), ".termshell_theme")
PLUGIN_DIR     = os.path.join(os.path.expanduser("~"), ".termshell", "plugins")
PLUGIN_STATE   = os.path.join(os.path.expanduser("~"), ".termshell", "trusted.json")
MAX_HISTORY    = 500
HELP_MAX_LINES = 25

# PERF 1: characters that force a shell (pipes, redirection, chaining)
SHELL_META = set("|&<>;()")


# ---------------------------------------------------------------- ANSI
def enable_ansi():
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        mode.value |= 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode))
    except Exception:
        return False


ANSI_OK = enable_ansi()


# ---------------------------------------------------------------- themes
RESET = "\x1b[0m"
THEMES = {
    "default": {"prompt": "\x1b[1;36m", "input": "\x1b[0;37m",
                "message": "\x1b[0;32m", "error": "\x1b[1;31m"},
    "blue":    {"prompt": "\x1b[1;34m", "input": "\x1b[0;36m",
                "message": "\x1b[0;34m", "error": "\x1b[1;31m"},
    "green":   {"prompt": "\x1b[1;32m", "input": "\x1b[0;32m",
                "message": "\x1b[0;32m", "error": "\x1b[1;31m"},
    "red":     {"prompt": "\x1b[1;31m", "input": "\x1b[0;31m",
                "message": "\x1b[0;31m", "error": "\x1b[1;33m"},
    "yellow":  {"prompt": "\x1b[1;33m", "input": "\x1b[0;33m",
                "message": "\x1b[0;33m", "error": "\x1b[1;31m"},
    "magenta": {"prompt": "\x1b[1;35m", "input": "\x1b[0;35m",
                "message": "\x1b[0;35m", "error": "\x1b[1;31m"},
    "white":   {"prompt": "\x1b[1;37m", "input": "\x1b[0;97m",
                "message": "\x1b[0;97m", "error": "\x1b[1;31m"},
    "dark":    {"prompt": "\x1b[1;90m", "input": "\x1b[0;90m",
                "message": "\x1b[0;90m", "error": "\x1b[1;31m"},
    "light":   {"prompt": "\x1b[1;97m", "input": "\x1b[0;97m",
                "message": "\x1b[0;97m", "error": "\x1b[1;31m"},
    "matrix":  {"prompt": "\x1b[1;92m", "input": "\x1b[0;32m",
                "message": "\x1b[0;92m", "error": "\x1b[1;31m"},
    "sunset":  {"prompt": "\x1b[1;38;5;208m", "input": "\x1b[0;38;5;208m",
                "message": "\x1b[0;38;5;208m", "error": "\x1b[1;31m"},
    "ocean":   {"prompt": "\x1b[1;38;5;39m", "input": "\x1b[0;38;5;39m",
                "message": "\x1b[0;38;5;39m", "error": "\x1b[1;31m"},
}

CURRENT_THEME_NAME = "default"
CURRENT_THEME      = dict(THEMES["default"])


def save_theme(name):
    try:
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump({"name": name}, f)
    except OSError:
        pass


def load_theme():
    global CURRENT_THEME_NAME, CURRENT_THEME
    if os.path.exists(THEME_FILE):
        try:
            with open(THEME_FILE, "r", encoding="utf-8") as f:
                name = json.load(f).get("name", "default")
            if name in THEMES:
                CURRENT_THEME_NAME = name
                CURRENT_THEME = dict(THEMES[name])
        except Exception:
            pass


def set_theme(name):
    global CURRENT_THEME_NAME, CURRENT_THEME
    name = name.lower()
    if name not in THEMES:
        return False
    CURRENT_THEME_NAME = name
    CURRENT_THEME      = dict(THEMES[name])
    save_theme(name)
    return True


def color(kind, text):
    if not ANSI_OK:
        return text
    return CURRENT_THEME.get(kind, "") + text + RESET


def cprint(kind, text):
    print(color(kind, text))


# ---------------------------------------------------------------- helpers
def is_admin():
    try:
        if os.name == "nt":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def confirm(question):
    try:
        ans = input(color("message", question)).strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run_streaming(cmd, shell=False, cwd=None):
    try:
        proc = subprocess.Popen(
            cmd, shell=shell, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as e:
        cprint("error", f"failed to launch: {e}")
        return 1
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        cprint("error", "^C — terminated")
        return 130
    return proc.wait()


# ---------------------------------------------------------------- line editor
def read_line(prompt=""):
    if ANSI_OK:
        sys.stdout.write(CURRENT_THEME["prompt"] + prompt + RESET)
    else:
        sys.stdout.write(prompt)
    sys.stdout.flush()

    buf, cursor = [], 0
    hist_index = len(HISTORY)
    input_color = CURRENT_THEME["input"] if ANSI_OK else ""
    reset = RESET if ANSI_OK else ""

    def redraw():
        if ANSI_OK:
            sys.stdout.write("\r" + CURRENT_THEME["prompt"] + prompt + RESET
                             + input_color + "".join(buf) + reset)
        else:
            sys.stdout.write("\r" + prompt + "".join(buf))
        sys.stdout.write(" " * 4)
        back = len(buf) - cursor
        if back > 0:
            sys.stdout.write("\b" * back)
        sys.stdout.flush()

    while True:
        ch = msvcrt.getwch()

        # ---- Ctrl+R reverse search ----
        if ch == "\x12":
            matches = []
            query = ""
            idx = 0
            sys.stdout.write("\r(reverse-i-search)`': " + "\x1b[K")
            sys.stdout.flush()
            chosen = None
            while True:
                ch2 = msvcrt.getwch()
                if ch2 in ("\r", "\n"):
                    chosen = matches[idx] if matches else ""
                    break
                if ch2 == "\x1b":
                    chosen = None
                    break
                if ch2 == "\x08":
                    if query:
                        query = query[:-1]
                        matches = [c for c in reversed(HISTORY) if query in c][:50]
                        idx = 0
                elif ch2.isprintable():
                    query += ch2
                    matches = [c for c in reversed(HISTORY) if query in c][:50]
                    idx = 0
                elif ch2 in ("\x00", "\xe0"):
                    code = msvcrt.getwch()
                    if code == "H" and matches:
                        idx = (idx - 1) % len(matches)
                    elif code == "P" and matches:
                        idx = (idx + 1) % len(matches)
                disp = matches[idx] if matches else ""
                sys.stdout.write("\r(reverse-i-search)`" + query + "': "
                                 + input_color + disp + reset + "\x1b[K")
                sys.stdout.flush()
            if chosen is not None:
                buf = list(chosen)
                cursor = len(buf)
            sys.stdout.write("\r" + CURRENT_THEME["prompt"] + prompt + RESET
                             + input_color + "".join(buf) + reset + "\x1b[K")
            sys.stdout.flush()
            continue

        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            if code == "H":
                if hist_index > 0:
                    hist_index -= 1
                    buf = list(HISTORY[hist_index])
                    cursor = len(buf)
                    redraw()
            elif code == "P":
                if hist_index < len(HISTORY) - 1:
                    hist_index += 1
                    buf = list(HISTORY[hist_index])
                else:
                    hist_index = len(HISTORY)
                    buf = []
                cursor = len(buf)
                redraw()
            elif code == "K":
                if cursor > 0:
                    cursor -= 1
                    sys.stdout.write("\b")
                    sys.stdout.flush()
            elif code == "M":
                if cursor < len(buf):
                    sys.stdout.write(input_color + buf[cursor] + reset)
                    cursor += 1
                    sys.stdout.flush()
            elif code == "G":
                while cursor > 0:
                    sys.stdout.write("\b")
                    cursor -= 1
                sys.stdout.flush()
            elif code == "O":
                while cursor < len(buf):
                    sys.stdout.write(input_color + buf[cursor] + reset)
                    cursor += 1
                sys.stdout.flush()
            elif code == "S":
                if cursor < len(buf):
                    del buf[cursor]
                    redraw()
            continue

        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(buf)

        if ch == "\x03":
            sys.stdout.write("^C\n")
            sys.stdout.flush()
            return ""

        if ch == "\x04":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return None

        if ch == "\b":
            if cursor > 0:
                del buf[cursor - 1]
                cursor -= 1
                sys.stdout.write("\b" + input_color + "".join(buf[cursor:])
                                 + reset + " ")
                sys.stdout.write("\b" * (len(buf) - cursor + 1))
                sys.stdout.flush()
            continue

        if ch.isprintable() or ch == "\t":
            buf.insert(cursor, ch)
            cursor += 1
            sys.stdout.write(input_color + "".join(buf[cursor - 1:]) + reset)
            sys.stdout.flush()


# ---------------------------------------------------------------- history
HISTORY = []


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line:
                        HISTORY.append(line)
        except OSError:
            pass


def save_history():
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for line in HISTORY[-MAX_HISTORY:]:
                f.write(line + "\n")
    except OSError:
        pass


# ================================================================
#  CORE BUILT-INS
# ================================================================
def builtin_cd(args):
    target = args[0] if args else os.path.expanduser("~")
    if target == "-":
        prev = os.environ.get("OLDPWD")
        if not prev:
            cprint("error", "cd: no previous directory"); return
        target = prev
    try:
        old = os.getcwd(); os.chdir(target); os.environ["OLDPWD"] = old
    except OSError as e:
        cprint("error", f"cd: {e}")


def builtin_clear(args=None):
    os.system("cls" if os.name == "nt" else "clear")


def builtin_pwd(args=None):
    cprint("message", os.getcwd())


def builtin_history(args=None):
    for i, cmd in enumerate(HISTORY[-50:], 1):
        cprint("message", f"{i:>4}  {cmd}")


def builtin_ls(args):
    if os.name == "nt":
        translated = []
        for a in args:
            if a in ("-la", "-al", "-l", "-a"):
                translated.append("/a")
            elif a == "-h":
                continue
            else:
                translated.append(a)
        cmd = "dir " + " ".join(translated) if translated else "dir"
        run_streaming(cmd, shell=True)
        return
    ls = shutil.which("ls")
    if not ls:
        cprint("error", "ls: not found"); return
    run_streaming([ls] + args)


def builtin_mkdir(args):
    if not args:
        cprint("error", "usage: mkdir <dir> [dir...]"); return
    for path in args:
        try:
            os.makedirs(path, exist_ok=False)
            cprint("message", f"created: {path}")
        except FileExistsError:
            cprint("error", f"mkdir: already exists: {path}")
        except OSError as e:
            cprint("error", f"mkdir: {path}: {e}")


DANGEROUS_TARGETS = {"/", "\\", "C:\\", "C:/", "C:", os.path.expanduser("~")}


def _is_dangerous(path):
    norm = os.path.normpath(os.path.abspath(path))
    for t in DANGEROUS_TARGETS:
        try:
            if norm == os.path.normpath(os.path.abspath(t)):
                return True
        except Exception:
            continue
    return False


def builtin_rm(args):
    if not args:
        cprint("error", "usage: rm [-rf] <path> [path...]"); return
    recursive = False
    force = False
    paths = []
    for a in args:
        if a.startswith("-") and len(a) > 1:
            for ch in a[1:]:
                if ch == "r": recursive = True
                elif ch == "f": force = True
                else:
                    cprint("error", f"rm: unknown flag -{ch}"); return
        else:
            paths.append(a)
    if not paths:
        cprint("error", "rm: no paths given"); return
    for path in paths:
        if _is_dangerous(path):
            cprint("error", f"rm: refusing to remove '{path}' (protected path)")
            continue
        if not os.path.exists(path):
            if not force:
                cprint("error", f"rm: no such file or directory: {path}")
            continue
        if os.path.isdir(path) and not os.path.islink(path):
            if not recursive:
                cprint("error", f"rm: '{path}' is a directory (use -r or -rf)")
                continue
            if not confirm(f"remove directory '{path}' and everything inside? [y/N]: "):
                cprint("message", "aborted."); continue
            try:
                shutil.rmtree(path)
                cprint("message", f"removed directory: {path}")
            except OSError as e:
                cprint("error", f"rm: {path}: {e}")
        else:
            try:
                os.remove(path)
                cprint("message", f"removed: {path}")
            except OSError as e:
                cprint("error", f"rm: {path}: {e}")


CAT_MAX_BYTES = 2 * 1024 * 1024


def builtin_cat(args):
    if not args:
        cprint("error", "usage: cat <file> [file...] [--force]"); return
    force = "--force" in args
    paths = [a for a in args if a != "--force"]
    if not paths:
        cprint("error", "cat: no files given"); return
    for path in paths:
        if not os.path.isfile(path):
            cprint("error", f"cat: {path}: not a file"); continue
        try:
            size = os.path.getsize(path)
            if size > CAT_MAX_BYTES and not force:
                cprint("error", f"cat: {path} is {size} bytes (> {CAT_MAX_BYTES}).")
                cprint("message", "  use `cat --force <file>` or a pager.")
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                sys.stdout.write(f.read())
            try:
                with open(path, "rb") as fb:
                    fb.seek(-1, os.SEEK_END)
                    if fb.read(1) != b"\n":
                        print()
            except OSError:
                print()
        except OSError as e:
            cprint("error", f"cat: {path}: {e}")


def builtin_ping(args):
    if not args:
        cprint("error", "usage: ping <host> [-n count]"); return
    host = args[0]
    rest = args[1:]
    ping = shutil.which("ping")
    if not ping:
        cprint("error", "ping: not found on PATH"); return
    if os.name == "nt":
        if "-n" not in rest:
            rest = ["-n", "4"] + rest
    else:
        if "-c" not in rest:
            rest = ["-c", "4"] + rest
    run_streaming([ping] + rest + [host])


def builtin_netstat(args):
    netstat = shutil.which("netstat")
    if not netstat:
        cprint("error", "netstat: not found on PATH"); return
    if os.name == "nt":
        linux_flags = ("-tulpn", "-tuln", "-tulp", "-tupn")
        if any(a in linux_flags for a in args) or not args:
            cmd = [netstat, "-a", "-n", "-o"]
        else:
            cmd = [netstat] + args
    else:
        cmd = [netstat] + (["-tulpn"] if not args else args)
    run_streaming(cmd)


def builtin_ss(args):
    if os.name != "nt":
        ss = shutil.which("ss")
        if ss:
            run_streaming([ss] + args); return
    cprint("message", "[ss] falling back to native netstat on this system.")
    builtin_netstat(["-tulpn"] if not args else args)


def builtin_wget(args):
    if not args:
        cprint("error", "usage: wget <url> [filename]"); return
    builtin_get(args)


def builtin_which(args):
    if not args:
        cprint("error", "usage: which <command> [command...]"); return
    for name in args:
        resolved = shutil.which(name)
        if resolved:
            cprint("message", f"{resolved}")
        else:
            cprint("error", f"{name}: not found on PATH")


def builtin_whoami(args=None):
    user, host = get_user_host()
    cprint("message", f"user:  {user}")
    cprint("message", f"host:  {host}")
    cprint("message", f"admin: {'yes' if is_admin() else 'no'}")
    cprint("message", f"cwd:   {os.getcwd()}")


def builtin_man(args):
    if not args:
        cprint("error", "usage: man <tool>"); return
    tool = args[0]
    resolved = shutil.which(tool)
    if not resolved:
        cprint("error", f"man: {tool}: not found on PATH"); return
    if os.name != "nt":
        man = shutil.which("man")
        if man:
            run_streaming([man, tool]); return
    try:
        r = subprocess.run([resolved, "--help"], capture_output=True,
                           text=True, timeout=15)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        lines = [ln for ln in out.splitlines() if ln.strip()]
        if not lines:
            cprint("error", f"man: {tool}: no help output"); return
        cprint("message", f"{tool} — help (showing {min(len(lines), HELP_MAX_LINES)} of {len(lines)} lines)")
        cprint("message", "-" * 48)
        for ln in lines[:HELP_MAX_LINES]:
            print("  " + ln)
        if len(lines) > HELP_MAX_LINES:
            cprint("message", f"  ... ({len(lines) - HELP_MAX_LINES} more lines)")
    except (subprocess.TimeoutExpired, OSError) as e:
        cprint("error", f"man: {tool}: {e}")


def builtin_chmod(args):
    if not args:
        cprint("error", "usage: chmod +x <file>   (or chmod 755 <file> on POSIX)"); return
    mode_arg = args[0]
    paths = args[1:]
    if not paths:
        cprint("error", "chmod: no file given"); return
    if os.name == "nt":
        cprint("message", "chmod: executable bits do not exist on Windows.")
        cprint("message", "  - .sh files: run with `bash file.sh` (Git Bash / WSL).")
        cprint("message", "  - to grant full ACL to your user, run:")
        for p in paths:
            cprint("message", f"      icacls \"{p}\" /grant %USERNAME%:F")
        return
    try:
        if mode_arg in ("+x", "a+x", "u+x", "g+x", "o+x"):
            for p in paths:
                st = os.stat(p)
                os.chmod(p, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                cprint("message", f"chmod +x: {p}")
        else:
            try:
                mode = int(mode_arg, 8)
            except ValueError:
                cprint("error", f"chmod: invalid mode: {mode_arg}"); return
            for p in paths:
                os.chmod(p, mode)
                cprint("message", f"chmod {mode_arg}: {p}")
    except OSError as e:
        cprint("error", f"chmod: {e}")


def builtin_chown(args):
    if len(args) < 2:
        cprint("error", "usage: chown <user>[:group] <file>   (POSIX only)"); return
    if os.name == "nt":
        cprint("message", "chown: Windows does not use POSIX ownership.")
        cprint("message", "  use `takeown` and `icacls` from an elevated prompt:")
        for p in args[1:]:
            cprint("message", f"      takeown /f \"{p}\"")
            cprint("message", f"      icacls \"{p}\" /grant %USERNAME%:F")
        return
    owner = args[0]
    try:
        import pwd, grp
        user, group = (owner.split(":", 1) + [None])[:2]
        uid = pwd.getpwnam(user).pw_uid if user else -1
        gid = grp.getgrnam(group).gr_gid if group else -1
        for p in args[1:]:
            os.chown(p, uid, gid)
            cprint("message", f"chown {owner}: {p}")
    except (KeyError, PermissionError, OSError) as e:
        cprint("error", f"chown: {e}")


def builtin_sudo(args):
    if not args:
        cprint("error", "usage: sudo <command> [args...]"); return
    if os.name != "nt":
        cprint("error", "sudo: run the system sudo/su from a real terminal."); return
    cmdline = subprocess.list2cmdline(args)
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", f"/k {cmdline}", None, 1
        )
    except Exception as e:
        cprint("error", f"sudo: failed to launch elevated process ({e})"); return
    if rc <= 32:
        if rc == 5:
            cprint("error", "sudo: elevation cancelled by user (UAC declined).")
        else:
            cprint("error", f"sudo: ShellExecuteW failed (code {rc}).")
        return
    cprint("message", "sudo: launched elevated console (UAC prompt should appear).")


def builtin_su(args=None):
    if os.name == "nt":
        cprint("error", "su: POSIX-only. On Windows use:")
        cprint("message", "  runas /user:<username> cmd")
        cprint("message", "or open an elevated terminal (right-click → Run as administrator).")
        cprint("message", "Password prompts are unsafe in this raw-mode line editor.")
    else:
        cprint("error", "su: run from a real POSIX terminal (password prompt is unsafe here).")


def builtin_scan(args):
    ports = []
    if args:
        for a in args:
            try:
                ports.append(int(a))
            except ValueError:
                cprint("error", f"scan: '{a}' is not a port number"); return
    else:
        ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
                 3000, 3306, 3389, 5000, 5432, 6379, 8000, 8080, 8443, 9000]
    host = "127.0.0.1"
    cprint("message", f"[scan] localhost ({host}) — {len(ports)} port(s)")
    open_ports = []
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            if s.connect_ex((host, p)) == 0:
                open_ports.append(p)
                cprint("message", f"  {p:>5}  OPEN")
        except OSError:
            pass
        finally:
            s.close()
    if not open_ports:
        cprint("message", "[scan] no open ports on 127.0.0.1 among the checked set.")
    else:
        cprint("message", f"[scan] {len(open_ports)} open: {open_ports}")


WEBTEST_ALLOWED_LOCAL = {"localhost", "127.0.0.1", "::1"}


def builtin_webtest(args):
    if not args:
        cprint("error", "usage: webtest <http://localhost:PORT/...>"); return
    url = args[0]
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        cprint("error", "webtest: could not parse host from URL"); return
    if host not in WEBTEST_ALLOWED_LOCAL:
        cprint("error", f"webtest: refusing non-local target '{host}'.")
        cprint("message", "  webtest is localhost-only by design.")
        cprint("message", "  for remote targets use:  curl -I <url>")
        return
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            body = r.read(2048)
            cprint("message", f"status:  {r.status} {r.reason}")
            cprint("message", f"final:   {r.geturl()}")
            cprint("message", f"server:  {r.headers.get('Server', '(none)')}")
            cprint("message", f"ctype:   {r.headers.get('Content-Type', '(none)')}")
            cprint("message", f"length:  {r.headers.get('Content-Length', '(none)')}")
            if url.startswith("https://"):
                cprint("message", "tls:     established")
            cprint("message", "--- first 2 KB of body ---")
            sys.stdout.buffer.write(body)
            print()
    except urllib.error.HTTPError as e:
        cprint("error", f"HTTP {e.code} {e.reason}")
        for k, v in e.headers.items():
            cprint("message", f"  {k}: {v}")
    except urllib.error.URLError as e:
        cprint("error", f"webtest: connection failed ({e.reason})")
    except Exception as e:
        cprint("error", f"webtest: {e}")


def builtin_get(args):
    if not args:
        cprint("error", "usage: get <url> [filename]"); return
    url = args[0]
    filename = args[1] if len(args) > 1 else None
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        cprint("error", "get: curl.exe not found on PATH"); return
    cmd = [curl, "-L", "-C", "-", "--retry", "10", "--retry-delay", "5"]
    cmd += (["-o", filename] if filename else ["-O"])
    cmd.append(url)
    cprint("message", f"[get] {' '.join(cmd)}")
    cprint("message", "[get] if interrupted, run the same command again to resume.")
    run_streaming(cmd)


def builtin_theme(args):
    if not args:
        cprint("message", f"current theme: {CURRENT_THEME_NAME}")
        cprint("message", "available: " + ", ".join(sorted(THEMES.keys()))); return
    name = args[0].lower()
    if name == "list":
        cprint("message", "available themes:")
        for t in sorted(THEMES.keys()):
            marker = " *" if t == CURRENT_THEME_NAME else ""
            cprint("message", f"  {t}{marker}")
        return
    if name == "reset": name = "default"
    if set_theme(name):
        cprint("message", f"theme set to '{name}'")
    else:
        cprint("error", f"unknown theme: '{name}'")
        cprint("error", "available: " + ", ".join(sorted(THEMES.keys())))


def builtin_clone(args):
    if not args:
        cprint("error", "usage: clone <url> [dir] [--full]"); return
    full = "--full" in args
    args = [a for a in args if a != "--full"]
    url = args[0]
    git = shutil.which("git")
    if not git:
        cprint("error", "clone: git not found on PATH")
        cprint("message", "install Git from https://git-scm.com/download/win"); return
    if len(args) >= 2:
        target = args[1]
    else:
        base = url.rstrip("/").split("/")[-1]
        if base.endswith(".git"): base = base[:-4]
        target = base or "repo"
    exists = os.path.isdir(target) and os.path.isdir(os.path.join(target, ".git"))
    if exists:
        cprint("message", f"[clone] '{target}' exists — fetching + pulling to resume")
        rc = run_streaming([git, "-C", target, "fetch", "--all", "--prune"])
        if rc != 0:
            cprint("error", f"[clone] fetch failed ({rc})"); return
        rc = run_streaming([git, "-C", target, "pull", "--ff-only"])
        if rc != 0:
            cprint("error", f"[clone] pull failed ({rc}) — resolve manually"); return
        cprint("message", f"[clone] updated '{target}'")
        return
    cmd = [git, "clone", "--progress"]
    if not full: cmd += ["--depth", "1"]
    cmd += [url, target]
    cprint("message", f"[clone] {' '.join(cmd)}")
    cprint("message", "[clone] if interrupted, rerun the same command to resume.")
    rc = run_streaming(cmd)
    if rc != 0:
        cprint("error", f"[clone] failed ({rc})"); return
    cprint("message", f"[clone] done → {os.path.abspath(target)}")


def builtin_runpy(args):
    if not args:
        cprint("error", "usage: runpy <file.py> [args...]"); return
    path = args[0]
    rest = args[1:]
    if not os.path.isfile(path):
        cprint("error", f"runpy: file not found: {path}"); return
    try:
        preview_lines = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip(): preview_lines.append(line.rstrip("\n"))
                if len(preview_lines) >= 5: break
    except OSError as e:
        cprint("error", f"runpy: could not read file ({e})"); return
    size = os.path.getsize(path)
    cprint("message", f"[runpy] {os.path.abspath(path)}  ({size} bytes)")
    cprint("message", "--- first 5 non-empty lines ---")
    for ln in preview_lines: print("  " + ln)
    cprint("message", "-------------------------------")
    if not confirm("run this file? [y/N]: "):
        cprint("message", "aborted — nothing executed."); return
    run_streaming([sys.executable, path] + rest)


def builtin_hashfile(args):
    if not args:
        cprint("error", "usage: hashfile <path> [expected_sha256]"); return
    path = args[0]
    expected = args[1].lower() if len(args) > 1 else None
    if not os.path.isfile(path):
        cprint("error", f"hashfile: file not found: {path}"); return
    sha = hashlib.sha256(); md5 = hashlib.md5(); size = 0
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                size += len(chunk); sha.update(chunk); md5.update(chunk)
    except OSError as e:
        cprint("error", f"hashfile: could not read file ({e})"); return
    sha_hex = sha.hexdigest(); md5_hex = md5.hexdigest()
    cprint("message", f"file:    {os.path.abspath(path)}")
    cprint("message", f"size:    {size} bytes")
    cprint("message", f"sha256:  {sha_hex}")
    cprint("message", f"md5:     {md5_hex}")
    if expected:
        if expected == sha_hex:
            cprint("message", "match:   YES (sha256 matches expected)")
        else:
            cprint("error",   "match:   NO  (sha256 does NOT match expected)")


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def builtin_ports(args):
    if len(args) < 2:
        cprint("error", "usage: ports <host> <port> [--i-own-this-host]"); return
    host = args[0]
    try:
        port = int(args[1])
    except ValueError:
        cprint("error", "ports: port must be an integer"); return
    if not (1 <= port <= 65535):
        cprint("error", "ports: port must be 1–65535"); return
    flag = "--i-own-this-host" in args
    is_local = host.lower() in LOCAL_HOSTS
    if not is_local and not flag:
        cprint("error", "ports: refusing to scan a non-local host.")
        cprint("message", "  Only localhost/127.0.0.1/::1 are allowed by default.")
        cprint("message", f"  If authorized, rerun:  ports {host} {port} --i-own-this-host")
        return
    if not is_local:
        cprint("message", "REMINDER: you are asserting you own or are authorized")
        cprint("message", f"to test '{host}'. Unauthorized scanning is illegal.")
    try:
        with socket.create_connection((host, port), timeout=5):
            cprint("message", f"{host}:{port}  OPEN")
    except socket.timeout:
        cprint("error", f"{host}:{port}  TIMEOUT (5s)")
    except ConnectionRefusedError:
        cprint("error", f"{host}:{port}  CLOSED (refused)")
    except socket.gaierror as e:
        cprint("error", f"{host}:{port}  DNS FAILED ({e})")
    except OSError as e:
        cprint("error", f"{host}:{port}  ERROR ({e})")


def builtin_ai(args):
    if not args:
        cprint("error", "usage: ai <prompt> [--model <name>]")
        return
    model = "llama3.2"
    prompt_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        else:
            prompt_parts.append(args[i])
            i += 1
    prompt = " ".join(prompt_parts)
    if not prompt:
        cprint("error", "ai: no prompt given")
        return
    url = "http://localhost:11434/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    cprint("message", f"[ai] {model} → {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("response", "")
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                if obj.get("done"):
                    break
            print()
    except urllib.error.URLError as e:
        cprint("error", f"ai: cannot reach Ollama at localhost:11434 ({e.reason})")
        cprint("message", "  is Ollama installed and running? try: ollama list")
    except Exception as e:
        cprint("error", f"ai: {e}")


# ================================================================
#  live-sys  — live system monitor
# ================================================================
def _get_cpu_times():
    if os.name == "nt":
        try:
            idle = ctypes.c_ulonglong()
            kernel = ctypes.c_ulonglong()
            user = ctypes.c_ulonglong()
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            )
            i = idle.value
            t = kernel.value + user.value + idle.value
            return i, t
        except Exception:
            return 0, 0
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = [int(x) for x in line.split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        return idle, total
    except Exception:
        return 0, 0


def _get_mem():
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total = stat.ullTotalPhys
            used = total - stat.ullAvailPhys
            return used, total
        except Exception:
            return None, None
    try:
        total = avail = None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024
        if total is not None and avail is not None:
            return total - avail, total
    except Exception:
        pass
    return None, None


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _list_processes(limit=8):
    procs = []
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 5:
                    name = parts[0]
                    pid = parts[1]
                    mem = parts[4].replace(",", "").replace(" K", "").strip()
                    try:
                        mem_kb = int(mem)
                    except ValueError:
                        mem_kb = 0
                    procs.append((pid, name, mem_kb))
        except Exception:
            pass
    else:
        try:
            r = subprocess.run(["ps", "-eo", "pid,rss,comm", "--no-headers"],
                               capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                parts = line.split(None, 2)
                if len(parts) == 3:
                    pid, rss_kb, name = parts
                    try:
                        procs.append((pid, name, int(rss_kb)))
                    except ValueError:
                        pass
        except Exception:
            pass
    procs.sort(key=lambda p: p[2], reverse=True)
    return procs[:limit]


def builtin_live_sys(args):
    interval = 1.0
    if args:
        try:
            interval = max(0.5, float(args[0]))
        except ValueError:
            cprint("error", "live-sys: interval must be a number (seconds)")
            return
    if not ANSI_OK:
        cprint("error", "live-sys: requires ANSI (VT processing) — not available.")
        return
    cprint("message", "[live-sys] live monitor — press any key to exit")
    time.sleep(0.4)
    prev_idle, prev_total = _get_cpu_times()
    cpu_pct = 0.0
    frame = 0
    cached_procs = []
    proc_refresh_every = 3   # PERF 5: refresh process list every 3rd frame
    sys.stdout.write("\x1b[2J\x1b[?25l")
    sys.stdout.flush()
    try:
        while True:
            if msvcrt.kbhit():
                msvcrt.getwch()
                break
            idle, total = _get_cpu_times()
            if total > prev_total:
                d_idle = idle - prev_idle
                d_total = total - prev_total
                if d_total > 0:
                    cpu_pct = 100.0 * (1.0 - d_idle / d_total)
            prev_idle, prev_total = idle, total
            mem_used, mem_total = _get_mem()
            disk_total, disk_used, disk_free = shutil.disk_usage(os.getcwd())
            if frame % proc_refresh_every == 0 or not cached_procs:
                cached_procs = _list_processes(8)
            procs = cached_procs
            user, host = get_user_host()
            frame += 1
            lines = []
            lines.append(f"{APP_NAME} live-sys   frame {frame}   {interval:.1f}s refresh")
            lines.append("=" * 68)
            lines.append(f"user@host:  {user}@{host}")
            lines.append(f"python:     {sys.version.split()[0]}")
            lines.append(f"platform:   {platform.platform()}")
            lines.append("")
            bar_w = 40
            filled = int(cpu_pct / 100.0 * bar_w)
            cpu_bar = "█" * filled + "░" * (bar_w - filled)
            lines.append(f"CPU    [{cpu_bar}] {cpu_pct:5.1f}%")
            if mem_total:
                mem_pct = 100.0 * mem_used / mem_total
                filled = int(mem_pct / 100.0 * bar_w)
                mem_bar = "█" * filled + "░" * (bar_w - filled)
                lines.append(f"MEM    [{mem_bar}] {mem_pct:5.1f}%  "
                             f"({_fmt_bytes(mem_used)} / {_fmt_bytes(mem_total)})")
            else:
                lines.append("MEM    (unavailable)")
            if disk_total:
                disk_pct = 100.0 * disk_used / disk_total
                filled = int(disk_pct / 100.0 * bar_w)
                disk_bar = "█" * filled + "░" * (bar_w - filled)
                lines.append(f"DISK   [{disk_bar}] {disk_pct:5.1f}%  "
                             f"({_fmt_bytes(disk_used)} / {_fmt_bytes(disk_total)}  cwd)")
            lines.append("")
            lines.append("Top processes (by memory):")
            lines.append(f"  {'PID':<8} {'NAME':<30} {'MEM':>10}")
            for pid, name, mem_kb in procs:
                name_short = name if len(name) <= 30 else name[:27] + "..."
                lines.append(f"  {pid:<8} {name_short:<30} {_fmt_bytes(mem_kb * 1024):>10}")
            lines.append("")
            lines.append("press any key to exit")
            sys.stdout.write("\x1b[H")
            sys.stdout.write("\n".join(lines))
            sys.stdout.write("\x1b[J")
            sys.stdout.flush()
            time.sleep(interval)
    finally:
        sys.stdout.write("\x1b[?25h\x1b[2J\x1b[H")
        sys.stdout.flush()
        cprint("message", "[live-sys] exited")


# ================================================================
#  PLUGIN SYSTEM  — confirmed-load, hash-pinned
# ================================================================
LOADED_PLUGINS = {}
_PLUGIN_CACHE = None   # PERF 3: (path, name, hash) cache


def _ensure_plugin_dir():
    try:
        os.makedirs(PLUGIN_DIR, exist_ok=True)
    except OSError:
        pass


def _load_trusted():
    if os.path.exists(PLUGIN_STATE):
        try:
            with open(PLUGIN_STATE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_trusted(d):
    try:
        os.makedirs(os.path.dirname(PLUGIN_STATE), exist_ok=True)
        with open(PLUGIN_STATE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except OSError:
        pass


def _hash_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# PERF 3: cached plugin scan
def _scan_plugins_cached():
    global _PLUGIN_CACHE
    if _PLUGIN_CACHE is not None:
        return _PLUGIN_CACHE
    _ensure_plugin_dir()
    out = []
    try:
        for n in os.listdir(PLUGIN_DIR):
            if n.endswith(".py") and not n.startswith("_"):
                p = os.path.join(PLUGIN_DIR, n)
                out.append((p, os.path.splitext(n)[0], _hash_file(p)))
    except OSError:
        pass
    _PLUGIN_CACHE = sorted(out, key=lambda x: x[0])
    return _PLUGIN_CACHE


def _invalidate_plugin_cache():
    global _PLUGIN_CACHE
    _PLUGIN_CACHE = None


def _plugin_files():
    return [p for (p, _n, _h) in _scan_plugins_cached()]


def _plugin_name(path):
    return os.path.splitext(os.path.basename(path))[0]


def load_plugin(path, confirm_hash=True):
    name = _plugin_name(path)
    if not os.path.isfile(path):
        cprint("error", f"plugin: not a file: {path}")
        return False
    file_hash = _hash_file(path)
    if file_hash is None:
        cprint("error", f"plugin: could not hash {path}")
        return False
    trusted = _load_trusted()
    known = trusted.get(name)
    if confirm_hash and known != file_hash:
        cprint("message", f"[plugin] untrusted: {name}")
        cprint("message", f"  file:   {os.path.abspath(path)}")
        cprint("message", f"  sha256: {file_hash}")
        cprint("message", "  --- first 8 non-empty lines ---")
        try:
            shown = 0
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        print("  " + line.rstrip("\n"))
                        shown += 1
                        if shown >= 8:
                            break
        except OSError:
            pass
        cprint("message", "  ---------------------------------")
        cprint("message", "  Plugins run with the same privileges as termShell.")
        cprint("message", "  A plugin can read/write/delete anything you can.")
        if not confirm("  trust and load this plugin? [y/N]: "):
            cprint("message", "plugin not loaded.")
            return False
        trusted[name] = file_hash
        _save_trusted(trusted)
    ns = {
        "__name__": f"termshell_plugin_{name}",
        "__file__": os.path.abspath(path),
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        exec(compile(code, path, "exec"), ns)
    except Exception as e:
        cprint("error", f"plugin '{name}': execution failed: {e}")
        return False
    reg = ns.get("register_builtins")
    if not callable(reg):
        cprint("error", f"plugin '{name}': missing register_builtins()")
        return False
    try:
        extra = reg()
    except Exception as e:
        cprint("error", f"plugin '{name}': register_builtins() raised: {e}")
        return False
    if not isinstance(extra, dict):
        cprint("error", f"plugin '{name}': register_builtins() must return dict")
        return False
    collisions = [k for k in extra if k in BUILTINS]
    if collisions:
        cprint("error", f"plugin '{name}': refusing to shadow built-ins: "
                        + ", ".join(collisions))
        return False
    BUILTINS.update(extra)
    LOADED_PLUGINS[name] = {"path": path, "commands": list(extra.keys())}
    cprint("message", f"[plugin] loaded '{name}' — commands: "
                      + ", ".join(extra.keys()))
    return True


def builtin_plugins(args):
    _ensure_plugin_dir()
    if not args or args[0] == "list":
        files = _scan_plugins_cached()
        cprint("message", f"plugin dir: {PLUGIN_DIR}")
        if not files:
            cprint("message", "  (no plugin files)")
            return
        for path, name, _h in files:
            status = "LOADED" if name in LOADED_PLUGINS else "available"
            cprint("message", f"  {name:<20} {status}")
        return
    sub = args[0].lower()
    if sub == "dir":
        print(PLUGIN_DIR); return
    if sub == "load" and len(args) >= 2:
        name = args[1]
        path = os.path.join(PLUGIN_DIR, name + ".py")
        load_plugin(path)
        _invalidate_plugin_cache()
        return
    if sub == "load-all":
        for path in _plugin_files():
            name = _plugin_name(path)
            if name in LOADED_PLUGINS:
                cprint("message", f"[plugin] '{name}' already loaded")
                continue
            load_plugin(path)
        _invalidate_plugin_cache()
        return
    if sub == "unload" and len(args) >= 2:
        name = args[1]
        if name not in LOADED_PLUGINS:
            cprint("error", f"plugin '{name}' is not loaded")
            return
        for cmd in LOADED_PLUGINS[name]["commands"]:
            BUILTINS.pop(cmd, None)
        del LOADED_PLUGINS[name]
        cprint("message", f"plugin '{name}' unloaded")
        return
    if sub == "info" and len(args) >= 2:
        name = args[1]
        path = os.path.join(PLUGIN_DIR, name + ".py")
        if not os.path.isfile(path):
            cprint("error", f"plugin '{name}': not found")
            return
        h = _hash_file(path) or "(unknown)"
        trusted = _load_trusted().get(name)
        cprint("message", f"name:     {name}")
        cprint("message", f"path:     {os.path.abspath(path)}")
        cprint("message", f"sha256:   {h}")
        cprint("message", f"trusted:  {'yes' if trusted == h else 'no'}")
        if name in LOADED_PLUGINS:
            cprint("message", "commands: " + ", ".join(LOADED_PLUGINS[name]["commands"]))
        return
    cprint("error", "usage: plugins [list|load <name>|load-all|unload <name>|info <name>|dir]")


# ---------------------------------------------------------------- BUILTINS
BUILTINS = {
    "cd":       builtin_cd,
    "clear":    builtin_clear,
    "cls":      builtin_clear,
    "pwd":      builtin_pwd,
    "history":  builtin_history,
    "ls":       builtin_ls,
    "mkdir":    builtin_mkdir,
    "rm":       builtin_rm,
    "cat":      builtin_cat,
    "ping":     builtin_ping,
    "netstat":  builtin_netstat,
    "ss":       builtin_ss,
    "wget":     builtin_wget,
    "which":    builtin_which,
    "whoami":   builtin_whoami,
    "man":      builtin_man,
    "chmod":    builtin_chmod,
    "chown":    builtin_chown,
    "sudo":     builtin_sudo,
    "su":       builtin_su,
    "scan":     builtin_scan,
    "webtest":  builtin_webtest,
    "get":      builtin_get,
    "theme":    builtin_theme,
    "clone":    builtin_clone,
    "runpy":    builtin_runpy,
    "hashfile": builtin_hashfile,
    "ports":    builtin_ports,
    "live-sys": builtin_live_sys,
    "plugins":  builtin_plugins,
    "ai":       builtin_ai,
    "exit":     None,
    "quit":     None,
}


# ================================================================
#  TOOL REGISTRY
# ================================================================
VERSION_TOOLS = {
    "python": ("python", "Python"), "python3": ("python", "Python"),
    "py": ("py", "Python Launcher"), "pip": ("pip", "pip"), "pip3": ("pip", "pip"),
    "node": ("node", "Node.js"), "npm": ("npm", "npm"), "npx": ("npx", "npx"),
    "deno": ("deno", "Deno"), "bun": ("bun", "Bun"),
    "java": ("java", "Java"), "javac": ("javac", "javac"),
    "kotlin": ("kotlin", "Kotlin"), "kotlinc": ("kotlinc", "Kotlin compiler"),
    "scala": ("scala", "Scala"), "groovy": ("groovy", "Groovy"),
    "go": ("go", "Go"), "gcc": ("gcc", "GCC"), "g++": ("g++", "G++"),
    "clang": ("clang", "Clang"), "clang++": ("clang++", "Clang++"),
    "rustc": ("rustc", "Rust"), "cargo": ("cargo", "Cargo"),
    "rustup": ("rustup", "rustup"), "dotnet": ("dotnet", ".NET"),
    "ruby": ("ruby", "Ruby"), "gem": ("gem", "RubyGems"),
    "perl": ("perl", "Perl"), "php": ("php", "PHP"),
    "composer": ("composer", "Composer"),
    "lua": ("lua", "Lua"), "luajit": ("luajit", "LuaJIT"),
    "rscript": ("Rscript", "Rscript"), "julia": ("julia", "Julia"),
    "swift": ("swift", "Swift"), "dart": ("dart", "Dart"),
    "flutter": ("flutter", "Flutter"), "elixir": ("elixir", "Elixir"),
    "erl": ("erl", "Erlang"), "clojure": ("clojure", "Clojure"),
    "lein": ("lein", "Leiningen"), "zig": ("zig", "Zig"),
    "nim": ("nim", "Nim"), "crystal": ("crystal", "Crystal"),
    "ghc": ("ghc", "GHC"), "stack": ("stack", "Stack"),
    "cabal": ("cabal", "Cabal"), "git": ("git", "Git"),
    "docker": ("docker", "Docker"), "kubectl": ("kubectl", "kubectl"),
    "terraform": ("terraform", "Terraform"), "make": ("make", "GNU Make"),
    "cmake": ("cmake", "CMake"), "curl": ("curl", "cURL"), "wget": ("wget", "wget"),
    "ollama": ("ollama", "Ollama"),
}

VERSION_FLAGS = ("--version", "-V", "-v", "version")
HELP_FLAGS    = ("--help", "-h", "help")


def _first_nonempty_line(text):
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def check_version(command, extra_args):
    if len(extra_args) != 1 or extra_args[0] not in VERSION_FLAGS:
        return False
    key = command.lower()
    exe, label = VERSION_TOOLS.get(key, (command, command))
    resolved = shutil.which(exe)
    if resolved is None:
        cprint("error", f"{label}: not installed (could not find '{exe}' on PATH)")
        cprint("message", "hint: install it, or check your PATH.")
        return True
    for flag in VERSION_FLAGS:
        try:
            result = subprocess.run([resolved, flag], capture_output=True,
                                    text=True, timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            continue
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        if output:
            cprint("message", f"{label}: {_first_nonempty_line(output)}")
            return True
    cprint("error", f"{label}: found but printed no version info.")
    return True


def check_help(command, extra_args):
    if len(extra_args) != 1 or extra_args[0] not in HELP_FLAGS:
        return False
    key = command.lower()
    exe, label = VERSION_TOOLS.get(key, (command, command))
    resolved = shutil.which(exe)
    if resolved is None:
        cprint("error", f"{label}: not installed (could not find '{exe}' on PATH)")
        return True
    for flag in HELP_FLAGS:
        try:
            result = subprocess.run([resolved, flag], capture_output=True,
                                    text=True, timeout=15)
        except (subprocess.TimeoutExpired, OSError):
            continue
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        if not output:
            continue
        lines = [ln for ln in output.splitlines() if ln.strip()]
        snippet = lines[:HELP_MAX_LINES]; total = len(lines)
        cprint("message", f"{label} — help (showing {len(snippet)} of {total} lines)")
        cprint("message", "-" * 48)
        for ln in snippet:
            print("  " + ln)
        if total > len(snippet):
            cprint("message", f"  ... ({total - len(snippet)} more lines)")
        return True
    cprint("error", f"{label}: found but printed no help output.")
    return True


# ================================================================
#  --help / --version
# ================================================================
def show_shell_help():
    cprint("message", f"{APP_NAME} — command reference")
    cprint("message", "=" * 64)
    rows = [
        ("cd [dir]",                "change directory  (cd - goes back)"),
        ("pwd",                     "print working directory"),
        ("ls [flags/path]",         "list directory (delegates to dir/ls)"),
        ("mkdir <dir...>",          "create directories"),
        ("rm [-rf] <path...>",      "remove files; dirs need -r; confirms; guards / and ~"),
        ("cat <file> [--force]",    "print file (2 MB guard)"),
        ("clear / cls / --clear",   "clear the screen"),
        ("history",                 "show last 50 commands"),
        ("theme <name>",            "set theme"),
        ("<color> thm",             "shortcut: blue thm | green thm | ..."),
        ("list thm / reset thm",    "list themes / reset to default"),
        ("get <url> [file]",        "resumable download via curl -C -"),
        ("wget <url> [file]",       "alias for get"),
        ("clone <url> [dir]",       "shallow, resumable git clone (--full for history)"),
        ("ping <host>",             "native ping (streams live)"),
        ("netstat [-tulpn]",        "native netstat (Linux flags translated)"),
        ("ss [-tulpn]",             "ss if available, else netstat"),
        ("which <cmd...>",          "locate on PATH"),
        ("whoami",                  "user, host, admin status"),
        ("man <tool>",              "tool help (bounded snippet)"),
        ("chmod +x <file>",         "exec bit (POSIX) / icacls hint (Windows)"),
        ("chown <user> <file>",     "POSIX only; Windows hint"),
        ("sudo <cmd>",              "run in a new elevated console (UAC prompt)"),
        ("su",                      "POSIX-only notice"),
        ("scan [ports...]",         "localhost port scan (127.0.0.1 only)"),
        ("webtest <url>",           "HTTP check — localhost only"),
        ("runpy <file.py> [args]",  "preview + confirm, then run"),
        ("hashfile <path> [sha]",   "SHA-256 + MD5"),
        ("ports <host> <port>",     "single TCP check; localhost unless --i-own-this-host"),
        ("ai <prompt> [--model m]", "query local Ollama and stream the reply"),
        ("live-sys [interval]",     "live CPU/mem/disk/process monitor"),
        ("plugins [list|load|...]", "manage plugins (confirmed-load, hash-pinned)"),
        ("<tool> --version",        "python/node/gcc/ollama/... version check"),
        ("<tool> --help",           "tool help (bounded snippet)"),
        ("--version",               "termShell version"),
        ("--help",                  "this screen"),
        ("--doctor",                "PATH health report"),
        ("--doctor --fix",          "propose installs for missing tools"),
        ("--secscan",               "detect security tools + official links"),
        ("--no-plugins",            "startup flag: skip auto-loading trusted plugins"),
        ("exit / quit",             "leave termShell (or Ctrl+D)"),
    ]
    for cmd, desc in rows:
        cprint("message", f"  {cmd:<24} {desc}")
    cprint("message", "")
    cprint("message", "themes: " + ", ".join(sorted(THEMES.keys())))
    cprint("message", "line editing: ←/→ move, Home/End, Del, ↑/↓ history, Ctrl+R search, Ctrl+C cancel")


def show_shell_version():
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = f"{platform.system()} {platform.release()}"
    ansi = "on" if ANSI_OK else "off"
    cprint("message", f"{APP_NAME} {APP_VERSION}  (pure-stdlib terminal)")
    cprint("message", f"Python {py}  •  {os_name}  •  ANSI: {ansi}")


# ================================================================
#  --doctor / --doctor --fix
# ================================================================
DOCTOR_GROUPS = {
    "Languages": [
        "python", "python3", "node", "deno", "bun", "java", "javac",
        "go", "gcc", "g++", "clang", "clang++", "rustc", "cargo",
        "ruby", "perl", "php", "lua", "julia", "swift", "dart",
        "elixir", "erl", "clojure", "zig", "nim", "crystal", "ghc",
        "dotnet", "kotlin", "kotlinc", "scala", "groovy",
    ],
    "Package managers": [
        "pip", "pip3", "npm", "npx", "gem", "composer", "lein",
        "stack", "cabal", "rustup", "flutter",
    ],
    "Build & tools": [
        "make", "cmake", "git", "docker", "kubectl", "terraform",
        "curl", "wget", "rscript", "py",
    ],
    "AI runtimes": [
        "ollama",
    ],
}

FIX_RECIPES = {
    "python":     {"winget": "Python.Python.3.12", "choco": "python",   "scoop": "python"},
    "pip":        {"pip":   "pip"},
    "node":       {"winget": "OpenJS.NodeJS.LTS",  "choco": "nodejs",  "scoop": "nodejs-lts"},
    "npm":        {"winget": "OpenJS.NodeJS.LTS",  "choco": "nodejs",  "scoop": "nodejs-lts"},
    "deno":       {"winget": "DenoLand.Deno",      "choco": "deno",    "scoop": "deno"},
    "bun":        {"scoop": "bun"},
    "java":       {"winget": "Oracle.JDK.21",      "choco": "openjdk", "scoop": "openjdk"},
    "javac":      {"winget": "Oracle.JDK.21",      "choco": "openjdk", "scoop": "openjdk"},
    "go":         {"winget": "GoLang.Go",          "choco": "golang",  "scoop": "go"},
    "gcc":        {"choco": "mingw",               "scoop": "gcc"},
    "g++":        {"choco": "mingw",               "scoop": "gcc"},
    "clang":      {"winget": "LLVM.LLVM",          "choco": "llvm",    "scoop": "llvm"},
    "clang++":    {"winget": "LLVM.LLVM",          "choco": "llvm",    "scoop": "llvm"},
    "rustc":      {"winget": "Rustlang.Rustup",    "scoop": "rustup"},
    "cargo":      {"winget": "Rustlang.Rustup",    "scoop": "rustup"},
    "rustup":     {"winget": "Rustlang.Rustup",    "scoop": "rustup"},
    "dotnet":     {"winget": "Microsoft.DotNet.SDK.8", "choco": "dotnet-sdk", "scoop": "dotnet-sdk"},
    "ruby":       {"winget": "RubyInstallerTeam.Ruby", "choco": "ruby",  "scoop": "ruby"},
    "gem":        {"winget": "RubyInstallerTeam.Ruby", "choco": "ruby",  "scoop": "ruby"},
    "perl":       {"choco": "strawberryperl",      "scoop": "perl"},
    "php":        {"winget": "PHP.PHP",            "choco": "php",     "scoop": "php"},
    "composer":   {"choco": "composer",            "scoop": "composer"},
    "lua":        {"choco": "lua",                 "scoop": "lua"},
    "julia":      {"winget": "Julialang.Julia",    "choco": "julia",   "scoop": "julia"},
    "dart":       {"choco": "dart-sdk",            "scoop": "dart"},
    "flutter":    {"choco": "flutter",             "scoop": "flutter"},
    "elixir":     {"choco": "elixir",              "scoop": "elixir"},
    "clojure":    {"choco": "clojure",             "scoop": "clojure"},
    "lein":       {"choco": "leiningen",           "scoop": "leiningen"},
    "zig":        {"winget": "zig.zig",            "scoop": "zig"},
    "nim":        {"choco": "nim",                 "scoop": "nim"},
    "ghc":        {"choco": "ghc",                 "scoop": "ghc"},
    "stack":      {"choco": "haskell-stack",       "scoop": "stack"},
    "cabal":      {"choco": "cabal",               "scoop": "cabal"},
    "kotlin":     {"choco": "kotlin",              "scoop": "kotlin"},
    "kotlinc":    {"choco": "kotlin",              "scoop": "kotlin"},
    "scala":      {"choco": "scala",               "scoop": "scala"},
    "groovy":     {"choco": "groovy",              "scoop": "groovy"},
    "swift":      {"winget": "Swift.Toolchain",    "scoop": "swift"},
    "git":        {"winget": "Git.Git",            "choco": "git",     "scoop": "git"},
    "docker":     {"winget": "Docker.DockerDesktop", "choco": "docker-desktop", "scoop": "docker"},
    "kubectl":    {"winget": "Kubernetes.kubectl", "choco": "kubernetes-cli", "scoop": "kubectl"},
    "terraform":  {"winget": "Hashicorp.Terraform","choco": "terraform", "scoop": "terraform"},
    "make":       {"choco": "make",                "scoop": "make"},
    "cmake":      {"winget": "Kitware.CMake",      "choco": "cmake",   "scoop": "cmake"},
    "wget":       {"winget": "GnuWin32.Wget",      "choco": "wget",    "scoop": "wget"},
    "curl":       {"winget": "cURL.cURL",          "choco": "curl",    "scoop": "curl"},
    "ollama":     {"winget": "Ollama.Ollama",      "scoop": "ollama"},
}


def _probe_tool(exe):
    resolved = shutil.which(exe)
    if resolved is None:
        return False, f"not on PATH (looked for '{exe}')"
    for flag in VERSION_FLAGS:
        try:
            result = subprocess.run([resolved, flag], capture_output=True,
                                    text=True, timeout=8)
        except subprocess.TimeoutExpired:
            return False, "timed out"
        except OSError as e:
            return False, f"could not run ({e})"
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        if output:
            return True, _first_nonempty_line(output)
    return False, f"found at '{resolved}' but no version output"


def _detect_package_manager():
    for name in ("winget", "scoop", "choco", "pip"):
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def _install_command(pm, package):
    if pm == "winget":
        return (f"winget install --id {package} -e "
                f"--accept-source-agreements --accept-package-agreements")
    if pm == "scoop":  return f"scoop install {package}"
    if pm == "choco":  return f"choco install {package} -y"
    if pm == "pip":    return f"python -m pip install --upgrade {package}"
    return ""


def run_doctor(fix=False):
    cprint("message", f"{APP_NAME} --doctor" + ("  (with --fix)" if fix else ""))
    cprint("message", "=" * 60)
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    cprint("message", f"{APP_NAME} {APP_VERSION}  •  Python {py}  •  "
                      f"{platform.system()} {platform.release()}")
    cprint("message", f"  theme:   {CURRENT_THEME_NAME}  (file: {THEME_FILE})")
    cprint("message", f"  history: {len(HISTORY)} entries  (file: {HISTORY_FILE})")
    cprint("message", f"  ANSI:    {'on' if ANSI_OK else 'off'}")
    cprint("message", f"  plugins: {len(LOADED_PLUGINS)} loaded from {PLUGIN_DIR}")
    curl = shutil.which("curl") or shutil.which("curl.exe")
    cprint("message", f"  cURL:    {curl or 'not found'}")
    if fix:
        pm, pm_path = _detect_package_manager()
        cprint("message", f"  pkgmgr:  {pm + ' (' + pm_path + ')' if pm else 'none found'}")
    cprint("message", "")
    seen = set(); missing = []
    total_ok = total_missing = 0

    def scan_group(keys):
        nonlocal total_ok, total_missing
        for key in keys:
            if key in seen: continue
            seen.add(key)
            exe, label = VERSION_TOOLS.get(key, (key, key))
            ok, detail = _probe_tool(exe)
            if ok:
                total_ok += 1
                cprint("message", f"  [OK]  {label:<18} {detail}")
            else:
                total_missing += 1
                missing.append((key, exe, label))
                cprint("error",   f"  [--]  {label:<18} {detail}")

    for group, keys in DOCTOR_GROUPS.items():
        cprint("message", f"{group}:")
        scan_group(keys)
        cprint("message", "")
    leftovers = [k for k in VERSION_TOOLS if k not in seen]
    if leftovers:
        cprint("message", "Other:")
        scan_group(leftovers)
        cprint("message", "")
    cprint("message", "-" * 60)
    cprint("message", f"installed: {total_ok}   missing: {total_missing}   "
                      f"total checked: {total_ok + total_missing}")
    if not fix:
        if total_missing:
            cprint("message", "run `--doctor --fix` to see proposed install commands.")
        return
    if total_missing == 0:
        cprint("message", "nothing to fix — every known tool is installed.")
        return
    pm, _ = _detect_package_manager()
    if pm is None:
        cprint("error", "no package manager found (winget / scoop / choco / pip).")
        return
    cprint("message", "")
    cprint("message", f"Proposed installs via {pm}:")
    cprint("message", "-" * 60)
    plan = []; no_recipe = []
    for key, exe, label in missing:
        recipe = FIX_RECIPES.get(key)
        if not recipe or pm not in recipe:
            no_recipe.append(label); continue
        cmd = _install_command(pm, recipe[pm])
        plan.append((label, cmd))
        cprint("message", f"  {label:<18} {cmd}")
    if no_recipe:
        cprint("message", "")
        cprint("message", "No auto-install recipe for: " + ", ".join(sorted(set(no_recipe))))
    if not plan:
        cprint("message", "no fixes available for the current package manager.")
        return
    cprint("message", "")
    cprint("message", f"{len(plan)} command(s) above will run in sequence.")
    if not confirm("run all now? [y/N]: "):
        cprint("message", "aborted — nothing was installed."); return
    cprint("message", "running installs — this may take a while…")
    for label, cmd in plan:
        cprint("message", f"\n>>> {cmd}")
        rc = run_streaming(cmd, shell=True)
        if rc != 0:
            cprint("error", f"failed: {label} (exit {rc}) — stopping.")
            cprint("message", "fix the error above, then rerun `--doctor --fix`.")
            return
    cprint("message", "")
    cprint("message", "all installs finished. rerun `--doctor` to verify.")


# ================================================================
#  --secscan
# ================================================================
SEC_TOOLS = [
    ("nmap", "Nmap", "https://nmap.org/download"),
    ("wireshark", "Wireshark", "https://www.wireshark.org/download.html"),
    ("tshark", "TShark (Wireshark CLI)", "https://www.wireshark.org/download.html"),
    ("nessusd", "Nessus", "https://www.tenable.com/downloads/nessus"),
    ("openvas", "OpenVAS / Greenbone", "https://greenbone.github.io/docs/latest/"),
    ("gvm-cli", "Greenbone CLI", "https://greenbone.github.io/docs/latest/"),
    ("nikto", "Nikto", "https://github.com/sullo/nikto"),
    ("sqlmap", "SQLmap", "https://sqlmap.org/"),
    ("john", "John the Ripper", "https://www.openwall.com/john/"),
    ("hashcat", "Hashcat", "https://hashcat.net/hashcat/"),
    ("hydra", "Hydra", "https://github.com/vanhauser-thc/thc-hydra"),
    ("aircrack-ng", "Aircrack-ng", "https://www.aircrack-ng.org/downloads.html"),
    ("kismet", "Kismet", "https://www.kismetwireless.net/packages/"),
    ("msfconsole", "Metasploit", "https://www.metasploit.com/download"),
    ("snort", "Snort", "https://www.snort.org/downloads"),
    ("autopsy", "Autopsy", "https://www.autopsy.com/download/"),
    ("whois", "whois", "https://learn.microsoft.com/sysinternals/downloads/whois"),
    ("shodan", "Shodan CLI", "https://cli.shodan.io/"),
    ("curl", "cURL", "https://curl.se/windows/"),
    ("openssl", "OpenSSL", "https://slproweb.com/products/Win32OpenSSL.html"),
]


def run_secscan():
    cprint("message", f"{APP_NAME} --secscan  (installed security tools)")
    cprint("message", "=" * 64)
    cprint("message", "Authorized use only — scan/attack only systems you own")
    cprint("message", "or have explicit written permission to test.")
    cprint("message", "")
    present = missing = 0
    for exe, label, url in SEC_TOOLS:
        resolved = shutil.which(exe)
        if not resolved:
            missing += 1
            cprint("error", f"  [--]  {label:<22} not on PATH")
            cprint("message", f"         official: {url}")
            continue
        present += 1
        version_line = ""
        for flag in VERSION_FLAGS:
            try:
                r = subprocess.run([resolved, flag], capture_output=True,
                                   text=True, timeout=8)
            except (subprocess.TimeoutExpired, OSError):
                continue
            out = (r.stdout or "").strip() or (r.stderr or "").strip()
            if out:
                version_line = _first_nonempty_line(out); break
        if version_line:
            cprint("message", f"  [OK]  {label:<22} {version_line}")
        else:
            cprint("message", f"  [OK]  {label:<22} (installed; no version output)")
    cprint("message", "")
    cprint("message", "-" * 64)
    cprint("message", f"installed: {present}   missing: {missing}   "
                      f"total checked: {present + missing}")
    if missing:
        cprint("message", "install links above — no auto-install is performed.")


# ================================================================
#  prompt  (PERF 2: cached user/host/admin/home)
# ================================================================
_PROMPT_CACHE = {"user": None, "host": None, "admin": None, "home": None}


def _init_prompt_cache():
    u, h = get_user_host()
    _PROMPT_CACHE["user"] = u
    _PROMPT_CACHE["host"] = h
    _PROMPT_CACHE["admin"] = "yes" if is_admin() else "no"
    _PROMPT_CACHE["home"] = os.path.expanduser("~")


def get_user_host():
    try:
        import getpass
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    try:
        host = socket.gethostname() or "host"
    except Exception:
        host = "host"
    return user, host


def make_prompt():
    if _PROMPT_CACHE["user"] is None:
        _init_prompt_cache()
    cwd = os.getcwd()
    home = _PROMPT_CACHE["home"]
    if home and cwd.lower().startswith(home.lower()):
        cwd = "~" + cwd[len(home):]
    sigil = "#" if _PROMPT_CACHE["admin"] == "yes" else "$"
    return f"{_PROMPT_CACHE['user']}@{_PROMPT_CACHE['host']}:{cwd}{sigil} "


# ================================================================
#  DISPATCH  (PERF 1: shell=False fast path; PERF 4: builtins first)
# ================================================================
def _needs_shell(line):
    return any(c in SHELL_META for c in line)


def run_command(line):
    parts = split_args(line)
    if not parts:
        return True
    if parts[0].lower() == APP_NAME.lower():
        parts = parts[1:]
        if not parts:
            show_shell_help()
            return True
    if len(parts) == 1 and parts[0] in ("--version", "-V"):
        show_shell_version(); return True
    if parts[0] == "--doctor":
        fix = any(a == "--fix" for a in parts[1:])
        run_doctor(fix=fix); return True
    if len(parts) == 1 and parts[0] == "--secscan":
        run_secscan(); return True
    if len(parts) == 1 and parts[0] == "--help":
        show_shell_help(); return True
    if len(parts) == 1 and parts[0] == "--clear":
        builtin_clear(); return True
    if len(parts) >= 2 and parts[-1].lower() == "thm":
        builtin_theme([parts[0].lower()]); return True

    name = parts[0].lower()

    # PERF 4: builtins before tool-registry probes
    if name in ("exit", "quit"):
        return False
    if name in BUILTINS:
        fn = BUILTINS[name]
        try:
            fn(parts[1:])
        except TypeError:
            try:
                fn()
            except Exception as e:
                cprint("error", f"{name}: {e}")
        except Exception as e:
            cprint("error", f"{name}: {e}")
        return True

    # Tool version/help probes (only for non-builtins)
    if check_version(parts[0], parts[1:]):
        return True
    if check_help(parts[0], parts[1:]):
        return True

    # PERF 1: shell=False fast path for simple commands
    try:
        if _needs_shell(line):
            run_streaming(line, shell=True)
        else:
            run_streaming(parts)
    except KeyboardInterrupt:
        print("^C")
    return True


def split_args(line):
    out, cur, quote = [], [], None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch.isspace():
            if cur:
                out.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def main():
    no_plugins = "--no-plugins" in sys.argv
    load_history()
    load_theme()
    _init_prompt_cache()   # PERF 2

    if not ANSI_OK:
        print("warning: ANSI colors unavailable; themes will be no-ops.")
    cprint("message", f"{APP_NAME} {APP_VERSION}")
    cprint("message", "  --help  for commands")

    # Auto-load ONLY already-trusted plugins (never prompt at startup).
    if not no_plugins:
        trusted = _load_trusted()
        for path, name, file_hash in _scan_plugins_cached():
            if name in trusted and trusted[name] == file_hash:
                load_plugin(path, confirm_hash=False)

    try:
        while True:
            try:
                line = read_line(make_prompt())
            except KeyboardInterrupt:
                print("^C"); continue
            if line is None:
                print(); break
            line = line.strip()
            if not line:
                continue
            HISTORY.append(line)
            if not run_command(line):
                break
    finally:
        save_history()
        print("bye.")


if __name__ == "__main__":
    main()