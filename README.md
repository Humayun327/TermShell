# termShell

A pure-standard-library terminal for Windows. No pip packages. Python 3.8+.

`termShell` is a persistent shell written in Python that runs on Windows
(and POSIX where noted), streams command output live, and adds a small set
of built-in utilities that are useful in a Windows dev environment:
resumable downloads, shallow git clones, local system monitoring, color
themes, plugin support, and a bounded `--help`/`--version` handler for
any tool on `PATH`.

It is **not** a Linux emulator, **not** a security product, and **not**
a replacement for PowerShell or WSL. It is a small, readable shell you
can audit in one sitting.

---

## Quick start

```bat
python termShell.py
```

For the fastest cold start, use a launcher script (`ts.bat`):

```bat
@echo off
python -O -S "%~dp0termShell.py" %*
```

Save that next to `termShell.py`, add the folder to `PATH`, and run `ts`.

On first launch you'll see:

```
termShell 1.6.0
  --help  for commands
alice@DESKTOP-ABC:E:\Projects$
```

The prompt is `user@host:cwd$`, with `#` in place of `$` when elevated —
the same convention used by Bash and Zsh.

---

## DESCRIPTION

**termShell** is a persistent shell written in pure Python standard
library. It runs on Windows (POSIX best-effort), accepts ordinary shell
commands, and streams their output line-by-line as it is produced.

It provides Linux-style commands on Windows: `ls`, `cd`, `pwd`, `mkdir`,
`rm -rf`, `cat`, `ping`, `netstat`, `ss`, `wget`, `which`, `whoami`,
`man`, `chmod`, `chown`, `sudo`, `su`, and more. Each command is
implemented as a builtin or as a thin wrapper around the native Windows
tool, so the output and behavior match what you expect from Linux.

**termShell** is not a Linux emulator, not a security product, and not a
replacement for `powershell.exe` or WSL. It is a small, auditable shell
that gives you Linux-style commands on Windows.

---

## DESIGN

termShell is intentionally small. The entire shell is a single Python
file with no third-party dependencies. It exists to answer a specific
question: *what does a useful Windows shell look like if you refuse to
install anything?*

The answer has three parts.

**The OS is the shell.** Most commands are not reimplemented; termShell
hands them to the OS via `subprocess` and streams the output. `dir`,
`ping`, `netstat`, `git`, `curl`, `npm`, `python`, and everything else
on `PATH` run unchanged. This means termShell inherits the behavior of
every tool you already know. When `git clone` prints progress, you see
git's progress. When `ping` prints a reply line, you see the same reply
line `cmd.exe` would show.

**The shell adds Linux ergonomics.** What termShell does add is a set of
Linux-style commands that Windows lacks: `ls` (instead of `dir`), `rm
-rf` (instead of `rmdir /s /q`), `cat` (instead of `type`), `which`
(instead of `where`), `man` (instead of `help`), `chmod`, `chown`, and
the rest. Each one is implemented so the behavior matches Linux, not
Windows. `ls -la` shows hidden files. `rm -rf` recursively removes.
`cat` prints. `which` resolves. `man` shows help.

**Safety is not optional.** Anything that touches privilege, the
network, or arbitrary code execution asks first, or refuses. The `sudo`
command fires the Windows UAC dialog and respects a decline. `scan` is
hardcoded to localhost. `webtest` refuses remote targets. Plugins
require a hash-pinned confirmation on first load and any time their
content changes.

---

## INSTALLATION

termShell requires only Python 3.8+ on Windows. There are no pip
packages to install.

1. Save `termShell.py` somewhere on your machine, e.g.
   `C:\Tools\termShell\termShell.py`.

2. (Optional, recommended) Create `ts.bat` in the same folder:

   ```bat
   @echo off
   python -O -S "%~dp0termShell.py" %*
   ```

3. (Optional) Add `C:\Tools\termShell` to your `PATH` so you can run
   `ts` from anywhere.

4. Launch:

   ```
   ts
   ```

   or

   ```
   python C:\Tools\termShell\termShell.py
   ```

**Requirements:**

- Python 3.8+ (Windows; POSIX support is best-effort)
- Windows 10 build 1803+ for `curl.exe` (or install cURL separately)
- Git for `clone` — https://git-scm.com/download/win
- Windows Terminal or modern `conhost` for ANSI colors

**Optional:**

- Ollama for the `ai` builtin — https://ollama.com
- Wireshark or tshark for packet capture (termShell does not sniff)

---

## OPTIONS

### Command-line flags

