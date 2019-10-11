output "vpc_id" {
  value = "${aws_vpc.myVPC.id}"
}

output "private_subnet_ids" {
  value = "${aws_subnet.myPrivateSubnets.*.id}"

  # type  = "list"
}

output "public_subnet_ids" {
  value = "${aws_subnet.myPublicSubnets.*.id}"

  # type  = "list"
}

output "ecs_security_group" {
  value = "${aws_security_group.ecs_tasks_sg.id}"
}
