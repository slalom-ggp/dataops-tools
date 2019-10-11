data "aws_availability_zones" "myAZs" {}

resource "aws_ecs_cluster" "myECSStandardCluster" {
  name = "${var.name_prefix}StandardCluster"
}

resource "aws_ecs_cluster" "myFargateCluster" {
  name = "${var.name_prefix}FargateCluster"
  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_role" "ecs_task_execution_role" {
  # TODO: Codify this role as a resource
  name = "PTB-ECSWorkerRole"
}
resource "aws_iam_role" "ecs_instance_role" {
  name               = "${var.name_prefix}ECSStandard-InstanceRole"
  assume_role_policy = <<EOF
{
"Version": "2012-10-17",
"Statement": [
  {
    "Effect": "Allow",
    "Principal": {
      "Service": "ec2.amazonaws.com"
    },
    "Action": "sts:AssumeRole"
  }
]
}
EOF
}

resource "aws_iam_role_policy" "ecs_instance_role_policy" {
  name   = "ecs_instance_role_policy"
  role   = aws_iam_role.ecs_instance_role.id
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCluster",
        "ecs:DeregisterContainerInstance",
        "ecs:DiscoverPollEndpoint",
        "ecs:Poll",
        "ecs:RegisterContainerInstance",
        "ecs:StartTelemetrySession",
        "ecs:Submit*",
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecs:StartTask"
      ],
      "Resource": "*"
    }
  ]
}
EOF
}

resource "aws_iam_instance_profile" "ecs_iam_instance_profile" {
  name = "${var.name_prefix}ecs_iam_instance_profile"
  role = aws_iam_role.ecs_instance_role.name
}

resource "aws_launch_configuration" "myEcsInstanceLaunchConfig" {
  name_prefix                 = "${var.name_prefix}ECSStandardLaunchConfig"
  associate_public_ip_address = true
  ebs_optimized               = true
  enable_monitoring           = true
  instance_type               = var.instance_type
  image_id                    = var.image_id
  iam_instance_profile        = aws_iam_instance_profile.ecs_iam_instance_profile.id
  lifecycle {
    create_before_destroy = true
  }

  user_data = <<USER_DATA
#!/usr/bin/env bash
echo ECS_CLUSTER=${aws_ecs_cluster.myECSStandardCluster.name} >> /etc/ecs/ecs.config
USER_DATA
}

resource "aws_autoscaling_group" "myEcsAsg" {
  name                 = "${var.name_prefix}ECSASG"
  availability_zones   = slice(data.aws_availability_zones.myAZs.names, 0, 2)
  desired_capacity     = var.min_ec2_instances
  min_size             = var.min_ec2_instances
  max_size             = var.max_ec2_instances
  launch_configuration = aws_launch_configuration.myEcsInstanceLaunchConfig.id
}

resource "aws_ecs_service" "myECSService" {
  name            = "${var.name_prefix}ECSServiceOnEC2"
  desired_count   = 0
  cluster         = aws_ecs_cluster.myECSStandardCluster.id
  task_definition = aws_ecs_task_definition.myECSStandardTask.arn
  launch_type     = "EC2"

  # network_configuration {
  #   subnets         = "${var.subnet_ids}"
  #   security_groups = ["${var.ecs_security_group}"]
  # }

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

resource "aws_ecs_task_definition" "myECSStandardTask" {
  family                   = "${var.name_prefix}ECSStandardTask"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  cpu                      = var.container_num_cores * 1024
  memory                   = var.container_ram_gb * 1024
  execution_role_arn       = data.aws_iam_role.ecs_task_execution_role.arn

  # task_role_arn           = "${aws_iam_role.github-role.arn}"
  container_definitions = <<DEFINITION
[
  {
    "name":         "${var.name_prefix}Container",
    "image":        "${var.container_image}",
    "cpu":           ${var.container_num_cores * 1024},
    "memory":        ${var.container_ram_gb * 1024},
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
