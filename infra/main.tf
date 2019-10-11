terraform {
  backend "s3" {
    bucket = "propensity-to-buy"
    key    = "infra/dataops-pkg-state"
    region = "us-east-2"
  }
}

provider "aws" {
  region  = var.region
  version = "~> 2.10"
}

module "ecr_docker_registry" {
  repository_name = "${var.name_prefix}Docker-Registry"
  image_name      = "ptb"
  source          = "./modules/aws-ecr"
}

module "aws_vpc" {
  name_prefix = var.name_prefix
  source      = "./modules/aws-vpc"
}

module "aws_ecs_fargate" {
  # FARGATE: No always-on cost, no ECS instances to manage, max 30GB RAM
  name_prefix           = var.name_prefix
  source                = "./modules/aws-ecs-fargate"
  region                = var.region
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.private_subnet_ids
  ecs_security_group    = module.aws_vpc.ecs_security_group
  aws_secrets_manager   = var.aws_secrets_manager
  container_name        = "${var.name_prefix}Container"
  container_num_cores   = var.fargate_container_num_cores
  container_ram_gb      = var.fargate_container_ram_gb
  container_image       = "${module.ecr_docker_registry.ecr_image_url}:latest-dev"
  container_entrypoint  = "/home/jovyan/bin/bootstrap_ecs.sh"
  container_run_command = "python3 bin/run.py"
}

module "aws_ecs_standard" {
  # STANDARD: Faster execution time, can select any instance type, must manage
  name_prefix           = var.name_prefix
  source                = "./modules/aws-ecs-standard"
  region                = var.region
  vpc_id                = module.aws_vpc.vpc_id
  subnet_ids            = module.aws_vpc.private_subnet_ids
  ecs_security_group    = module.aws_vpc.ecs_security_group
  aws_secrets_manager   = var.aws_secrets_manager
  container_name        = "${var.name_prefix}Container"
  container_num_cores   = var.ec2_container_num_cores
  container_ram_gb      = var.ec2_container_ram_gb
  container_image       = "${module.ecr_docker_registry.ecr_image_url}:latest-dev"
  container_entrypoint  = "/home/jovyan/bin/bootstrap_ecs.sh"
  container_run_command = "python3 bin/run.py"
  min_ec2_instances     = var.prefer_fargate ? 0 : 1
  max_ec2_instances     = 2
  instance_type         = var.ec2_instance_type
}

# module "aws_eks" {
#   count      = 1
#   source     = "./modules/aws-eks"
#   subnet_ids = "${module.aws_vpc.private_subnet_ids}"
# }