```
--no-plugins        Skip auto-loading already-trusted plugins at startup.
--help              Print the built-in command reference and exit.
--version, -V       Print termShell's version and exit.
```

### Launch flags (Python interpreter)

```
-O                  Strip asserts (sets __debug__ = False).
-S                  Skip site initialization; saves 30-80 ms at start.
```

The `-S` flag is the single biggest cold-start win. It skips `.pth`
file processing, user site-packages scanning, and `sitecustomize`
import. termShell itself imports nothing from site-packages, so `-S`
is safe for the shell — but child processes launched via `runpy` still
get normal `site` because they are separate processes.

Without `-S`, Python processes every `.pth` file in every site-packages
directory it knows about. On a machine with many installed packages,
this can take 30-80 ms per launch. With `-S`, none of that happens.

`-O` strips asserts and sets `__debug__ = False`. termShell does not
use asserts in the hot path, so the practical difference is small, but
it's free.

---

## LINUX-STYLE COMMANDS

This is the core of termShell. Every command below is Linux-style: the
name, the flags, and the behavior match what you would type on a Linux
system. Each command is either a builtin or a thin wrapper around the
native Windows tool.

Builtins are dispatched before tool-registry probes, so `cd`, `ls`, and
`pwd` never cause a subprocess spawn. External commands that share a
name with a builtin are unreachable by name; use the full path (e.g.
`C:\Windows\System32\where.exe`) if you need to bypass.

### File and directory commands

**`ls [flags/path...]`**

List directory contents. Linux-style.

```
ls                  # list current directory
ls -la              # list all files, long format (shows hidden)
ls -l               # long format
ls -a               # show hidden files
ls C:\Users         # list a specific directory
ls /path/to/dir     # list a specific directory
```

On Windows, `ls` delegates to `dir` with flag translation:
`-la`, `-al`, `-l`, `-a` become `dir /a` (show hidden). `-h` is
ignored (dir shows sizes by default). Other flags pass through.

On POSIX, `ls` invokes the real `ls` binary directly.

**`cd [dir]`**

Change directory. Linux-style.

```
cd                  # go to home directory (~)
cd Documents        # go to Documents
cd ..               # go up one level
cd -                # go back to previous directory (via $OLDPWD)
cd C:\Users\alice   # absolute path
```

`cd -` works after any successful `cd`. The previous directory is
stored in `$OLDPWD`, same as Bash.

**`pwd`**

Print working directory. Linux-style.

```
pwd
# C:\Users\alice\Projects
```

**`mkdir <dir...>`**

Create directories. Linux-style.

```
mkdir newfolder             # create one directory
mkdir a b c                 # create three directories
mkdir -p a/b/c              # create parents as needed (always recursive)
```

termShell's `mkdir` always creates intermediate directories, so `-p`
is effectively always on. You can pass `-p` for compatibility; it is
ignored.

**`rm [-rf] <path...>`**

Remove files and directories. Linux-style.

```
rm file.txt                 # remove a file
rm -r folder                # remove a directory (confirms first)
rm -rf folder               # remove a directory without -f errors (still confirms)
rm file1.txt file2.txt      # remove multiple files
rm -f missing.txt           # no error if missing
```

Flags:

```
-r   recursive (required for directories)
-f   force (suppress missing-file errors)
```

