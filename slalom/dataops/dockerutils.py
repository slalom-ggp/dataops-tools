""" Standard sparkutils module """

import datetime
import hashlib
import json
import time
import tempfile
import os
from shutil import copyfile
import sys

import docker
import fire

from slalom.dataops.logs import get_logger, logged, logged_block
from slalom.dataops import jobs
from slalom.dataops import io

MAX_ECS_WAIT = 12 * 60 * 60  # max 12 hours wait

docker_client = docker.from_env()
logging = get_logger("slalom.dataops.dockerutils")


def build(dockerfile_path, tag_as, addl_args=None):
    """ Build an image. 'tag_as' can be a string or list of strings """
    folder_path = os.path.dirname(dockerfile_path)
    addl_args = addl_args or ""
    tag_as = _to_list(tag_as)
    if tag_as:
        tags = " ".join([f"-t {t}" for t in tag_as])
        cmd = f"docker build {addl_args} {tags} {folder_path} -f {dockerfile_path}"
    else:
        cmd = f"docker build {addl_args} {folder_path} -f {dockerfile_path}"
    jobs.run_command(cmd)


def _to_list(str_or_list):
    if str_or_list is None:
        return []
    elif isinstance(str_or_list, str):
        return str_or_list.split(",")
    else:
        return str_or_list


def tag(image_name: str, tag_as):
    """ Tag an image. 'tag_as' can be a string or list of strings """
    tag_as = _to_list(tag_as)
    for tag in tag_as:
        jobs.run_command(f"docker tag {image_name} {tag}")


@logged("pushing image '{image_name}'")
def push(image_name):
    # docker_client.images.push(image_name)
    cmd = f"docker push {image_name}"
    jobs.run_command(cmd)


def smart_split(dockerfile_path: str, tag_as, addl_args=None):
    tag_as = _to_list(tag_as)
    if tag_as:
        interim_image_name = tag_as[0].split(":")[0]
    else:
        interim_image_name = "untitled_image"
    (image_core, dockerfile_core), (image_derived, dockerfile_derived) = _smart_split(
        dockerfile_path, interim_image_name, addl_args=addl_args
    )
    dockerfile_path_core = os.path.realpath(f"{dockerfile_path}.core")
    dockerfile_path_derived = os.path.realpath(f"{dockerfile_path}.quick")
    io.create_text_file(filepath=dockerfile_path_core, contents=dockerfile_core)
    if dockerfile_derived:
        io.create_text_file(filepath=dockerfile_path_derived, contents=dockerfile_derived)
    else:
        io.delete_file(dockerfile_path_derived, ignore_missing=True)
        dockerfile_path_derived = None
    return image_core, dockerfile_path_core, image_derived, dockerfile_path_derived


@logged("smartly building '{dockerfile_path}' as {tag_as or '(none)'}")
def smart_build(
    dockerfile_path: str,
    tag_as=None,
    push_core=True,
    push_final=False,
    with_login=False,
    addl_args=None,
    ignore_caches=False,
):
    """
    Builds the dockerfile if needed but pulls it from the remote if possible.
    """
    if bool(with_login):
        login()
    tag_as = _to_list(tag_as)
    result = smart_split(dockerfile_path, tag_as, addl_args=addl_args)
    image_core, dockerfile_path_core, image_derived, dockerfile_path_derived = result
    if not ignore_caches:
        if dockerfile_path_derived is None and exists_remotely(image_core):
            logging.info(
                "Image with matching hash already exists "
                "and no host files are referenced in Dockerfile."
                f"Attempting to retag existing image '{image_core}' as '{tag_as}'..."
            )
            return remote_retag(
                image_name=image_core.split(":")[0],
                existing_tag=image_core.split(":")[1],
                tag_as=tag_as,
            )
        pull(image_core, skip_if_exists=True, silent=True)
    if ignore_caches or not exists_locally(image_core):
        with logged_block(f"building interim (core) image as '{image_core}'"):
            build(dockerfile_path_core, image_core, addl_args=addl_args)
    if push_core:
        if ignore_caches or not exists_remotely(image_core):
            with logged_block(f"pushing interim (core) image '{image_derived}'"):
                push(image_core)
        else:
            logging.info(f"Already exists. Skipping push of image '{image_derived}'")
    with logged_block(f"building '{dockerfile_path_derived}' as '{image_derived}'"):
        if dockerfile_path_derived:
            build(dockerfile_path_derived, image_derived, addl_args=addl_args)
        else:
            tag(image_core, image_derived)
    if tag_as:
        tag(image_derived, tag_as)
        if push_final:
            for image_name in tag_as:
                push(image_name)


