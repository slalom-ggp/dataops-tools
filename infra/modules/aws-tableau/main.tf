data "aws_ami" "ubuntu" {
  owners      = ["099720109477"] # Canonical
  most_recent = true
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-18.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ami" "windows" {
  owners      = ["amazon"]
  most_recent = true
  # platform    = "Windows"
  filter {
    name   = "name"
    values = ["Windows_Server-2016-English-Full-Base-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

locals {
  project_shortname = substr(var.name_prefix, 0, length(var.name_prefix) - 1)
}

resource "aws_security_group" "ec2_sg_allow_ssh" {
  name        = "${var.name_prefix}SecurityGroupForSSH"
  description = "allow SSH traffic (port 22)"
  vpc_id      = var.vpc_id
  tags        = { project = local.project_shortname }
  ingress {
    protocol    = "tcp"
    from_port   = "22"
    to_port     = "22"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "ec2_sg_allow_outbound" {
  name        = "${var.name_prefix}SecurityGroupForOutbound"
  description = "allow all outbound traffic"
  vpc_id      = var.vpc_id
  tags        = { project = local.project_shortname }
  egress {
    protocol    = "tcp"
    from_port   = "0"
    to_port     = "65535"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "ec2_sg_allow_rdp" {
  name        = "${var.name_prefix}SecurityGroupForRDP"
  description = "allow SSH traffic (port 3389)"
  vpc_id      = var.vpc_id
  tags        = { project = local.project_shortname }
  ingress {
    protocol    = "tcp"
    from_port   = "3389"
    to_port     = "3389"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "ec2_sg_tableau_server" {
  # https://help.tableau.com/current/server/en-us/ports.htm
  name        = "${var.name_prefix}SecurityGroupForTableauServer"
  description = "open ports used by Tableau Server"
  vpc_id      = var.vpc_id
  tags        = { project = local.project_shortname }
  ingress {
    description = "HTTP/HTTPS"
    protocol    = "tcp"
    from_port   = "80"
    to_port     = "80"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSL"
    protocol    = "tcp"
    from_port   = "443"
    to_port     = "443"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Tableau Services Manager (TSM)"
    protocol    = "tcp"
    from_port   = "8850"
    to_port     = "8850"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "PostgreSQL Database"
    protocol    = "tcp"
    from_port   = "8060"
    to_port     = "8061"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Tableau License Verification Service"
    protocol    = "tcp"
    from_port   = "27000"
    to_port     = "27009"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Tableau dynamic process mapping"
    protocol    = "tcp"
    from_port   = "8000"
    to_port     = "9000"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

locals {
  ssh_key_dir = pathexpand("~/.ssh")
}
locals {
  ssh_public_key_filepath  = "${local.ssh_key_dir}/${lower(var.name_prefix)}prod-ec2keypair.pub"
  ssh_private_key_filepath = "${local.ssh_key_dir}/${lower(var.name_prefix)}prod-ec2keypair.pem"
}
locals {
  chocolatey_install_win = <<EOF
@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
EOF
  registration_install_cmd_win = (
    substr(var.registration_file, 0, 4) == "http" ?
    "curl \"${var.registration_file}\" > " :
    "echo ${base64encode(file(var.registration_file))} > tmp9.b64 && certutil -decode tmp9.b64 "
  )
  registration_install_cmd_lin = (
    substr(var.registration_file, 0, 4) == "http" ?
    "curl ${var.registration_file} > " :
    "echo ${base64encode(file(var.registration_file))} | base64 --decode > "
  )
}

data "template_file" "userdata_lin" {
  template = <<EOF
#!/bin/bash
mkdir -p /home/ubuntu/tableau
cd /home/ubuntu/tableau
sudo chmod 777 /home/ubuntu/tableau
touch /home/ubuntu/tableau/_INIT_STARTED_
export PROJECT=${local.project_shortname}
${local.registration_install_cmd_lin} registration.json
echo ${base64encode(file("${path.module}/tableau_setup.sh"))} | base64 --decode > tableau_setup.sh
echo ${base64encode(file("${path.module}/userdata_lin.sh"))} | base64 --decode > userdata.sh
${file("${path.module}/userdata_lin.sh")}
touch /home/ubuntu/tableau/_INIT_COMPLETE_
sudo chmod 777 /home/ubuntu/tableau/*
EOF
}
data "template_file" "userdata_win" {
  template = <<EOF
<script>
${local.chocolatey_install_win}
choco install -y curl
mkdir C:\Users\Administrator\tableau 2> NUL
cd C:\Users\Administrator\tableau
echo "" > ___BOOSTSTRAP_STARTED_
${local.registration_install_cmd_win} "C:\Users\Administrator\tableau\registration.json"
echo ${base64encode(file("${path.module}/defaultapps_win.xml"))} > tmp1.b64 && certutil -decode tmp1.b64 defaultapps.xml
dism.exe /online /import-defaultappassociations:defaultapps.xml
echo ${base64encode(file("${path.module}/tableau_setup.bat"))} > tmp2.b64 && certutil -decode tmp2.b64 tableau_setup.bat
echo "" > __BOOTSTRAP_COMPLETE_
echo "" > C:\Users\Administrator\tableau\__USERDATA_SCRIPT_STARTED_
${file("${path.module}/userdata_win.bat")}
echo "" > C:\Users\Administrator\tableau\_USERDATA_SCRIPT_COMPLETE_
</script>
<persist>true</persist>
EOF
}
resource "aws_key_pair" "mykey" {
  key_name   = "${var.name_prefix}ec2-keypair"
  public_key = file(local.ssh_public_key_filepath)
}

resource "aws_instance" "linux_tableau_server" {
  count                   = var.num_linux_instances
  ami                     = "${data.aws_ami.ubuntu.id}"
  instance_type           = var.ec2_instance_type
  key_name                = aws_key_pair.mykey.key_name
  ebs_optimized           = true
  monitoring              = true
  subnet_id               = var.subnet_ids[0]
  user_data               = data.template_file.userdata_lin.rendered
  disable_api_termination = false
  tags = {
    name    = "${var.name_prefix}TableauServer-Linux"
    project = local.project_shortname
  }
  vpc_security_group_ids = [
    aws_security_group.ec2_sg_allow_ssh.id,
    aws_security_group.ec2_sg_allow_outbound.id,
    aws_security_group.ec2_sg_tableau_server.id
  ]
  root_block_device {
    volume_type = "gp2"
    volume_size = var.ec2_instance_storage_gb
    encrypted   = true
  }
  lifecycle {
    create_before_destroy = true
    ignore_changes        = [tags]
  }
}
resource "aws_instance" "windows_tableau_server" {
  count                   = var.num_windows_instances
  ami                     = "${data.aws_ami.windows.id}"
  instance_type           = var.ec2_instance_type
  key_name                = aws_key_pair.mykey.key_name
  get_password_data       = true
  ebs_optimized           = true
  monitoring              = true
  subnet_id               = var.subnet_ids[0]
  user_data               = data.template_file.userdata_win.rendered
  disable_api_termination = false
  tags = {
    name    = "${var.name_prefix}TableauServer-Windows"
    project = local.project_shortname
  }
  vpc_security_group_ids = [
    aws_security_group.ec2_sg_allow_rdp.id,
    aws_security_group.ec2_sg_allow_outbound.id,
    aws_security_group.ec2_sg_tableau_server.id
  ]
  root_block_device {
    volume_type = "gp2"
    volume_size = var.ec2_instance_storage_gb
    encrypted   = true
  }
  lifecycle {
    create_before_destroy = true
    ignore_changes        = [tags]
  }
}
