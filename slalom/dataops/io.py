import os
import tempfile
from pathlib import Path
import shutil

import fire

from slalom.dataops.logs import get_logger, logged, logged_block
from slalom.dataops import jobs

logging = get_logger("slalom.dataops")


def warn_failed_import(library_name, install_hint):
    logging.warning(
        f"Could not load '{library_name}' library. Some functionality may be disabled. "
        f"Please confirm '{library_name}' is installed or install via '{install_hint}'."
    )


try:
    import pandas as pd
except Exception as ex:
    pd = None
    warn_failed_import("pandas", "pip install pandas")
try:
    import boto3
except Exception as ex:
    boto3 = None
    warn_failed_import("boto3", "pip install boto3")
try:
    import s3fs
except Exception as ex:
    s3fs = None
    warn_failed_import("s3fs", "pip install s3fs")

try:
    from azure.datalake.store import core, lib, multithread
    from azure.datalake.store.core import AzureDLFileSystem
    from azure.common.client_factory import get_client_from_cli_profile
except Exception as ex:
    logging.warning(f"Azure libraries not loaded: {ex}")
try:
    tenant = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]
    RESOURCE = "https://datalake.azure.net/"
    adlCreds = lib.auth(
        tenant_id=tenant,
        client_secret=client_secret,
        client_id=client_id,
        resource=RESOURCE,
    )
except Exception as ex:
    logging.warning(f"Azure creds not loaded: {ex}")


SAFE_PATHS = []

# Enforcement of write safety
def set_safe_paths(list_of_paths):
    """ Set list of safe writeable paths """
    global SAFE_PATHS
    SAFE_PATHS = list_of_paths


USE_SCRATCH_DIR = os.environ.get("USE_SCRATCH_DIR", False)
_scratch_dir = None
_tmpdir = None


def get_temp_dir():
    global _tmpdir

    if not _tmpdir:
        _tmpdir = tempfile.mkdtemp()
    return _tmpdir


def get_scratch_dir():
    global _scratch_dir

    if not _scratch_dir:
        _scratch_dir = get_temp_dir()
        os.environ["SCRATCH_DIR"] = _scratch_dir
    return _scratch_dir


# Helper functions
def _check_one_or_all(string_or_list, fn, agg_fn=all):
    if isinstance(string_or_list, str):
        string = string_or_list
        return fn(string)
    else:
        return agg_fn([fn(string) for string in string_or_list])


# Path parsing
def cleanup_filepath(filepath):
    if "%USERPROFILE%" in filepath and "USERPROFILE" in os.environ:
        filepath = filepath.replace("%USERPROFILE%", os.environ["USERPROFILE"])
    filepath = filepath.replace("s3a://", "s3://")
    return filepath


def parse_s3_path(s3_path):
    """ Returns tuple (bucket_name, object_key) """
    path_parts = s3_path.replace("s3://", "").split("/")
    bucket_name, object_key = path_parts[0], "/".join(path_parts[1:])
    return bucket_name, object_key


def parse_adl_path(adl_path):
    """ Returns tuple (store_name, object_key) """
    path_parts = adl_path.replace("adl://", "").split("/")
    store_name = path_parts[0].replace(".azuredatalakestore.net", "")
    object_key = "/".join(path_parts[1:])
    return store_name, object_key


def parse_git_path(git_path):
    """ Returns tuple (repo_url, git_ref, code_path) """
    git_ref = "master"
    repo_url, code_path = git_path.replace("git://", "").split("//")
    if "#" in repo_url:
        repo_url, git_ref = repo_url.split("#")
    repo_url = repo_url.rstrip(".git")
    if not code_path:
        code_path = "/"
    return repo_url, git_ref, code_path


def is_s3(path_or_paths, agg_fn=all):
    check_fn = lambda s: s.startswith("s3")
    return _check_one_or_all(path_or_paths, check_fn, agg_fn)


def is_adl(path_or_paths, agg_fn=all):
    check_fn = lambda s: s.startswith("adl")
    return _check_one_or_all(path_or_paths, check_fn, agg_fn)


