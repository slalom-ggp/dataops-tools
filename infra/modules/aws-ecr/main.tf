resource "aws_ecr_repository" "ecr_repo" {
  name = "${replace(lower(var.repository_name), "_", "-")}/${lower(var.image_name)}"

  tags = {
    tf = 1
  }

  lifecycle {
    prevent_destroy = true
  }
}
