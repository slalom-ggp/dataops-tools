#!/usr/bin/env python3

import datetime
from distutils.util import strtobool
import hashlib
import inspect
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

import fire

sys.path.append("../src/")
if __name__ == "__main__" and __package__ is None:
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.join(repo_dir, "src"))

from slalom.dataops.logs import logged, get_logger, fstr, flush_all_output
from slalom.dataops import io


logging = get_logger("slalom.dataops")

DATA_REPO_ROOT = "s3://propensity-to-buy/data"
if "ARTIFACTS_ROOT" not in os.environ:
    os.environ["ARTIFACTS_ROOT"] = tempfile.mkdtemp()
ARTIFACTS_ROOT = os.environ["ARTIFACTS_ROOT"]


def init_batch_id():
    if "BATCH_ID" in os.environ:
        batch_id = os.environ["BATCH_ID"]
        logging.info(f"BATCH_ID:\t{batch_id} (detected)")
    else:
        batch_id = "{:%Y%m%d.%H%M%S}".format(datetime.datetime.now())
        os.environ["BATCH_ID"] = batch_id  # Only shared with child processes
        logging.info(f"BATCH_ID:\t{batch_id} (newly created)")
    return batch_id


# If debugging or if running in CI/CD, only do a dry run (much faster)
BATCH_ID = init_batch_id()
DEV_MODE = strtobool(os.environ.get("DEV_MODE", "0"))
DRY_RUN_MODE = DEV_MODE or ("CI" in os.environ)


def get_project_steps(path, as_dag=False):
    """ Returns the project steps either as a dag or as an ordered list. """
    if as_dag:
        raise NotImplementedError("DAG feature not yet implemented")
    else:
        return


def get_all_script_files(*scripts_folders):
    for folder in scripts_folders:
        for dirpath, _, filenames in os.walk(folder):
            for f in sorted(filenames, key=lambda x: x.replace("_", " ")):
                if ".disabled" not in f and (
                    f.lower().endswith(".r")
                    or f.lower().endswith(".py")
                    or f.lower().endswith(".sql")
                    or f.lower().endswith(".ipynb")
                ):
                    yield os.path.join(dirpath, f)


@logged(
    "replicating cache from '{source_folder}' to '{target_folder}'",
    success_detail="{len(result)} files copied",
)
def replicate_cache(source_folder, target_folder):
    if source_folder != target_folder:
        copied_files = []
        source_files = io.list_s3_files(os.path.join(source_folder, ""))
        for source_file in source_files:
            if not source_file in [
                source_folder + "/_SUCCESS",
                source_folder + "/",
                source_folder,
            ]:
                if source_folder not in source_file:
                    logging.warning(
                        f"Problem detected. Folder path '{source_folder}' not "
                        f"contained in '{source_file}'"
                    )
                target_file = source_file.replace(source_folder, target_folder)
                if target_folder not in target_file:
                    logging.warning(
                        f"Problem detected. Folder path '{target_folder}' not "
                        f"contained in '{target_file}'"
                    )
                logging.debug(f"Replicating file cache: {source_file}->{target_file}")
                io.copy_s3_file(source_file, target_file)
                copied_files.append(target_file)
        return copied_files
    else:
        logging.debug(
            "Source and target are the same. Skipping '{source_folder}' replication."
        )


