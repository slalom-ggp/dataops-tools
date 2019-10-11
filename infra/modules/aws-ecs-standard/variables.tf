variable "region" {
  description = "AWS region to launch servers."
}

variable "name_prefix" {}

variable "instance_type" {}

variable "image_id" {
  default = "ami-0e7c12c1bedd6bf21" # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-optimized_AMI.html
}

variable "min_ec2_instances" {
  default = 1
}
variable "max_ec2_instances" {
  default = 3
}

variable "container_name" {
  default = "DefaultContainer"
}

variable "container_image" {
}

variable "container_ram_gb" {
  default = "8"
}

variable "container_num_cores" {
  description = "The number of vCPUs. e.g. 0.25, 0.5, 1, 2, 4"
  default     = "4"
}

variable "container_entrypoint" {
  default = "python"
}

variable "container_run_command" {
  default = "bin/run.py"
}

variable "app_port" {
  default = "8080"
}

variable "subnet_ids" {
  type = "list"
}

variable "vpc_id" {
  type = "string"
}

variable "ecs_security_group" {
  type = "string"
}

variable "aws_secrets_manager" {
  type = "string"
}
