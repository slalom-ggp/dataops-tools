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


def build(dockerfile_path, tag_as):
    """ Build an image. 'tag_as' can be a string or list of strings """
    folder_path = os.path.dirname(dockerfile_path)
    if tag_as:
        if isinstance(tag_as, str):
            tag_as = [tag_as]
        tags = " ".join([f"-t {t}" for t in tag_as])
        cmd = f"docker build {tags} {folder_path} -f {dockerfile_path}"
    else:
        cmd = f"docker build {folder_path} -f {dockerfile_path}"
    jobs.run_command(cmd)


def tag(image_name: str, tag_as):
    """ Tag an image. 'tag_as' can be a string or list of strings """
    if tag_as:
        if isinstance(tag_as, str):
            tag_as = [tag_as]
    for tag in tag_as:
        jobs.run_command(f"docker tag {image_name} {tag}")


@logged("pushing image '{image_name}'")
def push(image_name):
    # docker_client.images.push(image_name)
    cmd = f"docker push {image_name}"
    jobs.run_command(cmd)


def smart_split(dockerfile_path: str, tag_as):
    if tag_as:
        if isinstance(tag_as, str):
            tag_as = [tag_as]
    (image_core, dockerfile_core), (image_derived, dockerfile_derived) = _smart_split(
        dockerfile_path, tag_as[0].split(":")[0]
    )
    dockerfile_path_core = os.path.realpath(f"{dockerfile_path}.core")
    dockerfile_path_derived = os.path.realpath(f"{dockerfile_path}.quick")
    io.create_text_file(filepath=dockerfile_path_core, contents=dockerfile_core)
    io.create_text_file(filepath=dockerfile_path_derived, contents=dockerfile_derived)
    return image_core, dockerfile_path_core, image_derived, dockerfile_path_derived


@logged("smartly building '{dockerfile_path}'")
def smart_build(dockerfile_path: str, tag_as, push_core=True):
    """
    Builds the dockerfile if needed but pulls it from the remote if possible.
    """
    if tag_as:
        if isinstance(tag_as, str):
            tag_as = [tag_as]

    image_core, dockerfile_path_core, image_derived, dockerfile_path_derived = smart_split(
        dockerfile_path, tag_as
    )
    # pull(image_derived, skip_if_exists=True, silent=True)
    # if not exists_locally(image_derived):
    #     pull(image_core, skip_if_exists=True, silent=True)
    pull(image_core, skip_if_exists=True, silent=True)
    if not exists_locally(image_core):
        with logged_block(f"building interim (core) image as '{image_core}'"):
            build(dockerfile_path_core, image_core)
    if push_core:
        if exists_remotely(image_core):
            logging.info(f"Already exists. Skipping push of image '{image_derived}'")
        else:
            with logged_block(f"pushing interim (core) image '{image_derived}'"):
                push(image_core)
    with logged_block(f"building '{dockerfile_path_derived}' as '{image_derived}'"):
        build(dockerfile_path_derived, image_derived)
    tag(image_derived, tag_as)


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
        logging.exception("Failure when checking if image exists remotely '{image_name}'")
        return None


def _smart_split(dockerfile_path, image_name):
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
    core_md5 = hashlib.md5(core_dockerfile.encode("utf-8")).hexdigest()
    full_md5 = hashlib.md5(orig_text.encode("utf-8")).hexdigest()
    core_image_name = f"{image_name}:core-md5-{core_md5}"
    derived_image_name = f"{image_name}:md5-{full_md5}"

    core_dockerfile = (
        f"# NO NOT EDIT - file is generated automatically from `Dockerfile`\n\n"
        f"# Dockerfile.core - will be created and pushed as:\n"
        f"# \t{core_image_name}\n\n{core_dockerfile}"
    )
    derived_dockerfile = (
        f"# NO NOT EDIT - file is generated automatically from `Dockerfile`\n\n"
        f"FROM {core_image_name}\n\n{derived_dockerfile}"
    )

    return [(core_image_name, core_dockerfile), (derived_image_name, derived_dockerfile)]


def ecs_login(region):
    logging.info("Logging into ECS...")
    try:
        _, ecs_login_cmd = jobs.run_command(
            f"aws ecr get-login --region {region} --no-include-email", echo=False
        )
        _, _ = jobs.run_command(ecs_login_cmd, hide=True)
    except Exception as ex:
        raise RuntimeError("ECS login failed. {ex}")


@logged("applying tag '{new_tag}' to remote ECS image '{image_name}:{existing_tag}'")
def ecs_retag(image_name, existing_tag, new_tag):
    if "amazonaws.com/" in image_name:
        image_name = image_name.split("amazonaws.com/")[1]
    get_manifest_cmd = (
        f"aws ecr batch-get-image"
        f" --repository-name {image_name} --image-ids imageTag={existing_tag}"
        f" --query 'images[].imageManifest' --output text"
    )
    _, manifest = jobs.run_command(get_manifest_cmd, echo=False)
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
    success_detail=lambda: get_ecs_log_url(f"{region}", f"{task_arn}"),
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


if __name__ == "__main__":
    fire.Fire()
