data "local_file" "config_yml" { filename = "../config.yml" }

locals { config = yamldecode(data.local_file.config_yml.content) }
locals {
  #   aws_account            = data.aws_caller_identity.current.account_id
  project_shortname      = local.config["project_shortname"]
  aws_region             = local.config["region"]
  aws_secret_name_prefix = local.config["aws_secret_name_prefix"]
}
locals {
  #   aws_secrets_manager = "arn:aws:secretsmanager:${local.aws_region}:${local.aws_account}:secret:${local.aws_secret_name_prefix}"
  name_prefix = "${local.project_shortname}-"
}

provider "aws" {
  region  = local.aws_region
  version = "~> 2.10"
}

module "ssh_key_pair" {
  source                = "git::https://github.com/cloudposse/terraform-aws-key-pair.git?ref=master"
  namespace             = "${local.project_shortname}"
  stage                 = "prod"
  name                  = "ec2_keypair"
  ssh_public_key_path   = "${path.module}/secrets"
  private_key_extension = ".pem"
  public_key_extension  = ".pub"
  generate_ssh_key      = true
  chmod_command = ( # chmod only on linux (ignore on windows)
    substr(pathexpand("~"), 1, 1) == "/" ? "chmod 600 %v" : ""
  )
}

resource "local_file" "ssh_installed_private_key_path" {
  filename   = "${pathexpand("~/.ssh")}/${basename(module.ssh_key_pair.private_key_filename)}"
  content    = fileexists(module.ssh_key_pair.private_key_filename) ? file(module.ssh_key_pair.private_key_filename) : "n/a"
  depends_on = [module.ssh_key_pair]
}
resource "local_file" "ssh_installed_public_key_path" {
  filename   = "${pathexpand("~/.ssh")}/${basename(module.ssh_key_pair.public_key_filename)}"
  content    = fileexists(module.ssh_key_pair.public_key_filename) ? file(module.ssh_key_pair.public_key_filename) : "n/a"
  depends_on = [module.ssh_key_pair]
}

resource "aws_iam_user" "automation_user" {
  name = "${local.project_shortname}-automation-user"
  tags = {
    project = local.project_shortname
  }
}
resource "aws_iam_access_key" "automation_user_key" {
  user = "${aws_iam_user.automation_user.name}"
}
resource "aws_iam_user_policy" "automation_user_permissions" {
  name   = "${local.project_shortname}-automation-user-access"
  user   = "${aws_iam_user.automation_user.name}"
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "ec2:Describe*"
      ],
      "Effect": "Allow",
      "Resource": "*"
    }
  ]
}
EOF
}
resource "random_id" "suffix" {
  byte_length = 2
}
resource "aws_s3_bucket" "s3_metadata_bucket" {
  bucket = "${lower(local.project_shortname)}-project-metadata-${random_id.suffix.hex}"
  acl    = "private"
  tags   = { project = local.project_shortname }
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}
resource "aws_s3_bucket_public_access_block" "s3_metadata_bucket_block" {
  bucket              = aws_s3_bucket.s3_metadata_bucket.id
  block_public_acls   = true
  block_public_policy = true
}
