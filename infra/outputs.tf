output "aws_region" { value = local.aws_region }
output "docker_repo_image_url" { value = module.ecr_docker_registry.ecr_image_url }
output "ecs_logging_url" { value = module.aws_ecs.ecs_logging_url }
output "ecs_cluster_name" { value = module.aws_ecs.ecs_cluster_name }
output "tableau_server_linux_urls" {
  value = "https://${module.aws_tableau.ec2_linux_public_ip}:8850 / https://${module.aws_tableau.ec2_linux_public_ip}"
}
output "tableau_server_linux_ssh_command" {
  value = "ssh -o StrictHostKeyChecking=no -i \"${module.aws_tableau.ssh_private_key_path}\" ubuntu@${module.aws_tableau.ec2_linux_public_ip}"
}
output "tableau_server_windows_account" {
  value = "Administrator:${module.aws_tableau.ec2_windows_instance_password}"
}
output "tableau_server_windows_rdp_command" {
  value = "cmdkey /generic:TERMSRV/${module.aws_tableau.ec2_windows_public_ip} /user:Administrator /pass:\"${module.aws_tableau.ec2_windows_instance_password}\" && mstsc /v:${module.aws_tableau.ec2_windows_public_ip} /w:1100 /h:900"
}
output "tableau_server_windows_urls" {
  value = "https://${module.aws_tableau.ec2_windows_public_ip}:8850 / https://${module.aws_tableau.ec2_windows_public_ip}"
}

# output "temp" {
#   value = module.aws_tableau.temp
# }
/*
output "estimated_aws_costs" {
  value = 1 == 1 ? "n/a" : <<COST_ESTIMATE_TEXT

=== PRICING ESTIMATES ===

AWS Kubernetes (Per Cluster): (https://aws.amazon.com/eks/pricing/)
  hourly:         $ 0.20
  weekly (24x7):  $33.00
  weekly (10x5):  $10.00

AWS ECS (Per Cluster):        (https://aws.amazon.com/ecs/pricing/)
  [no cost]       $ 0.00

AWS EC2 Instances:            (https://aws.amazon.com/ec2/pricing/)
  [varies]        $ ?.??

NAT Gateway (optional):       (https://aws.amazon.com/vpc/pricing/)
  hourly:         $ 0.045
  weekly:         $ 7.56

VPC and Security:
  [no cost]       $ 0.00

Other Resources:
  [not estimated]

COST_ESTIMATE_TEXT
}
*/

/*
output "account_id" { value = "${data.aws_caller_identity.current.account_id}" }
output "vpc_private_subnets" { value = module.aws_vpc.private_subnet_ids }
output "vpc_public_subnets" { value = module.aws_vpc.public_subnet_ids }
output "ecs_runtask_cli" {
  value = local.ecs_prefer_fargate ? module.aws_ecs.ecs_fargate_runtask_cli : module.aws_ecs.ecs_standard_runtask_cli
}
output "ecs_container_name" { value = module.aws_ecs.ecs_container_name }
output "ecs_security_group" { value = module.aws_vpc.ecs_security_group }
output "ecs_task_names" {
  value = local.ecs_prefer_fargate ? module.aws_ecs.ecs_fargate_task_name : module.aws_ecs.ecs_standard_task_name
}
output "docker_repo_root" { value = module.ecr_docker_registry.ecr_repo_root }
output "tableau_server_windows_password" {
  value = module.aws_tableau.ec2_windows_instance_password
}
*/