**Protected paths.** termShell refuses to remove `/`, `\`, `C:\`,
`C:/`, `C:`, and `~`. These are safety guards.

**Confirmation.** Directory removal always asks first, even with `-f`:

```
remove directory '<path>' and everything inside? [y/N]:
```

Answer `y` or `yes` to proceed, anything else to skip.

**`cat <file> [--force]`**

Print a file. Linux-style.

```
cat file.txt                # print a file
cat file1.txt file2.txt     # print multiple files
cat --force bigfile.log     # print a file larger than 2 MB
```

Refuses files over 2 MB unless `--force` is given. If the file does
not end with a newline, `cat` adds one.

**`hashfile <path> [sha256]`**

Compute and print SHA-256 and MD5. Linux-style (`sha256sum` +
`md5sum` combined).

```
hashfile file.iso                               # print hashes
hashfile file.iso abc123...                     # compare to expected SHA-256
```

### Network commands

**`ping <host> [-n count]`**

Ping a host. Linux-style.

```
ping google.com             # 4 pings
ping google.com -n 10       # 10 pings
```

Streams output line-by-line. Defaults to 4 packets. On POSIX, uses
`-c` instead of `-n`.

**`netstat [-tulpn]`**

Show network connections. Linux-style.

```
netstat                     # all connections
netstat -tulpn              # TCP/UDP listening, numeric, with PID
netstat -an                 # all, numeric
```

Linux-style flags are translated to Windows equivalents:
`-tulpn` becomes `-a -n -o`. Other flags pass through unchanged.

**`ss [-tulpn]`**

Show socket statistics. Linux-style.

```
ss                          # all sockets
ss -tulpn                   # TCP/UDP listening, numeric, with PID
```

On POSIX, uses the real `ss` binary. On Windows, falls back to
`netstat` with a printed notice.

**`wget <url> [file]`**

Download a file with resume support. Linux-style.

```
wget https://example.com/file.iso                  # save to file.iso
wget https://example.com/file.iso myname.iso       # save to myname.iso
```

Resumable. If interrupted, rerun the same command; cURL resumes from
the correct byte offset.

**`get <url> [file]`**

Alias for `wget`. Same behavior.

**`ports <host> <port> [--i-own-this-host]`**

Check a single TCP port. Linux-style (`nc -zv` equivalent).

```
ports localhost 80              # check localhost:80
ports 127.0.0.1 443             # check 127.0.0.1:443
ports example.com 443 --i-own-this-host   # authorized remote check
```

Localhost targets are allowed by default. Non-local targets require
`--i-own-this-host`.

**`scan [ports...]`**

Scan localhost ports. Linux-style (`nmap localhost` equivalent).

```
scan                            # scan default port set
scan 80 443 8080                # scan specific ports
```

Hardcoded to `127.0.0.1`. No host argument exists. Default port set:
`21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3000, 3306, 3389, 5000,
5432, 6379, 8000, 8080, 8443, 9000`.

**`webtest <url>`**

Check a localhost HTTP server. Linux-style (`curl -I` equivalent for
local testing).

```
webtest http://localhost:8080/
webtest http://127.0.0.1:3000/api
```

Prints status, headers, TLS status, and first 2 KB of body. Refuses
non-local URLs.

### Process and system commands

**`whoami`**

Print user, host, admin status, and current directory. Linux-style.

```
whoami
# user:  alice
# host:  DESKTOP-ABC
# admin: no
# cwd:   C:\Users\alice\Projects
```

**`which <cmd...>`**

Locate commands on PATH. Linux-style.

```
which python                    # find python
which git curl wget             # find multiple
which nonexistent               # not found on PATH
```

**`man <tool>`**

Show help for a tool. Linux-style.

```
man python                      # first 25 lines of python --help
man git                         # first 25 lines of git --help
man nmap                        # first 25 lines of nmap --help
```

Truncates to 25 lines with a footer noting how many more exist. On
POSIX, uses the real `man` if present.

**`history`**

Show command history. Linux-style.

```
history                         # last 50 commands
```

**`live-sys [interval]`**

Live system monitor. Linux-style (`top` / `htop` equivalent).

```
live-sys                        # 1.0s refresh
live-sys 2                      # 2.0s refresh
```

Shows CPU, memory, disk, and top processes by memory. Press any key
to exit.

### Privilege commands

**`sudo <cmd>`**

Run a command elevated. Linux-style.

```
sudo netstat -ano               # run netstat elevated
sudo icacls file /grant ...
sudo powershell -c "..."
```

On Windows, uses `ShellExecuteW("runas", ...)` to show the UAC prompt.
The elevated command runs in a new console window. If you decline the
UAC prompt, nothing runs.

**`su`**

Switch user. Linux-style.

```
su
# su: POSIX-only. On Windows use:
#   runas /user:<username> cmd
# or open an elevated terminal (right-click → Run as administrator).
# Password prompts are unsafe in this raw-mode line editor.
```

On Windows, prints the `runas` equivalent. Interactive password
prompts are not supported in termShell's line editor.

**`chmod +x <file>` / `chmod <mode> <file>`**

Change file permissions. Linux-style.

```
chmod +x script.sh              # make executable (POSIX)
chmod 755 script.sh             # set mode 755 (POSIX)
chmod +x script.sh              # Windows: prints icacls hint
```

On POSIX, sets the executable bit via `os.chmod`. On Windows, prints
that the bit does not exist and suggests `icacls`.

**`chown <user> <file>`**

Change file ownership. Linux-style.

```
chown alice file.txt            # change owner (POSIX)
chown alice:users file.txt      # change owner and group (POSIX)
```

On POSIX, uses `os.chown`. On Windows, prints `takeown` and `icacls`
hints.

### Shell control commands

**`clear` / `cls` / `--clear`**

Clear the screen. Linux-style.

```
clear                           # clear screen
cls                             # alias
--clear                         # flag form
```

**`exit` / `quit`**

Exit the shell. Linux-style.

```
exit                            # leave termShell
quit                            # alias
# or press Ctrl+D
```

### Source control commands

**`clone <url> [dir] [--full]`**

Shallow git clone with resume. Linux-style (`git clone --depth 1`
equivalent).

```
clone https://github.com/psf/requests              # shallow clone
clone https://github.com/psf/requests mydir        # to mydir
clone https://github.com/psf/requests --full       # full history
```

If the target directory already exists with `.git`, runs `git fetch &&
git pull --ff-only` to resume.

### Execution commands

**`runpy <file.py> [args]`**

Run a Python file with preview. Linux-style (`python file.py` with
safety).

```
runpy script.py                     # preview + confirm + run
runpy script.py --verbose arg1      # with arguments
```

Shows first 5 non-empty lines and asks for confirmation before running.

### AI commands

**`ai <prompt> [--model m]`**

Query local Ollama. Custom command.

```
ai explain how TCP handshakes work
ai --model qwen2.5 write a Python function to parse JSON
ai --model llama3.2 summarize this text
```

Streams the response token by token from `localhost:11434`.

### Theme commands

**`theme <name>`**

Set the color theme. Custom command.

```
theme blue                      # set theme to blue
theme green                     # set theme to green
theme list                      # list all themes
theme reset                     # reset to default
```

**`<color> thm`**

Shortcut for `theme <color>`.

```
blue thm                        # set theme to blue
green thm                       # set theme to green
red thm                         # set theme to red
dark thm                        # set theme to dark
matrix thm                      # set theme to matrix
ocean thm                       # set theme to ocean
sunset thm                      # set theme to sunset
list thm                        # list all themes
reset thm                       # reset to default
```

Available themes: `blue`, `dark`, `default`, `green`, `light`,
`magenta`, `matrix`, `ocean`, `red`, `sunset`, `white`, `yellow`.

### Plugin commands

**`plugins`** / **`plugins list`**

List plugins. Custom command.

```
plugins                         # list available and loaded
plugins list                    # same
```

**`plugins load <name>`**

Load a plugin. Confirms hash on first load.

```
plugins load hello              # load hello.py
plugins load myplugin           # load myplugin.py
```

**`plugins load-all`**

Load all plugins. Each confirmed individually if untrusted.

```
plugins load-all
```

**`plugins unload <name>`**

Unload a plugin. Does not remove the file.

```
plugins unload hello
```

**`plugins info <name>`**

Show plugin details.

```
plugins info hello
# name:     hello
# path:     C:\Users\alice\.termshell\plugins\hello.py
# sha256:   abc123...
# trusted:  yes
# commands: hello
```

**`plugins dir`**

Print the plugin directory.

```
plugins dir
# C:\Users\alice\.termshell\plugins
```

### Diagnostic commands

**`--help`**

Print the full command reference.

```
--help
```

**`--version`**

Print termShell version.

```
--version
# termShell 1.6.0  (pure-stdlib terminal)
# Python 3.12.3  •  Windows 11  •  ANSI: on
```

**`--doctor`**

Scan PATH for installed tools.

```
--doctor
# Languages:
#   [OK]  Python             Python 3.12.3
#   [OK]  Node.js            v20.11.0
#   [--]  Java               not on PATH (looked for 'java')
#   ...
```

**`--doctor --fix`**

Propose install commands for missing tools. Asks before running.

```
--doctor --fix
# Proposed installs via winget:
#   Java               winget install --id Oracle.JDK.21 ...
#   Deno               winget install --id DenoLand.Deno ...
# 2 command(s) above will run in sequence.
# run all now? [y/N]:
```

**`--secscan`**

Report installed security tools with official download links.

```
--secscan
# [OK]  Nmap               Nmap version 7.94
# [--]  Wireshark          not on PATH
#         official: https://www.wireshark.org/download.html
```

### Universal version/help

**`<tool> --version`**

Print a tool's version. Linux-style.

```
python --version                # Python: Python 3.12.3
node --version                  # Node.js: v20.11.0
gcc --version                   # GCC: gcc (MinGW-W64 ...) 13.2.0
ollama --version                # Ollama: ollama version 0.1.42
git --version                   # Git: git version 2.44.0.windows.1
```

**`<tool> --help`**

Show a tool's help. Linux-style.

```
python --help                   # first 25 lines of Python help
git --help                      # first 25 lines of git help
npm --help                      # first 25 lines of npm help
```

The tool registry (`VERSION_TOOLS`) covers ~50 entries: python, python3,
py, pip, pip3, node, npm, npx, deno, bun, java, javac, kotlin, kotlinc,
scala, groovy, go, gcc, g++, clang, clang++, rustc, cargo, rustup,
dotnet, ruby, gem, perl, php, composer, lua, luajit, rscript, julia,
swift, dart, flutter, elixir, erl, clojure, lein, zig, nim, crystal,
ghc, stack, cabal, git, docker, kubectl, terraform, make, cmake, curl,
wget, ollama.

Adding a new tool is one line in `VERSION_TOOLS`:

```python
"mytool": ("mytool", "My Tool"),
```

Then `mytool --version`, `mytool --help`, and `--doctor` all work.

---

## LINE EDITING

Linux-style line editing, the same as Bash:

```
Left / Right             Move cursor.
Home / End               Jump to start / end of line.
Delete                   Delete character at cursor.
Backspace                Delete character before cursor.
Up / Down                Navigate command history.
Ctrl+R                   Reverse history search.
Ctrl+C                   Cancel the current line.
Ctrl+D                   Exit termShell.
```

Ctrl+R search operates on the in-memory `HISTORY` list. Matches are
returned newest-first, capped at 50. Type to filter; Up/Down cycles;
Enter accepts; Esc cancels.

When you accept a match, the prompt is redrawn with the matched command
in the input buffer. You can then edit it (arrows, backspace, etc.) or
press Enter to execute.

---

## PLUGIN AUTHORING

A plugin is a Python file in `~/.termshell/plugins/` ending in `.py`.
It must define `register_builtins()` returning a dict mapping command
name to callable. Each callable receives a single `args` list (the
tokens after the command name).

Minimal plugin:

```python
def cmd_hello(args):
    print("hello from a plugin! args =", args)