def is_git(path_or_paths, agg_fn=all):
    check_fn = lambda s: s.startswith("git")
    return _check_one_or_all(path_or_paths, check_fn, agg_fn)


def _pick_cloud_function(filepath, s3_fn, adl_fn, git_fn=None, else_fn=None):
    if is_s3(filepath):
        fn = s3_fn
    elif is_adl(filepath):
        fn = adl_fn
    elif is_git(filepath):
        fn = git_fn
    else:
        fn = else_fn
    if not fn:
        raise NotImplemented()
    return fn


# General file operations
def file_exists(filepath):
    filepath = cleanup_filepath(filepath)
    fn = _pick_cloud_function(
        filepath, s3_fn=s3_file_exists, adl_fn=adl_file_exists, else_fn=os.path.exists
    )
    return fn(filepath)


def s3_file_exists(filepath):
    s3 = s3fs.S3FileSystem(anon=False)
    return s3.exists(filepath)


def adl_file_exists(filepath):
    store_name, path = parse_adl_path(filepath)
    adl = core.AzureDLFileSystem(adlCreds, store_name=store_name)
    return adl.exists(path)


def list_files(file_prefix):
    fn = _pick_cloud_function(
        file_prefix,
        s3_fn=list_s3_files,
        adl_fn=list_adl_files,
        else_fn=lambda prefix: [os.path.join(prefix, x) for x in os.listdir(prefix)],
    )
    return fn(file_prefix)


# Function Aliases:
ls = list_files
dir = list_files


@logged("listing S3 files from '{s3_prefix}'")
def list_s3_files(s3_prefix):
    boto = boto3.resource("s3")
    bucket_name, folder_key = parse_s3_path(s3_prefix)
    s3_bucket = boto.Bucket(bucket_name)
    file_list = []
    for object_summary in s3_bucket.objects.filter(Prefix=folder_key):
        if object_summary.key[-1] == "/":
            pass  # key is a directory
        else:
            file_list.append(os.path.join("s3://", bucket_name, object_summary.key))
    return file_list


def list_adl_files(adl_path_prefix):
    store_name, path_prefix = parse_adl_path(adl_path_prefix)
    adl = core.AzureDLFileSystem(adlCreds, store_name=store_name)
    root = adl_path_prefix.split(path_prefix)[0]
    files = adl.walk(path_prefix)
    return [f"{root}{result}" for result in files]


# File copy
def copy_s3_file(s3_source_file, s3_target_file):
    s3 = s3fs.S3FileSystem(anon=False)
    s3.cp(s3_source_file, s3_target_file)


def copy_adl_file(adl_source_file, adl_target_file):
    raise NotImplemented()


def copy_file(source_file, target_file):
    if is_s3([source_file, target_file]):
        copy_s3_file(source_file, target_file)
    elif is_adl([source_file, target_file]):
        copy_adl_file(source_file, target_file)
    elif is_adl([source_file, target_file], any) and is_adl(
        [source_file, target_file], any
    ):
        tmp_path = download_file(source_file)
        upload_file(tmp_path, target_file)
    else:
        raise shutil.copyfile(source_file, target_file)


# File deletion
def delete_file(filepath, ignore_missing=True):
    fn = _pick_cloud_function(
        filepath, s3_fn=delete_s3_file, adl_fn=delete_adl_file, else_fn=delete_local_file
    )
    return fn(filepath, ignore_missing=ignore_missing)


def delete_s3_file(s3_filepath, ignore_missing=True):
    if ignore_missing and not s3_file_exists(s3_filepath):
        return None
    boto = boto3.resource("s3")
    bucket_name, object_key = parse_s3_path(s3_filepath)
    boto.Object(bucket_name, object_key).delete()


def delete_adl_file(adl_filepath, ignore_missing=True):
    if ignore_missing and not adl_file_exists(adl_filepath):
        return None
    store_name, filepath = parse_adl_path(adl_filepath)
    adl = core.AzureDLFileSystem(adlCreds, store_name=store_name)
    return adl.rm(filepath)


