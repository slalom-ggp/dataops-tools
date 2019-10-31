terraform {
  backend "s3" {
    bucket = "propensity-to-buy"
    key    = "infra/dataops-pkg-state"
    region = "us-east-2"
  }
}

data "aws_caller_identity" "current" {}
data "local_file" "config_yml" { filename = "config.yml" }

locals { config = yamldecode(data.local_file.config_yml.content) }
locals {
  aws_account                     = data.aws_caller_identity.current.account_id
  project_shortname               = local.config["project_shortname"]
  aws_region                      = local.config["region"]
  ecs_prefer_fargate              = local.config["ecs_ec2_instances"] == 0 ? true : false
  ecs_fargate_container_num_cores = local.config["ecs_fargate_container_num_cores"]
  ecs_fargate_container_ram_gb    = local.config["ecs_fargate_container_ram_gb"]
  ecs_ec2_instance_type           = local.config["ecs_ec2_instance_type"]
  ecs_ec2_instances               = local.config["ecs_ec2_instances"]
  ecs_ec2_container_num_cores     = local.config["ecs_ec2_container_num_cores"]
  ecs_ec2_container_ram_gb        = local.config["ecs_ec2_container_ram_gb"]
  tableau_instance_type           = local.config["tableau_instance_type"]
  tableau_linux_servers           = local.config["tableau_linux_servers"]
  tableau_windows_servers         = local.config["tableau_windows_servers"]
  tableau_registration_file       = local.config["tableau_registration_file"]
  aws_secret_name_prefix = lookup(
    local.config,
    "aws_secret_name_prefix",
    "${upper(local.config["project_shortname"])}_SECRETS"
  )
}
locals {
  aws_secrets_manager = "arn:aws:secretsmanager:${local.aws_region}:${local.aws_account}:secret:${local.aws_secret_name_prefix}"
  name_prefix         = "${local.project_shortname}-"
}

provider "aws" {
  region  = local.aws_region
  version = "~> 2.10"
}

module "aws_vpc" {
  source      = "./modules/aws-vpc"
  name_prefix = local.name_prefix
}

module "ecr_docker_registry" {
  source            = "./modules/aws-ecr"
  repository_name   = "${local.name_prefix}Docker-Registry"
  image_name        = lower(local.project_shortname)
  project_shortname = local.project_shortname
}

module "aws_ecs" {
  source                = "./modules/aws-ecs"
  name_prefix           = local.name_prefix
  region                = local.aws_region
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.private_subnet_ids
  ecs_security_group    = module.aws_vpc.ecs_security_group
  aws_secrets_manager   = local.aws_secrets_manager
  container_name        = "${local.name_prefix}Container"
  container_image       = "${module.ecr_docker_registry.ecr_image_url}:latest-dev"
  container_entrypoint  = "/home/jovyan/bin/bootstrap_ecs.sh"
  container_run_command = "python3 bin/run.py"

  # FARGATE: No always-on cost, no EC2 instances to manage, max 30GB RAM
  fargate_container_num_cores = local.ecs_fargate_container_num_cores
  fargate_container_ram_gb    = local.ecs_fargate_container_ram_gb

  # STANDARD EC2: Faster execution time, any instance type, must manage EC2 intances, 
  #               significant EC2 costs if not turned off
  ec2_instance_type       = local.ecs_ec2_instance_type
  ec2_container_num_cores = local.ecs_ec2_container_num_cores
  ec2_container_ram_gb    = local.ecs_ec2_container_ram_gb
  min_ec2_instances       = local.ecs_ec2_instances
  max_ec2_instances       = local.ecs_ec2_instances + 1
}

module "aws_tableau" {
  source                = "./modules/aws-tableau"
  name_prefix           = local.name_prefix
  region                = local.aws_region
  num_linux_instances   = local.tableau_linux_servers
  num_windows_instances = local.tableau_windows_servers
  ec2_instance_type     = local.tableau_instance_type
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.public_subnet_ids
  registration_file     = local.tableau_registration_file
  # aws_secrets_manager   = local.aws_secrets_manager
}