def register_builtins():
    return {"hello": cmd_hello}
```

Save as `~/.termshell/plugins/hello.py`. Then:

```
plugins load hello
  → sha256 + first 8 lines + [y/N]
  → y
hello world
  → hello from a plugin! args = ['world']
```

Rules:

**You cannot shadow a builtin.** If `register_builtins()` returns a
key that already exists in `BUILTINS` (e.g. `cd`), the plugin is
refused with an error listing the collision. This prevents a plugin
from silently changing the behavior of `rm`, `sudo`, or any other
builtin.

**Content changes re-prompt.** If the file's SHA-256 no longer matches
`trusted.json`, termShell shows the new hash and preview and asks
again. This is deliberate: a plugin update is a new plugin from a trust
standpoint. If you didn't make the change, something else did.

**Plugins run with termShell's privileges.** A plugin can read, write,
and delete anything you can. It can also spawn processes, open network
connections, and do anything else Python can do. Review before loading.

**Already-trusted plugins auto-load at startup** unless you launch with
`--no-plugins`. The auto-load only happens if the file's hash still
matches `trusted.json`; if the file changed, it's listed as available
but not loaded.

A plugin can do anything Python can do. That's not a bug; it's the
whole point of a plugin system. Which is also why the confirmation step
is not configurable away.

---

## THEME AUTHORING

Themes are defined in the `THEMES` dict at the top of `termShell.py`.
Adding a theme is one edit:

```python
"mytheme": {"prompt": "\x1b[1;35m", "input": "\x1b[0;35m",
            "message": "\x1b[0;35m", "error": "\x1b[1;31m"},
