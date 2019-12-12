#!/usr/bin/env python3
import os
import platform
import sys

import fire

from slalom.dataops.logs import get_logger, logged, logged_block
from slalom.dataops import jobs, io

if os.name == "nt":
    import ctypes
else:
    ctypes = None


CACHED_INSTALL_LIST: str = None
DEBUG = False
logging = get_logger("slalom.dataops.env", debug=DEBUG)

CHOCO_INSTALL_CMD = """
@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
""".strip()
WINDOWS_INSTALL_LIST = {
    "chocolatey": CHOCO_INSTALL_CMD,
    "chocolateygui": None,
    "sudo": None,
    "git": 'choco install -y git.install --params "/GitOnlyOnPath /SChannel /NoAutoCrlf /WindowsTerminal"',
    "docker": "docker-desktop",
    "python": "python3",
    "terraform": None,
    "vscode": None,
}
LINUX_INSTALL_LIST = {"docker": "docker.io", "docker-compose": "docker-compose"}
MAC_INSTALL_LIST = {"docker": "brew cask install docker && open /Applications/Docker.app"}


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_mac() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def status():
    check_installs(install_if_missing=False)


def _to_list(str_or_list):
    if str_or_list is None:
        return []
    elif isinstance(str_or_list, str):
        return str_or_list.split(",")
    else:
        return str_or_list


def is_admin():
    if is_linux() or is_mac():
        return os.geteuid() == 0
    elif is_windows():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return None


def rerun_as_admin(prompt=True):
    if is_admin():
        return
    else:  # Re-run the program with admin rights
        args = " ".join(sys.argv[1:])
        response = "y"
        if prompt:
            response = input(
                f"While executing '{sys.executable} {__file__} {args}' we detected "
                f"that you do not have admin/root permissions.\n"
                f"Would you like to rerun this program as admin? [y/n]"
            ).lower()
        if response in ["y", "yes"]:
            return run_as_admin(
                wait=True, cmd=[sys.executable] + [__file__] + sys.argv[1:]
            )
        elif response in ["n", "no"]:
            return None
        else:
            raise RuntimeError("Invalid response.")


@logged("running {' '.join(cmd or [])}")
def run_as_admin(cmd: list = None, wait=True):

    if os.name != "nt":
        raise NotImplementedError("This function is only implemented on Windows.")

    import win32api, win32con, win32event, win32process
    from win32com.shell.shell import ShellExecuteEx
    from win32com.shell import shellcon
    import types

    if cmd is None:
        cmd = [sys.executable] + sys.argv
    process = '"%s"' % (cmd[0],)
    params = " ".join(['"%s"' % (x,) for x in cmd[1:]])
    cmdDir = ""
    showCmd = win32con.SW_SHOWNORMAL
    procInfo = ShellExecuteEx(
        nShow=showCmd,
        fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
        lpVerb="runas",
        lpFile=process,
        lpParameters=params,
    )
    if wait:
        procHandle = procInfo["hProcess"]
        obj = win32event.WaitForSingleObject(procHandle, win32event.INFINITE)
        rc = win32process.GetExitCodeProcess(procHandle)
        print(f"Return code: {rc}")
    else:
        rc = None
    return rc


def check_installs(install_list=None, install_if_missing: bool = None):
    if is_windows():
        ref_list = WINDOWS_INSTALL_LIST
    elif is_linux():
        ref_list = LINUX_INSTALL_LIST
    elif is_mac():
        ref_list = MAC_INSTALL_LIST
    else:
        raise RuntimeError("Could not detect OS type.")
    install_list = {
        program: ref_list.get(program.lower(), None)
        for program in (_to_list(install_list) or ref_list.keys())
    }
    missing = {}
    for name, install_cmd in install_list.items():
        installed = check_install(name, install_if_missing, install_cmd)
        logging.info(f"{name}: {'OK' if installed else 'Not installed'}")
        if not installed:
            missing[name] = install_cmd
    if install_if_missing is None and missing:  # prompt if not specified
        if input(
            f"The following software components appear to be missing: {','.join(missing.keys())}\n"
            f"Would you like to install them? [y/n] "
        ).lower() in ["y", "yes"]:
            for program, install_cmd in missing.items():
                install(program, install_cmd)


def check_install(
    program_name: str, install_if_missing: bool = None, install_cmd: str = None
) -> bool:
    installed = False
    installed_programs = get_installed_programs()
    installed = program_name.lower() in installed_programs.keys()
    if not installed:
        for test_cmd in [f"{program_name} --version", f"which {program_name}"]:
            return_code, output = jobs.run_command(test_cmd, raise_error=False)
            if return_code == 0 and len(output) > 1:
                installed = True
                break
    if install_if_missing and not installed:
        install(program_name, install_cmd)
        installed = True
    return installed


def _default_install_cmd(program_name):
    if is_windows():
        return f"choco install -y {program_name}"
    elif is_linux():
        return f"apt-get install -y {program_name}"
    elif is_mac():
        return f"choco install {program_name}"
    else:
        raise RuntimeError("Could not detect OS type.")


def get_installed_programs():
    global CACHED_INSTALL_LIST

    if CACHED_INSTALL_LIST:
        return CACHED_INSTALL_LIST
    if is_windows():
        return_code, output = jobs.run_command("choco list --local", raise_error=False)
        if return_code == 0:
            CACHED_INSTALL_LIST = {
                x.split(" ")[0].lower(): x.split(" ")[1]
                for x in output.split("\n")
                if len(x.split(" ")) == 2
            }
        else:
            CACHED_INSTALL_LIST = {}
    elif is_linux():
        CACHED_INSTALL_LIST = {}
    elif is_mac():
        CACHED_INSTALL_LIST = {}
    return CACHED_INSTALL_LIST


@logged("installing {program_name}")
def install(program_name, install_cmd):
    if not install_cmd:
        install_cmd = _default_install_cmd(program_name=program_name)
    elif " " not in install_cmd:
        install_cmd = _default_install_cmd(program_name=install_cmd)
    if not is_admin():
        return_code = run_as_admin(cmd=install_cmd.split(" "), prompt=True)
    else:
        return_code, output = jobs.run_command(install_cmd)
    return return_code == 0


if __name__ == "__main__":
    fire.Fire()