def delete_local_file(filepath, ignore_missing=True):
    if ignore_missing and not os.path.exists(filepath):
        return None
    os.remove(filepath)


# File writes and uploads
def upload_file(local_path, remote_path):
    fn = _pick_cloud_function(
        remote_path, s3_fn=upload_s3_file, adl_fn=upload_adl_file, else_fn=None
    )
    return fn(local_path, remote_path)


def upload_adl_file(local_path, adl_filepath):
    store_name, filepath = parse_adl_path(adl_filepath)
    adl = core.AzureDLFileSystem(adlCreds, store_name=store_name)
    multithread.ADLUploader(
        adl,
        lpath=local_path,
        rpath=filepath,
        nthreads=12,  # WAS: 64, reduced to resolve mem issue: https://github.com/Azure/azure-data-lake-store-python/issues/56
        overwrite=True,
        buffersize=4194304,
        blocksize=4194304,
    )


def upload_s3_file(local_path, s3_filepath):
    s3 = boto3.client("s3")
    bucket_name, object_key = parse_s3_path(s3_filepath)
    s3.upload_file(local_path, bucket_name, object_key)  # SAFE


def create_s3_text_file(s3_filepath, contents):
    s3 = boto3.client("s3")
    path_parts = s3_filepath.replace("s3://", "").split("/")
    bucket_name, file_key = path_parts[0], "/".join(path_parts[1:])
    _ = s3.put_object(Bucket=bucket_name, Body=contents, Key=file_key)


def create_text_file(filepath, contents):
    fn = _pick_cloud_function(
        filepath,
        s3_fn=create_s3_text_file,
        adl_fn=None,
        else_fn=lambda filepath, contents: Path(filepath).write_text(contents),
    )
    return fn(filepath, contents)


# Folder operations
def create_s3_folder(s3_folderpath):
    s3 = boto3.client("s3")
    bucket_name, folder_key = parse_s3_path(s3_folderpath)
    if not folder_key.endswith("/"):
        folder_key = folder_key + "/"
    _ = s3.put_object(Bucket=bucket_name, Body="", Key=folder_key)


def create_folder(folderpath):
    fn = _pick_cloud_function(
        folderpath,
        s3_fn=create_s3_folder,
        adl_fn=None,
        else_fn=lambda folderpath: Path(folderpath).mkdir(parents=True, exist_ok=True),
    )
    return fn(folderpath)


# File downloads
def download_file(remote_path, local_path):
    fn = _pick_cloud_function(
        remote_path, s3_fn=download_s3_file, adl_fn=None, else_fn=shutil.copyfile
    )
    return fn(remote_path, local_path)


@logged(desc_detail="{s3_path}::{local_path}")
def download_s3_file(s3_path, local_path):
    boto = boto3.resource("s3")
    bucket_name, object_key = parse_s3_path(s3_path)
    s3_bucket = boto.Bucket(bucket_name)
    s3_bucket.download_file(object_key, local_path)


def get_text_file_contents(filepath, encoding="utf-8"):
    filepath = cleanup_filepath(filepath)
    with open(filepath, "r", encoding=encoding) as f:
        return f.read()


# Folder downloads:
@logged(desc_detail="{remote_folder}::{local_folder}")
def download_folder(remote_folder, local_folder, as_subfolder=False):
    """ Expects that destination folder does not exist or is empty """
    if as_subfolder:
        local_folder = f"{local_folder}/{os.basename(remote_folder)}"
    fn = _pick_cloud_function(
        remote_folder,
        s3_fn=download_s3_folder,
        adl_fn=_download_folder,
        git_fn=download_git_folder,
        else_fn=_download_folder,
    )
    return fn(remote_folder, local_folder)


@logged(desc_detail="{remote_folder}::{local_folder}")
def _download_folder(remote_folder, local_folder):
    for remote_filepath in list_files(remote_folder):
        sub_path = remote_filepath.split(remote_folder)[1]
        sub_path = sub_path.lstrip("/\\")
        local_filepath = os.path.join(local_folder, sub_path)
        logging.info(f"Copying {remote_filepath} to {local_filepath}...")
        download_file(remote_filepath, local_filepath)