@logged("'{script_file_path}' script job", buffer_lines=2)
def generate_script_output(
    script_file_path,
    parent_hash,
    batch_output_dir,
    use_cache=True,
    save_cache=True,
    replicate_cache_if_skipped=True,
    schema_only=False,
):
    """ Run the job or if code hashes match, clone resources and skip rebuild """
    file_type = script_file_path.split(".")[-1].lower()
    cmd = None
    cli_shell = False
    if file_type == "md":
        pass
    elif ".disabled" in script_file_path:
        logging.info(f"Skipping disabled file: {script_file_path}")
    elif file_type == "py":
        logging.debug(f"Identified Python script: '{script_file_path}'")
        cmd = [sys.executable, script_file_path]
    elif file_type == "r":
        logging.debug(f"Identified R script: '{script_file_path}'")
        cmd = ["Rscript", script_file_path]
        cli_shell = False
    elif file_type == "sql":
        logging.debug(f"Identified SQL script: '{script_file_path}'")
        cmd = [
            sys.executable,
            "project/scripts/ptb_model_scripts/01_feat_eng_spark.py",
            "--sql_file_path",
            script_file_path,
        ]
    else:
        raise NotImplementedError(
            f"Script type not supported: '*.{file_type}' in script '{script_file_path}'"
        )
    if cmd:
        start_time = time.time()
        log_file_name = f"{os.path.basename(script_file_path)}.log"
        log_file_path = os.path.join(ARTIFACTS_ROOT, log_file_name)
        new_running_hash = get_appended_code_hash(parent_hash, script_file_path)
        parent_cache_folder, new_cache_folder = None, None
        if use_cache:
            parent_cache_folder = get_cache_folder_path(parent_hash)
        if save_cache:
            new_cache_folder = get_cache_folder_path(new_running_hash)
        if use_cache and io.file_exists(os.path.join(new_cache_folder, "_SUCCESS")):
            logging.info(
                f"Skipping '{script_file_path}' execution "
                f"and using cache from {new_cache_folder}"
            )
            prev_log_path = os.path.join(new_cache_folder, "logs", log_file_name)
            if io.file_exists(prev_log_path):
                io.download_s3_file(prev_log_path, log_file_path)
                flush_all_output()
                with open(log_file_path, "rU", encoding="utf-8") as prev_log:
                    sys.stdout.write(
                        "\n".join(["|| " + l.rstrip() for l in prev_log.readlines()])
                    )
                flush_all_output()
            if replicate_cache_if_skipped:
                replicate_cache(new_cache_folder, batch_output_dir)
            else:
                logging.info(
                    "Skipping execution and replication of already-cached script output: "
                    f"'{script_file_path}' (cache folder: '{new_cache_folder}')"
                )
        else:
            if (
                use_cache
                and parent_cache_folder
                and io.file_exists(os.path.join(parent_cache_folder, "_SUCCESS"))
            ):
                logging.debug(
                    f"Found usable cache for '{script_file_path}' "
                    f"(hash={new_running_hash})...\n\n"
                )
                replicate_cache(parent_cache_folder, new_cache_folder)
                os.environ["OUTPUT_DIR_OVERRIDE"] = new_cache_folder
                work_dir = new_cache_folder
            else:  # not using cache
                use_cache = False
                work_dir = batch_output_dir
                if "OUTPUT_DIR_OVERRIDE" in os.environ:
                    del os.environ["OUTPUT_DIR_OVERRIDE"]  # ?Is this needed?
            logging.info(
                f"Running script '{script_file_path}' (hash={new_running_hash})...\n\n"
                f"{'-' * 80}\n"
                f"{'-' * 80}\n\n"
            )
            return_code, output_text = run_command(
                cmd,
                raise_error=True,
                log_file_path=log_file_path,
                echo=True,
                shell=cli_shell,
            )
            io.create_s3_text_file(
                os.path.join(work_dir, "logs", log_file_name), contents=output_text
            )
            logging.debug(f"Script execution completed.")
            if use_cache:
                replicate_cache(work_dir, batch_output_dir)
            elif save_cache:
                replicate_cache(work_dir, new_cache_folder)
            if save_cache:
                io.create_s3_text_file(
                    os.path.join(new_cache_folder, "_SUCCESS"), contents=""
                )
        return new_running_hash
    return parent_hash


def _grep(full_text, match_with, insensitive=True, fn=any):
    lines = full_text.splitlines()
    if isinstance(match_with, str):
        match_with = [match_with]
    if insensitive:
        return "\n".join(
            [l for l in lines if fn([m.lower() in l.lower() for m in match_with])]
        )
    else:
        return "\n".join([l for l in lines if fn([m in l for m in match_with])])


