output "ecs_cluster_name" {
  value = "${aws_ecs_cluster.myFargateCluster.name}"
}

output "ecs_task_names" {
  value = "${aws_ecs_task_definition.myFargateTask.*.family}"
}

output "ecs_container_name" {
  value = "${var.container_name}"
}

output "ecs_logging_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#logEventViewer:group=${aws_cloudwatch_log_group.myCWLogGroup.name}"
}

output "ecs_runtask_cli" {
  value = "aws ecs run-task --task-definition ${aws_ecs_task_definition.myFargateTask[0].family} --cluster ${aws_ecs_cluster.myFargateCluster.name} --launch-type FARGATE --region ${var.region} --network-configuration 'awsvpcConfiguration={subnets=[${element(var.subnet_ids, 0)}],securityGroups=[${var.ecs_security_group}],assignPublicIp=ENABLED}'"
}