@logged("pulling image {image_name}")
def pull(image_name, skip_if_exists=False, silent=False):
    if skip_if_exists and exists_locally(image_name):
        logging.info(f"Skipping image pull. Already exists locally: {image_name}")
        return image_name
    else:
        try:
            jobs.run_command(f"docker pull {image_name}", raise_error=True)
        except Exception as ex:
            logging.info(f"Failed to pull image: {image_name}\n{ex}")
            if silent:
                return False
            else:
                raise ex
        if not exists_locally(image_name):
            logging.warning("Pull was successful in API but could not be confirmed")
        return image_name


def exists_locally(image_name):
    try:
        image = docker_client.images.get(image_name)
        return True
    except docker.errors.ImageNotFound as ex:
        return False


def exists_remotely(image_name):
    try:
        image = docker_client.images.get_registry_data(image_name)
        if image:
            return True
        else:
            return False
    except docker.errors.ImageNotFound as ex:
        return False
    except Exception as ex:
        logging.exception(
            f"Failure when checking if image exists remotely '{image_name}'"
        )
        return None


def _smart_split(dockerfile_path, image_name, addl_args=None):
    """ 
    Returns list of tuples: [
        (partial_image_name, partial_dockerfile_text)
        (derived_image_name, derived_dockerfile_text)
    ]
    Create two dockerfiles from a single file.
    1. The first 'core' image will contain all statements until the first COPY or ADD. 
    2. The second 'derived' image will pull from 'core' and complete the build using 
    local files or artifacts required by ADD or COPY commands.
    """
    orig_text = io.get_text_file_contents(dockerfile_path)
    addl_args = addl_args or ""
    core_dockerfile = ""
    derived_dockerfile = ""
    requires_context = False  # Whether we need file context to determine output
    for line in orig_text.split("\n"):
        if any([line.startswith("COPY"), line.startswith("ADD")]):
            requires_context = True
        if not requires_context:
            core_dockerfile += line + "\n"
        else:
            derived_dockerfile += line + "\n"
    core_md5 = hashlib.md5((addl_args + core_dockerfile).encode("utf-8")).hexdigest()
    full_md5 = hashlib.md5((addl_args + orig_text).encode("utf-8")).hexdigest()
    core_image_name = f"{image_name}:core-md5-{core_md5}"
    derived_image_name = f"{image_name}:md5-{full_md5}"

    core_dockerfile = (
        f"# NO NOT EDIT - file is generated automatically from `Dockerfile`\n\n"
        f"# Dockerfile.core - will be created and pushed as:\n"
        f"# \t{core_image_name}\n\n{core_dockerfile}"
    )
    if derived_dockerfile:
        derived_dockerfile = (
            f"# NO NOT EDIT - file is generated automatically from `Dockerfile`\n\n"
            f"FROM {core_image_name}\n\n{derived_dockerfile}"
        )
    else:
        derived_dockerfile = None  # No additional work to do.
    return [(core_image_name, core_dockerfile), (derived_image_name, derived_dockerfile)]


def ecs_login(region):
    logging.info("Logging into ECS...")
    try:
        _, ecs_login_cmd = jobs.run_command(
            f"aws ecr get-login --region {region} --no-include-email", echo=False
        )
        _, _ = jobs.run_command(ecs_login_cmd, hide=True)
    except Exception as ex:
        raise RuntimeError(f"ECS login failed. {ex}")


def login(raise_error=False):
    usr = os.environ.get("DOCKER_USERNAME", "")
    pwd = os.environ.get("DOCKER_PASSWORD", "")
    registry = os.environ.get("DOCKER_REGISTRY", "") or "index.docker.io"
    if not (usr and pwd):
        error_msg = (
            "Could not login to docker registry."
            "Missing env variable DOCKER_USERNAME or DOCKER_PASSWORD"
        )
        if raise_error:
            raise RuntimeError(error_msg)
        else:
            logging.warning(error_msg)
            return False
    logging.info(f"Logging into docker registry '{registry}' as user '{usr}'...")
    try:
        jobs.run_command(
            f"docker login {registry} --username {usr} --password {pwd}", hide=True
        )
        if registry == "index.docker.io":
            jobs.run_command(f"docker login --username {usr} --password {pwd}", hide=True)
    except Exception as ex:
        if raise_error:
            raise RuntimeError(f"Docker login failed. {ex}")
        else:
            logging.warning(f"Docker login failed. {ex}")


