"""
Helper for running LibreOffice (soffice) headless in sandboxed environments
where AF_UNIX sockets may be blocked, and where custom fonts need to be
visible to the conversion.

Adapted from the pattern used by Anthropic's bundled `pptx` skill
(scripts/office/soffice.py) — same AF_UNIX shim, plus a `fonts_dir` argument
so this skill's repaired decks render with the correct typefaces instead of
silently falling back to Calibri/Arial.

Call soffice through run_soffice(), not through subprocess directly: the
shim and the per-run user profile both matter for headless reliability in
a locked-down container.
"""

import contextlib
import os
import socket
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path


def get_soffice_env() -> dict:
    env = os.environ.copy()
    env["SAL_USE_VCLPLUGIN"] = "svp"

    if _needs_shim():
        shim = _ensure_shim()
        env["LD_PRELOAD"] = str(shim)

    return env


def run_soffice(args: Iterable[str], **kwargs) -> subprocess.CompletedProcess:
    args = list(args)
    with contextlib.ExitStack() as stack:
        if not any(str(a).startswith("-env:UserInstallation") for a in args):
            profile = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="lo_profile_", ignore_cleanup_errors=True)
            )
            args = [f"-env:UserInstallation={Path(profile).as_uri()}"] + args
        return subprocess.run(["soffice"] + args, env=get_soffice_env(), **kwargs)


def convert_to_pdf(input_path: str, out_dir: str, fonts_dir: str | None = None, timeout: int = 180) -> Path:
    """Convert a single office document to PDF via headless LibreOffice.

    `fonts_dir` is accepted for call-site compatibility but installing
    fonts is fonts.ensure_fonts_available()'s job — by the time this runs,
    the fonts a deck needs should already be sitting in a directory
    fontconfig scans by default (see fonts.py), and a plain `fc-cache -f`
    (already run there) is what makes soffice see them. There's nothing
    soffice-specific to configure here.

    Returns the path to the produced PDF. Raises RuntimeError on failure.
    """
    input_path = Path(input_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_soffice(
        ["--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(out_dir), str(input_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    produced = out_dir / (input_path.stem + ".pdf")
    if result.returncode != 0 or not produced.is_file():
        raise RuntimeError(
            "soffice conversion failed "
            f"(exit {result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return produced


_SHIM_SO = Path(tempfile.gettempdir()) / "der_socket_shim.so"


def _needs_shim() -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.close()
        return False
    except OSError:
        return True


def _ensure_shim() -> Path:
    if _SHIM_SO.exists():
        return _SHIM_SO

    src = Path(tempfile.gettempdir()) / "der_socket_shim.c"
    src.write_text(_SHIM_SOURCE)
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-o", str(_SHIM_SO), str(src), "-ldl"],
        check=True,
        capture_output=True,
    )
    src.unlink()
    return _SHIM_SO


_SHIM_SOURCE = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static int (*real_socket)(int, int, int);
static int (*real_socketpair)(int, int, int, int[2]);
static int (*real_listen)(int, int);
static int (*real_accept)(int, struct sockaddr *, socklen_t *);
static int (*real_close)(int);
static int (*real_read)(int, void *, size_t);

static int is_shimmed[1024];
static int peer_of[1024];
static int wake_r[1024];
static int wake_w[1024];
static int listener_fd = -1;

__attribute__((constructor))
static void init(void) {
    real_socket     = dlsym(RTLD_NEXT, "socket");
    real_socketpair = dlsym(RTLD_NEXT, "socketpair");
    real_listen     = dlsym(RTLD_NEXT, "listen");
    real_accept     = dlsym(RTLD_NEXT, "accept");
    real_close      = dlsym(RTLD_NEXT, "close");
    real_read       = dlsym(RTLD_NEXT, "read");
    for (int i = 0; i < 1024; i++) {
        peer_of[i] = -1;
        wake_r[i]  = -1;
        wake_w[i]  = -1;
    }
}

int socket(int domain, int type, int protocol) {
    if (domain == AF_UNIX) {
        int fd = real_socket(domain, type, protocol);
        if (fd >= 0) return fd;
        int sv[2];
        if (real_socketpair(domain, type, protocol, sv) == 0) {
            if (sv[0] >= 0 && sv[0] < 1024) {
                is_shimmed[sv[0]] = 1;
                peer_of[sv[0]]    = sv[1];
                int wp[2];
                if (pipe(wp) == 0) {
                    wake_r[sv[0]] = wp[0];
                    wake_w[sv[0]] = wp[1];
                }
            }
            return sv[0];
        }
        errno = EPERM;
        return -1;
    }
    return real_socket(domain, type, protocol);
}

int listen(int sockfd, int backlog) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        listener_fd = sockfd;
        return 0;
    }
    return real_listen(sockfd, backlog);
}

int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        if (wake_r[sockfd] >= 0) {
            char buf;
            real_read(wake_r[sockfd], &buf, 1);
        }
        errno = ECONNABORTED;
        return -1;
    }
    return real_accept(sockfd, addr, addrlen);
}

int close(int fd) {
    if (fd >= 0 && fd < 1024 && is_shimmed[fd]) {
        int was_listener = (fd == listener_fd);
        is_shimmed[fd] = 0;

        if (wake_w[fd] >= 0) {
            char c = 0;
            write(wake_w[fd], &c, 1);
            real_close(wake_w[fd]);
            wake_w[fd] = -1;
        }
        if (wake_r[fd] >= 0) { real_close(wake_r[fd]); wake_r[fd]  = -1; }
        if (peer_of[fd] >= 0) { real_close(peer_of[fd]); peer_of[fd] = -1; }

        if (was_listener)
            _exit(0);
    }
    return real_close(fd);
}
"""


if __name__ == "__main__":
    import sys
    result = run_soffice(sys.argv[1:])
    sys.exit(result.returncode)
