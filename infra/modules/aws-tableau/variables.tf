variable "name_prefix" {}
variable "region" { description = "AWS region" }
variable "ec2_instance_type" { type = "string" }
variable "ec2_instance_storage_gb" { default = 100 }
variable "num_linux_instances" { default = 1 }
variable "num_windows_instances" { default = 0 }
variable "registration_file" { default = "secrets/registration.json" }
variable "vpc_id" { type = "string" }
variable "subnet_ids" { type = "list" }

# variable "aws_secrets_manager" { default = "" }
