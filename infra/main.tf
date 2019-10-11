terraform {
  backend "s3" {
    bucket = "propensity-to-buy"
    key    = "infra/dataops-pkg-state"
    region = "us-east-2"
  }
}

data "local_file" "config_yml" {
  filename = "config.yml"
}

data "aws_caller_identity" "current" {}

output "account_id" {
  value = "${data.aws_caller_identity.current.account_id}"
}

locals {
  config = yamldecode(data.local_file.config_yml.content)
}

locals {
  aws_region                  = local.config["region"]
  aws_account                 = data.aws_caller_identity.current.account_id
  name_prefix                 = local.config["name_prefix"]
  prefer_fargate              = local.config["prefer_fargate"]
  aws_secret_name_prefix      = local.config["aws_secret_name_prefix"]
  fargate_container_ram_gb    = local.config["fargate_container_ram_gb"]
  fargate_container_num_cores = local.config["fargate_container_num_cores"]
  ec2_container_num_cores     = local.config["ec2_container_num_cores"]
  ec2_container_ram_gb        = local.config["ec2_container_ram_gb"]
  ec2_instance_type           = local.config["ec2_instance_type"]
}

locals {
  aws_secrets_manager = "arn:aws:secretsmanager:${local.aws_region}:${local.aws_account}:secret:${local.aws_secret_name_prefix}"
}

provider "aws" {
  region  = local.aws_region
  version = "~> 2.10"
}

module "ecr_docker_registry" {
  repository_name = "${local.name_prefix}Docker-Registry"
  image_name      = "ptb"
  source          = "./modules/aws-ecr"
}

module "aws_vpc" {
  name_prefix = local.name_prefix
  source      = "./modules/aws-vpc"
}

module "aws_ecs_fargate" {
  # FARGATE: No always-on cost, no ECS instances to manage, max 30GB RAM
  name_prefix           = local.name_prefix
  source                = "./modules/aws-ecs-fargate"
  region                = local.aws_region
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.private_subnet_ids
  ecs_security_group    = module.aws_vpc.ecs_security_group
  aws_secrets_manager   = local.aws_secrets_manager
  container_name        = "${local.name_prefix}Container"
  container_num_cores   = local.fargate_container_num_cores
  container_ram_gb      = local.fargate_container_ram_gb
  container_image       = "${module.ecr_docker_registry.ecr_image_url}:latest-dev"
  container_entrypoint  = "/home/jovyan/bin/bootstrap_ecs.sh"
  container_run_command = "python3 bin/run.py"
}

module "aws_ecs_standard" {
  # STANDARD: Faster execution time, can select any instance type, must manage
  name_prefix           = local.name_prefix
  source                = "./modules/aws-ecs-standard"
  region                = local.aws_region
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.private_subnet_ids
  ecs_security_group    = module.aws_vpc.ecs_security_group
  aws_secrets_manager   = local.aws_secrets_manager
  container_name        = "${local.name_prefix}Container"
  container_num_cores   = local.ec2_container_num_cores
  container_ram_gb      = local.ec2_container_ram_gb
  container_image       = "${module.ecr_docker_registry.ecr_image_url}:latest-dev"
  container_entrypoint  = "/home/jovyan/bin/bootstrap_ecs.sh"
  container_run_command = "python3 bin/run.py"
  min_ec2_instances     = local.prefer_fargate ? 0 : 1
  max_ec2_instances     = 2
  instance_type         = local.ec2_instance_type
}

# module "aws_eks" {
#   count      = 1
#   source     = "./modules/aws-eks"
#   subnet_ids = "${module.aws_vpc.private_subnet_ids}"
# }