@logged("applying tag '{tag_as}' to remote ECS image '{image_name}:{existing_tag}'")
def ecs_retag(image_name, existing_tag, tag_as):
    tag_as = _to_list(tag_as)
    if "amazonaws.com/" in image_name:
        image_name = image_name.split("amazonaws.com/")[1]
    get_manifest_cmd = (
        f"aws ecr batch-get-image"
        f" --repository-name {image_name} --image-ids imageTag={existing_tag}"
        f" --query 'images[].imageManifest' --output text"
    )
    _, manifest = jobs.run_command(get_manifest_cmd, echo=False)
    for new_tag in tag_as:
        if "amazonaws.com/" in new_tag:
            new_tag = new_tag.split("amazonaws.com/")[1]
        if ":" in new_tag:
            if image_name != new_tag.split(":")[0]:
                raise RuntimeError(
                    f"Image names do not match: '{image_name}', '{new_tag.split(':')[0]}'"
                )
            new_tag = new_tag.split(":")[1]
        put_image_cmd = [
            "aws",
            "ecr",
            "put-image",
            "--repository-name",
            image_name,
            "--image-tag",
            new_tag,
            "--image-manifest",
            manifest,
        ]
        return_code, output_text = jobs.run_command(
            put_image_cmd, shell=False, echo=False, hide=True, raise_error=False
        )
        if return_code != 0 and "ImageAlreadyExistsException" in output_text:
            logging.info("Image already exists. No tagging changes were made.")
        elif return_code != 0:
            raise RuntimeError(f"Could not retag the specified image.\n{output_text}")


@logged("applying tag '{tag_as}' to remote image '{image_name}:{existing_tag}'")
def remote_retag(image_name, existing_tag, tag_as, with_login=False):
    tag_as = _to_list(tag_as)
    if bool(with_login):
        login()
    if "amazonaws.com/" in image_name:
        return ecs_retag(image_name, existing_tag, tag_as)
    existing_fullname = f"{image_name}:{existing_tag}"
    pull(existing_fullname)
    for new_tag in tag_as:
        if ":" in new_tag:
            new_fullname = new_tag
        else:
            new_fullname = f"{image_name}:{new_tag}"
        tag(existing_fullname, new_fullname)
        push(new_fullname)


def ecs_submit(
    task_name: str,
    cluster: str,
    region: str,
    container_name: str = None,
    cmd_override: dict = None,
    env_overrides: dict = None,
    use_fargate: str = False,
    wait_for_start=True,
    wait_for_stop=False,
    max_wait=None,
    yyyymmdd=None,
):
    cmd = (
        f"aws ecs run-task"
        f" --task-definition {task_name}"
        f" --cluster {cluster}"
        f" --region {region}"
    )
    if use_fargate:
        cmd += f" --launch-type FARGATE"
    else:
        cmd += f" --launch-type EC2"
    if env_overrides and isinstance(env_overrides, str):
        env_overrides = {
            x.split("=")[0]: x.split("=")[1] for x in env_overrides.split(",")
        }
    if yyyymmdd and yyyymmdd != "0":
        if str(yyyymmdd).lower() == "today":
            yyyymmdd = datetime.today().strftime("%Y%m%d")
        env_overrides = env_overrides or {}
        env_overrides["YYYYMMDD"] = yyyymmdd
    if env_overrides or cmd_override:
        if not container_name:
            raise ValueError(
                "container_name is required if "
                "cmd_override or env_overrides are specified"
            )
        env_override_str = ""
        cmd_override_str = ""
        if env_overrides:
            env_override_str = (
                ',"environment":['
                + ",".join(
                    [
                        "{" + f'"name":"{k}","value":"{v}"' + "}"
                        for k, v in env_overrides.items()
                    ]
                )
                + "]"
            )
        if cmd_override:
            cmd_override_str = f", 'command': ['{cmd_override}']"
        overrides = (
            ' --overrides \'{"containerOverrides":'
            f'[{{"name":"{container_name}"'
            f"{cmd_override_str}{env_override_str}"
            "}]}'"
        )
        cmd += overrides
    return_code, output_text = jobs.run_command(cmd, raise_error=False, echo=False)
    if return_code != 0:
        raise RuntimeError(f"Could not start task: {output_text}")
    jsonobj = json.loads(output_text)
    if len(jsonobj.get("tasks", [])) == 0 or len(jsonobj.get("failures", [])) > 0:
        raise RuntimeError(
            f"Could not start task ({jsonobj.get('failures', '')})\n{output_text}"
        )
    task_arn = jsonobj["tasks"][0]["taskArn"]
    logging.info(f"ECS task status: {get_ecs_task_detail_url(region, task_arn, cluster)}")
    logging.info(f"ECS task logs:   {get_ecs_log_url(region, task_arn)}")
    if wait_for_start:
        ecs_wait_for_start(task_arn=task_arn, cluster=cluster, region=region)
    if wait_for_stop:
        ecs_wait_for_stop(task_arn=task_arn, cluster=cluster, region=region)
    if not wait_for_start and not wait_for_stop:
        logging.debug(f"ECS submit result: {output_text}")
    return task_arn


