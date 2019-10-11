resource "aws_ecs_cluster" "myFargateCluster" {
  name = "${var.name_prefix}FargateCluster"
}

data "aws_iam_role" "ecs_task_execution_role" {
  # TODO: Codify this role as a resource
  name = "PTB-ECSWorkerRole"
}

resource "aws_ecs_service" "myFargateECSService" {
  for_each = var.tag_aliases

  name            = "${var.name_prefix}ECSServiceOnFargate"
  desired_count   = 0
  cluster         = aws_ecs_cluster.myFargateCluster.id
  task_definition = aws_ecs_task_definition.myFargateTask[each.key].arn
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = "${var.subnet_ids}"
    security_groups = ["${var.ecs_security_group}"]
  }

  #   load_balancer {
  #     target_group_arn = "${aws_alb_target_group.app.id}"
  #     container_name   = "app"
  #     container_port   = "${var.app_port}"
  #   }
  #   depends_on = [
  #     "aws_alb_listener.front_end",
  #   ]
}

resource "aws_cloudwatch_log_group" "myCWLogGroup" {
  name_prefix = "${var.name_prefix}AWSLogs"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecs_task_definition" "myFargateTask" {
  for_each = var.tag_aliases

  family                   = "${var.name_prefix}ECSTask-{each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.container_num_cores * 1024
  memory                   = var.container_ram_gb * 1024
  execution_role_arn       = data.aws_iam_role.ecs_task_execution_role.arn

  # task_role_arn           = "${aws_iam_role.github-role.arn}"
  container_definitions = <<DEFINITION
[
  {
    "name":         "${var.container_name}",
    "image":        "${var.container_image}:{each.value}",
    "cpu":          ${var.container_num_cores * 1024},
    "memory":       ${var.container_ram_gb * 1024},
    "entryPoint": [
      "${var.container_entrypoint}"
    ],
    "command": [
      "${var.container_run_command}"
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group":          "${aws_cloudwatch_log_group.myCWLogGroup.name}",
        "awslogs-region":         "${var.region}",
        "awslogs-stream-prefix":  "container-log"
      }
    },
    "networkMode":  "awsvpc",
    "portMappings": [
      {
        "containerPort": ${var.app_port},
        "hostPort":      ${var.app_port}
      }
    ],
    "environment": [
      {
        "name":  "AWS_DEFAULT_REGION",
        "value": "${var.region}"
      }

    ],
    "secrets": [
      {
        "name":      "AWS_ACCESS_KEY_ID",
        "valueFrom": "${var.aws_secrets_manager}/AWS_ACCESS_KEY_ID"
      },
      {
        "name":      "AWS_SECRET_ACCESS_KEY",
        "valueFrom": "${var.aws_secrets_manager}/AWS_SECRET_ACCESS_KEY"
      }
    ]
  }
]
DEFINITION
}

resource "aws_security_group" "ecs_tasks_sg" {
  name        = "${var.name_prefix}ECSSecurityGroup"
  description = "allow inbound access from the ALB only"
  vpc_id      = var.vpc_id
  ingress {
    protocol    = "tcp"
    from_port   = var.app_port
    to_port     = var.app_port
    cidr_blocks = ["0.0.0.0/0"]
    # security_groups = ["${aws_security_group.lb.id}"]
  }
  egress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}
