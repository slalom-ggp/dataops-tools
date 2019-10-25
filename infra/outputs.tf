output "aws_region" { value = local.aws_region }
output "account_id" { value = "${data.aws_caller_identity.current.account_id}" }
output "docker_repo_root" { value = module.ecr_docker_registry.ecr_repo_root }
output "docker_repo_image_url" { value = module.ecr_docker_registry.ecr_image_url }
output "ecs_runtask_cli" {
  value = local.prefer_fargate ? module.aws_ecs.ecs_fargate_runtask_cli : module.aws_ecs.ecs_standard_runtask_cli
}
output "ecs_logging_url" { value = module.aws_ecs.ecs_logging_url }
output "ecs_cluster_name" { value = module.aws_ecs.ecs_cluster_name }
output "ecs_task_names" {
  value = local.prefer_fargate ? module.aws_ecs.ecs_fargate_task_name : module.aws_ecs.ecs_standard_task_name
}
output "ecs_container_name" { value = module.aws_ecs.ecs_container_name }
output "ecs_security_group" { value = module.aws_vpc.ecs_security_group }
output "vpc_private_subnets" { value = module.aws_vpc.private_subnet_ids }
output "vpc_public_subnets" { value = module.aws_vpc.public_subnet_ids }

# output "kubeconfig" {
#   value = "${module.aws_eks.kubeconfig}"
# }

output "estimated_cost_per_hour" {
  value = <<COST_ESTIMATE_TEXT

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
