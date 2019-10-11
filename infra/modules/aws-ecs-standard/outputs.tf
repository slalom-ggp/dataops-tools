output "ecs_cluster_name" {
  value = "${aws_ecs_cluster.myECSStandardCluster.name}"
}

output "ecs_task_name" {
  value = "${aws_ecs_task_definition.myECSStandardTask.family}"
}

output "ecs_container_name" {
  value = "${var.container_name}"
}

output "ecs_logging_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#logEventViewer:group=${aws_cloudwatch_log_group.myCWLogGroup.name}"
}

output "ecs_runtask_cli" {
  value = "aws ecs run-task --task-definition ${aws_ecs_task_definition.myECSStandardTask.family} --cluster ${aws_ecs_cluster.myECSStandardCluster.name} --launch-type EC2 --region ${var.region}"
}