# Alias 'copy_folder'
copy_folder = download_folder


@logged(desc_detail="{s3_prefix}::{local_folder}")
def download_s3_folder(s3_prefix, local_folder):
    for s3_file in list_s3_files(os.path.join(s3_prefix, "")):
        target_file = os.path.join(local_folder, os.path.basename(s3_file))
        download_s3_file(s3_file, target_file)


def download_git_repo(repo_url, git_ref, target_dir):
    jobs.run_command(f"git clone https://{repo_url} .", cwd=target_dir)
    if git_ref != "master":
        jobs.run_command(f"git fetch", cwd=target_dir)
        jobs.run_command(f"git checkout {git_ref}", cwd=target_dir)


def download_git_folder(git_path, local_folder):
    repo_url, git_ref, code_path = parse_git_path(git_path)
    temp_folder = get_temp_dir()
    download_git_repo(repo_url, git_ref, temp_folder)
    copy_folder(os.path.join(temp_folder, code_path), local_folder)


# Function wrappers for cloud IO
def s3write_using(func, *args, **kwargs):
    """ Send any function's output to s3 """
    newargs = []
    newkwargs = kwargs.copy()
    temp_path_map = {}
    for arg in args:
        if isinstance(arg, str) and arg.startswith("s3"):
            tmppath = tempfile.NamedTemporaryFile(delete=False).name
            temp_path_map[tmppath] = str(arg.replace("s3a:", "s3:"))
            newargs.append(tmppath)
        else:
            newargs.append(arg)
    for k, v in kwargs.items():
        if isinstance(v, str) and v.startswith("s3"):
            tmppath = tempfile.NamedTemporaryFile(delete=False).name
            temp_path_map[tmppath] = str(v.replace("s3a:", "s3:"))
            newkwargs[k] = tmppath
    func(*newargs, **newkwargs)
    if temp_path_map:
        s3 = boto3.client("s3")
        for local_path, s3_path in temp_path_map.items():
            if SAFE_PATHS and not any([s3_path in safepath for safepath in SAFE_PATHS]):
                raise RuntimeError(
                    f"Path '{s3_path}' cannot be written to because it is not in the "
                    f"designated safe output paths: '{', '.join(SAFE_PATHS)}'"
                )
            logging.info(f"Uploading file to S3: {s3_path}")
            upload_s3_file(local_path, s3_path)
            os.remove(local_path)
        logging.info(f"S3 upload(s) complete!")


def s3read_using(func, *args, **kwargs):
    """ Send any function's output to s3 """
    newargs = []
    newkwargs = kwargs.copy()
    tmpfolder = tempfile.gettempdir()
    temp_path_map = {}
    for arg in args:
        if isinstance(arg, str) and arg.startswith("s3"):
            tmppath = os.path.join(tmpfolder, os.path.basename(arg))
            temp_path_map[tmppath] = str(arg.replace("s3a:", "s3:"))
            newargs.append(tmppath)
        else:
            newargs.append(arg)
    for k, v in kwargs.items():
        if isinstance(v, str) and v.startswith("s3"):
            tmppath = os.path.join(tmpfolder, os.path.basename(arg))
            temp_path_map[tmppath] = str(v.replace("s3a:", "s3:"))
            newkwargs[k] = tmppath
    if temp_path_map:
        for local_path, s3_path in temp_path_map.items():
            logging.info(f"Download file from S3: {s3_path}")
            download_s3_file(s3_path, local_path)
        logging.info(f"S3 download(s) complete!")
    logging.debug(
        "s3read_using() is running function with the following args:\n"
        f"{str(newargs)}\n{str(newkwargs)}"
    )
    result = func(*newargs, **newkwargs)
    if temp_path_map:
        for local_path, _ in temp_path_map.items():
            logging.info(f"Deleting temporary local file: {local_path}")
            os.remove(local_path)
    return result


def main():
    fire.Fire()


if __name__ == "__main__":
    main()