@logged("running command: {'(hidden)' if hide else cmd}")
def run_command(
    cmd: str,
    working_dir=None,
    echo=True,
    raise_error=True,
    log_file_path: str = None,
    shell=True,
    daemon=False,
    hide=False,
    cwd=None,
    wait_test=None,
    wait_max=None,
):
    """ Run a CLI command and return a tuple: (return_code, output_text) """
    loglines = []
    if working_dir:
        prev_working_dir = os.getcwd()
        os.chdir(working_dir)
    if isinstance(cmd, list):
        pass  # cmd = " ".join(cmd)
    elif platform.system() == "Windows":
        cmd = " ".join(cmd.split())
    else:
        cmd = cmd.replace("\n", " \\\n")
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        shell=shell,
        cwd=cwd,
    )
    start_time = time.time()
    if working_dir:
        os.chdir(prev_working_dir)
    if log_file_path:
        logfile = open(log_file_path, "w", encoding="utf-8")
    else:
        logfile = None
    line = proc.stdout.readline()
    flush_all_output()
    while (proc.poll() is None) or line:
        if daemon:
            if wait_max is None and wait_test is None:
                logging.info("Daemon process is launched. Returning...")
                break
            if callable(wait_test) and wait_test(line):
                logging.info(f"Returning. Wait test passed: {line}")
                break
            if wait_max and time.time() >= start_time + wait_max:
                logging.info(
                    f"{line}\nMax timeout expired (wait_max={wait_max})."
                    f" Returning..."
                )
                if callable(wait_test):
                    return_code = 1
                else:
                    return_code = 0
                break
        if line:
            line = line.rstrip()
            loglines.append(line)
            if echo:
                for l in line.splitlines():
                    sys.stdout.write(l.rstrip() + "\r\n")
            if logfile:
                logfile.write(line + "\n")
        else:
            time.sleep(0.5)  # Sleep half a second if no new output
        line = proc.stdout.readline()
    flush_all_output()
    output_text = chr(10).join(loglines)
    if logfile:
        logfile.close()
    if not proc:
        return_code = None
        raise RuntimeError(f"Command failed: {cmd}\n\n")
    else:
        return_code = proc.returncode
        if (
            return_code != 0
            and raise_error
            and ((daemon == False) or (return_code is not None))
        ):
            err_msg = f"Command failed (exit code {return_code}): {cmd}"
            if not echo:
                print_str = output_text
            elif len(output_text.splitlines()) > 10:
                print_str = _grep(
                    output_text, ["error", "exception", "warning", "fail", "deprecat"]
                )
            else:
                print_str = ""
            if print_str:
                err_msg += (
                    f"{'-' * 80}\n"
                    f"SCRIPT ERRORS:\n{'-' * 80}\n"
                    f"{print_str}\n{'-' * 80}\n"
                    f"END OF SCRIPT OUTPUT\n{'-' * 80}"
                )
            raise RuntimeError(err_msg)
    return return_code, output_text


def get_cache_folder_path(code_hash):
    DATA_REPO_ROOT = "s3://propensity-to-buy/data"
    return os.path.join(DATA_REPO_ROOT, "temp/cache", code_hash)


def get_batch_folder_path(batch_id):
    if DRY_RUN_MODE:
        return f"{DATA_REPO_ROOT}/out/dry-run=True/batch={batch_id}"
    else:
        return f"{DATA_REPO_ROOT}/out/batch={batch_id}"


def get_appended_code_hash(prev_code_hash: str, script_file_path: str):
    new_file_hash = hashlib.md5(Path(script_file_path).read_bytes()).hexdigest()
    return hashlib.md5((prev_code_hash + new_file_hash).encode("utf-8")).hexdigest()


@logged("running {len(job_steps)} jobs")
def run_jobs(job_steps, use_cache=True, save_cache=True):
    """ Execute all steps in the provided list or dag """
    if not isinstance(job_steps, list):
        raise NotImplementedError(
            "List expected. (DAG feature not yet implemented.)"
            f"Argument was: {job_steps}"
        )
    # current_file_text = inspect.getsource(inspect.getmodule(inspect.currentframe()))
    # app_version_seed = current_file_text
    app_version_seed = (
        f"Version=1.0.4;"
        f"yyyymmdd={os.environ.get('YYYYMMDD', None)};DryRun={DRY_RUN_MODE}"
    )
    running_code_hash = hashlib.md5(app_version_seed.encode("utf-8")).hexdigest()
    for i, job_step in enumerate(job_steps, 1):
        is_last_job = i == len(job_steps)
        output_dir = get_batch_folder_path(BATCH_ID)
        running_code_hash = generate_script_output(
            script_file_path=job_step,
            parent_hash=running_code_hash,
            batch_output_dir=output_dir,
            use_cache=use_cache,
            save_cache=save_cache,
            replicate_cache_if_skipped=is_last_job,
        )
