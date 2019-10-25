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
  aws_account                 = data.aws_caller_identity.current.account_id
  project_shortname           = local.config["project_shortname"]
  aws_region                  = local.config["region"]
  aws_secret_name_prefix      = local.config["aws_secret_name_prefix"]
  prefer_fargate              = local.config["prefer_fargate"]
  fargate_container_ram_gb    = local.config["fargate_container_ram_gb"]
  fargate_container_num_cores = local.config["fargate_container_num_cores"]
  ec2_container_num_cores     = local.config["ec2_container_num_cores"]
  ec2_container_ram_gb        = local.config["ec2_container_ram_gb"]
  ec2_instance_type           = local.config["ec2_instance_type"]
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
  name_prefix = local.name_prefix
  source      = "./modules/aws-vpc"
}

module "ecr_docker_registry" {
  repository_name = "${local.name_prefix}Docker-Registry"
  image_name      = lower(local.project_shortname)
  source          = "./modules/aws-ecr"
}

module "aws_ecs" {
  name_prefix           = local.name_prefix
  source                = "./modules/aws-ecs"
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
  fargate_container_num_cores = local.fargate_container_num_cores
  fargate_container_ram_gb    = local.fargate_container_ram_gb

  # STANDARD EC2: Faster execution time, any instance type, must manage EC2 intances, 
  #               significant EC2 costs if not turned off
  ec2_instance_type       = local.ec2_instance_type
  ec2_container_num_cores = local.ec2_container_num_cores
  ec2_container_ram_gb    = local.ec2_container_ram_gb
  min_ec2_instances       = local.prefer_fargate ? 0 : 1
  max_ec2_instances       = 2
}