```

Values are ANSI SGR sequences. The four keys correspond to the parts
listed under "Theme commands" above. After adding the entry,
`mytheme thm` becomes available immediately on next launch.

ANSI sequences used by the built-in themes:

```
\x1b[0m         reset
\x1b[1;3Xm      bold + foreground color X (X = 0..7)
\x1b[0;3Xm      foreground color X
\x1b[1;9Xm      bright foreground color X (X = 0..7)
\x1b[1;38;5;Nm  bold + 256-color foreground N
```

Standard colors (X = 0..7): black, red, green, yellow, blue, magenta,
cyan, white. Bright colors (X = 0..7 with the 9 prefix): same names, but
brighter. 256-color codes (N = 0..255) give you the full xterm palette,
which is how `sunset` (orange) and `ocean` (bright blue) get their colors.

---

## FILES

```
~/.termshell_history         Command history (last 500).
~/.termshell_theme           Current theme name (JSON).
~/.termshell/plugins/        Plugin files (*.py).
~/.termshell/trusted.json    SHA-256 hashes of trusted plugins (JSON).
```

Removing any of these resets the corresponding state. Removing
`trusted.json` forces a re-confirmation of every plugin on the next
load.

The history file is plain text, one command per line. The theme file is
one line of JSON. The trusted store is JSON, `{plugin_name: sha256}`.
The plugin directory is the only one that holds executable code.

---

## ENVIRONMENT

`termShell` does not set environment variables. It reads:

```
PATH                     Used by shutil.which() to locate tools.
USERNAME / USER          Fallback for username if getpass() fails.
OLDPWD                   Set by `cd`; used by `cd -`.
```

On POSIX, `getpass.getuser()` reads `LOGNAME`, `USER`, `LNAME`, or
`USERNAME`, in that order. On Windows it reads `USERNAME`.

`OLDPWD` is set by `cd` on successful directory changes. It's the same
variable POSIX shells use, so scripts that read it work unchanged.

---

## EXAMPLES

### Launching

```
> python termShell.py
termShell 1.6.0
  --help  for commands
alice@DESKTOP-ABC:E:\Projects$
```

Faster launch via launcher script:

```
> ts
```

### Basic Linux-style workflow

```
alice@host:~$ pwd
C:\Users\alice
alice@host:~$ ls
...
alice@host:~$ mkdir projects
created: projects
alice@host:~$ cd projects
alice@host:~/projects$ ls -la
...
alice@host:~/projects$ cd -
alice@host:~$ rm -rf projects
remove directory 'projects' and everything inside? [y/N]: y
removed directory: projects
```

### Downloading over a weak connection

```
alice@host:~$ wget https://example.com/big.iso
[get] C:\Windows\System32\curl.exe -L -C - --retry 10 --retry-delay 5 -O https://example.com/big.iso
[get] if interrupted, run the same command again to resume.
 45  512M   45  232M    0     0  1.2M      0  0:07:02  0:03:10 ...
^C
alice@host:~$ wget https://example.com/big.iso
[get] ...
 45  512M   45  232M    0     0  1.2M      0  0:07:02  0:00:00 ...
100  512M  100  512M    0     0  2.1M      0  0:04:01  0:04:01 ...
```

The second invocation starts at 232 MB, not 0. That's cURL's `-C -`
doing the work; termShell just passes the flag.

### Cloning and resuming

```
alice@host:~$ clone https://github.com/psf/requests
[clone] git clone --progress --depth 1 https://github.com/psf/requests requests
...
^C
alice@host:~$ clone https://github.com/psf/requests
[clone] 'requests' exists — fetching + pulling to resume
[clone] updated 'requests'
```

The second call detects the existing `.git` directory and runs
`git fetch && git pull --ff-only` instead of re-cloning.

### Live monitoring

```
alice@host:~$ live-sys
termShell live-sys   frame 7   1.0s refresh
====================================================================
user@host:  alice@DESKTOP-ABC
python:     3.12.3
platform:   Windows-11-10.0.22631-SP0

CPU    [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  20.0%
MEM    [███████████████░░░░░░░░░░░░░░░░░░░░░░░]  38.4%  (6.1GB / 15.9GB)
DISK   [███████████████████░░░░░░░░░░░░░░░░░░░]  47.2%  (233.1GB / 494.0GB  cwd)

Top processes (by memory):
  PID      NAME                                      MEM
  14280    chrome.exe                              512.3MB
  ...
```

### Checking ports

```
alice@host:~$ scan
[scan] localhost (127.0.0.1) — 20 port(s)
    443  OPEN
   8080  OPEN
[scan] 2 open: [443, 8080]

alice@host:~$ ports localhost 80
localhost:80  OPEN
```

### Checking tools

```
alice@host:~$ --doctor
termShell --doctor
============================================================
termShell 1.6.0  •  Python 3.12.3  •  Windows 11
  theme:   default  (file: C:\Users\alice\.termshell_theme)
  history: 42 entries  (file: C:\Users\alice\.termshell_history)
  ANSI:    on
  plugins: 2 loaded from C:\Users\alice\.termshell\plugins
  cURL:    C:\Windows\System32\curl.exe

Languages:
  [OK]  Python             Python 3.12.3
  [OK]  Node.js            v20.11.0
  [--]  Java               not on PATH (looked for 'java')
  ...
```

### Setting a theme

```
alice@host:~$ ocean thm
theme set to 'ocean'
alice@host:~$ list thm
available themes:
  blue
  dark
  default
  green
  ...
  ocean *
  ...
```

### Querying local AI

```
alice@host:~$ ollama pull llama3.2
alice@host:~$ ai explain how TCP handshakes work
[ai] llama3.2 → explain how TCP handshakes work
The TCP three-way handshake establishes a connection...
```

---

## DIAGNOSTICS

`--doctor` exits with status 0 if all known tools are present, 1
otherwise. `--secscan` does not set a non-zero exit code for missing
tools; it is informational.

Within the shell, a builtin that raises an exception prints `name:
error` and returns to the prompt. The shell itself does not exit on
builtin failure. A `TypeError` from a zero-argument builtin is retried
with no arguments before giving up — this is how `clear` (which takes
no arguments) survives being called through the standard dispatch path.

---

## ARCHITECTURE

`termShell.py` is organized as follows:

```
constants         APP_NAME, APP_VERSION, file paths
enable_ansi()     Windows VT processing via SetConsoleMode
THEMES            dict of prompt/input/message/error ANSI codes
read_line()       raw-mode line editor (msvcrt + Ctrl+R)
HISTORY           in-memory command history
builtin_*()       one function per builtin
BUILTINS          dict mapping name → function
VERSION_TOOLS     dict mapping command → (exe, label)
check_version()   tool --version probe
check_help()      tool --help probe with truncation
show_shell_help() --help output
show_shell_version() --version output
run_doctor()      --doctor and --doctor --fix
run_secscan()     --secscan output
make_prompt()     user@host:cwd$ with cache
run_command()     dispatcher
main()            load history/theme, banner, loop
```

Dispatch order in `run_command()`:

1. `termShell <flags>` (strip name, re-dispatch)
2. `--version`, `-V`
3. `--doctor` (with optional `--fix`)
4. `--secscan`
5. `--help`
6. `--clear`
7. `<color> thm`
8. `exit` / `quit`
9. `BUILTINS[name]`
10. `check_version()`, `check_help()`
11. External command via `run_streaming()` — `shell=False` if no pipes,
    redirection, or chaining

Builtins are checked before tool probes because most commands a user
types (`cd`, `ls`, `pwd`) are builtins and should not pay the cost of
checking whether `cd --version` matches a registry entry.

---

## PERFORMANCE

External commands use `shell=False` when the command line contains no
pipe, redirection, or chaining. This avoids the `cmd.exe` spawn cost
(50-150 ms per command on Windows). When the line contains any of
`| & < > ; ( )`, termShell falls back to `shell=True` so pipes and
redirection keep working.

The prompt caches user, host, admin status, and home directory at
startup; no syscalls run per keystroke. `IsUserAnAdmin()` in particular
is a Win32 call that would otherwise run on every redraw.

The plugin directory and hashes are cached after the first scan, and
invalidated when you load or unload a plugin.

`live-sys` refreshes the process list every third frame; `tasklist` is
the dominant cost on Windows (~100 ms per spawn). Setting
`proc_refresh_every = 3` reduces the per-frame cost by about two thirds.

Cold-start time with `python -O -S` is typically 60-90 ms on a warm
filesystem. Without `-S`, add 30-80 ms for `site` initialization.

What dominates wall time in practice is the tool you're running — `git
clone` of a large repo, `npm install`, `pip download` — not termShell
itself. The shell's own contribution is in the tens of milliseconds
per command.

---

## EXIT STATUS

```
0        Normal exit (via `exit`, `quit`, or Ctrl+D).
1        `--doctor` found missing tools.
130      Interrupted by Ctrl+C during a long-running command
         (set by run_streaming when it terminates a child).
```

A child command's non-zero exit code is not propagated to termShell's
own exit status; the shell keeps running. This is standard for
interactive shells.

---

## SAFETY MODEL

termShell's safety rules, in one place:

- **No silent privilege escalation.** `sudo` uses the Windows UAC
  dialog. If you decline, nothing runs. `su` refuses to capture a
  password through the raw-mode line editor.
- **No remote scanning without explicit assertion.** `scan` is
  hardcoded to `127.0.0.1`. `ports` allows remote targets only with
  `--i-own-this-host`, and prints a legal reminder when the flag is
  used. `webtest` refuses non-local URLs entirely.
- **No packet capture.** termShell does not include a sniffer. Use
  Wireshark or tshark.
- **No auto-install of offensive tools.** `--secscan` reports and
  links; it never installs. `--doctor --fix` proposes install commands
  only for development tools, and only after confirmation.
- **No plugin execution without confirmation.** The confirmed-load,
  hash-pinned design is not configurable away. Plugins run with
  termShell's privileges; review before loading.
- **No claim of anonymity or immunity.** termShell is a shell. It
  inherits your user's privileges and your machine's network behavior.
  It cannot make you untrackable, and it cannot protect you from a
  compromised account.

If any of these rules is wrong for your use case, the answer is to
use a different tool — not to remove the rule.

---

## LIMITATIONS

By design, termShell does not:

- Perform packet capture. Use Wireshark/tshark.
- Auto-install offensive security tools. `--secscan` reports and links;
  it never installs.
- Escalate privileges silently. `sudo` uses the Windows UAC dialog and
  respects a decline.
- Scan remote hosts without an explicit flag. `scan` is hardcoded to
  127.0.0.1. `ports` accepts a remote target only with
  `--i-own-this-host`, and prints a legal reminder when the flag is
  used.
- Load plugins without confirmation. Plugins run with the same
  privileges as termShell.
- Provide anonymity or immunity from compromise.

Other limitations, not by design but by reality:

- ANSI colors require Windows Terminal or a modern `conhost`. Classic
  `conhost.exe` on older builds may print literal escape sequences;
  termShell attempts to enable VT processing via `SetConsoleMode` but
  cannot force it.
- `live-sys` requires ANSI. On terminals without VT support it refuses
  to run.
- `sudo` requires the Windows UAC prompt. If you run termShell from a
  session where UAC is disabled, elevation is not possible.
- `chmod`/`chown` on Windows print hints; they do not change
  permissions. Use `icacls` and `takeown` as printed.
- The `ai` builtin requires Ollama running at `localhost:11434`. If the
  Ollama service is not running, the command fails with a clear message.
- `live-sys` process info on Windows is only as accurate as
  `tasklist`'s CSV output, which occasionally varies across Windows
  builds. If parsing fails, the process list is empty for that frame;
  the CPU/memory/disk bars continue to work.

---

## TROUBLESHOOTING

**"warning: ANSI colors unavailable; themes will be no-ops."**
Your terminal does not support VT processing. Use Windows Terminal (the
default on Windows 11 and most Windows 10 installs). If you're on
classic `conhost.exe`, upgrade to Windows Terminal from the Microsoft
Store.

**`clear` crashes with TypeError.**
Fixed in v1.0.1. `builtin_clear` accepts an optional `args` parameter,
and the dispatcher retries with no arguments on TypeError. If you see
this, you're running an old version.

**`get` fails with "curl.exe not found on PATH".**
Windows 10 build 1803+ ships `curl.exe` in `System32`. If you're on an
older build, install cURL from https://curl.se/windows/.

**`clone` fails with "git not found on PATH".**
Install Git from https://git-scm.com/download/win.

**`ai` fails with "cannot reach Ollama at localhost:11434".**
Ollama is not running. Launch it from the Start menu, or run
`ollama list` (which starts the service if it isn't running).

**`--doctor --fix` fails with "no package manager found".**
Install one of `winget` (App Installer from the Microsoft Store),
`scoop` (https://scoop.sh), or `choco` (https://chocolatey.org).

**The prompt does not update when I `cd`.**
The prompt cache refreshes user/host/admin/home but reads `os.getcwd()`
live. If `cd` succeeds but the prompt does not change, check whether
you're in an environment where `getcwd()` throws (rare, but possible
with mapped network drives that disappear).

**A plugin I loaded yesterday re-prompts today.**
Its hash changed. Either the file was edited, or you're running a
different copy of the plugin from a different directory. Both are
correct reasons to re-prompt. If you trust the new content, answer
`y`; otherwise decline.

---

## SEE ALSO

```
bash(1), sh(1), zsh(1), powershell.exe(1), cmd.exe(1),
curl(1), git(1), ping(1), netstat(1), ss(1),
wireshark(1), tshark(1), nmap(1), ollama(1)
```

---

## BUGS

Report issues with:

- A minimal command line that reproduces the behavior.
- The output of `--version` and `--doctor`.
- Your Windows version (from `platform.platform()` in `--version`).

Known limitations are listed under LIMITATIONS. Issues that are
consequences of the design — no sniffer, no silent escalation, no
remote scan without a flag — are not bugs and will not be "fixed."

---

## LICENSE

Add your preferred license here. MIT or Apache-2.0 are common choices
for a project like this.

2. (Optional, recommended) Create `ts.bat` in the same folder:

   ```bat
   @echo off
   python -O -S "%~dp0termShell.py" %*