def get_ecs_log_url(
    region,
    task_arn,
    container_name="PTB-Container",
    log_group="PTB-AWSLogs20190822233355860300000001",
):
    task_id = task_arn.split("/")[-1]
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home?"
        f"region={region}#logEventViewer:group={log_group};"
        f"stream=container-log/{container_name}/{task_id}"
    )


def get_ecs_task_detail_url(region, task_arn, cluster_name):
    task_id = task_arn.split("/")[-1]
    return (
        f"https://{region}.console.aws.amazon.com/ecs/home?"
        f"region={region}#/clusters/{cluster_name}/tasks/{task_id}/details"
    )


def ecs_wait_for_start(task_arn, cluster, region, timeout=1200, raise_error=True):
    return _ecs_wait_for(
        "running",
        task_arn,
        cluster,
        region,
        timeout=timeout,
        heartbeat_interval=15,
        raise_error=raise_error,
    )


def ecs_wait_for_stop(task_arn, cluster, region, timeout=1200, raise_error=True):
    return _ecs_wait_for(
        "stopped",
        task_arn,
        cluster,
        region,
        timeout=timeout,
        heartbeat_interval=2 * 60,
        raise_error=raise_error,
    )


@logged(
    "waiting for ECS status '{wait_for}'",
    success_detail=lambda: get_ecs_log_url("{region}", "{task_arn}"),
)
def _ecs_wait_for(
    wait_for,
    task_arn,
    cluster,
    region,
    timeout=1200,
    heartbeat_interval=None,
    raise_error=True,
):
    task_id = task_arn.split("/")[-1]
    wait_cmd = f"aws ecs wait tasks-{wait_for} --cluster {cluster} --tasks {task_arn}"
    desc_cmd = f"aws ecs describe-tasks --cluster {cluster} --tasks {task_arn}"

    with logged_block(
        f"waiting for ECS job to reach '{wait_for}' status",
        heartbeat_interval=heartbeat_interval,
    ):
        timeout_time = time.time() + (timeout or MAX_ECS_WAIT)
        return_code, output_text = jobs.run_command(wait_cmd, raise_error=False)
        while return_code == 255 and time.time() < timeout_time:
            logging.info("aws cli timeout expired. Retrying...")
            return_code, output_text = jobs.run_command(wait_cmd, raise_error=True)
        if return_code != 0:
            raise RuntimeError(
                f"ECS wait command failed or timed out (return={return_code}).\n"
                f"{output_text}"
            )
    return_code, output_text = jobs.run_command(desc_cmd, raise_error=False)
    if return_code != 0:
        raise RuntimeError(f"ECS task describe failed.\n{output_text}")

    jsonobj = json.loads(output_text)
    if len(jsonobj.get("tasks", [])) == 0 or len(jsonobj.get("failures", [])) > 0:
        RuntimeError(f"Could not start task ({jsonobj.get('failures', '')})")
    task_arn = jsonobj["tasks"][0]["taskArn"]
    logging.info(f"ECS task status: {get_ecs_task_detail_url(region, task_arn, cluster)}")
    logging.info(f"ECS task logs:   {get_ecs_log_url(region, task_arn)}")
    return task_arn


def main():
    fire.Fire()


if __name__ == "__main__":
    main()
