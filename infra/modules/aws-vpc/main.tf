data "aws_availability_zones" "myAZs" {}

# Elastic IP:

resource "aws_eip" "myIP" {
  tags = {
    tf   = 1
    Name = "${var.name_prefix}IP"
  }
}

# VPC:

resource "aws_vpc" "myVPC" {
  tags = {
    tf   = 1
    Name = "${var.name_prefix}VPC"
  }

  cidr_block = "10.0.0.0/16"
}

# Public and Private Subnets:

resource "aws_subnet" "myPublicSubnets" {
  count = 2

  tags = {
    tf = 1

    Name = "${var.name_prefix}PublicSubnet-${count.index}"
  }

  availability_zone       = "${data.aws_availability_zones.myAZs.names[count.index]}"
  cidr_block              = "10.0.${count.index + 2}.0/24"
  vpc_id                  = "${aws_vpc.myVPC.id}"
  map_public_ip_on_launch = true
}

resource "aws_subnet" "myPrivateSubnets" {
  count = 2

  tags = {
    tf   = 1
    Name = "${var.name_prefix}PrivateSubnet-${count.index}"
  }

  availability_zone = "${data.aws_availability_zones.myAZs.names[count.index]}"
  cidr_block        = "10.0.${count.index}.0/24"
  vpc_id            = "${aws_vpc.myVPC.id}"
}

# Gateways:

resource "aws_internet_gateway" "myIGW" {
  vpc_id = "${aws_vpc.myVPC.id}"

  tags = {
    tf   = 1
    Name = "${var.name_prefix}IGW"
  }
}

resource "aws_nat_gateway" "myNATGateway" {
  allocation_id = "${aws_eip.myIP.id}"
  subnet_id     = "${aws_subnet.myPublicSubnets.0.id}"

  tags = {
    tf   = 1
    Name = "${var.name_prefix}NAT"
  }
}

# Public Routing Tables:

resource "aws_route_table" "myPublicRT" {
  vpc_id = "${aws_vpc.myVPC.id}"

  tags = {
    tf   = 1
    Name = "${var.name_prefix}PublicRT"
  }
}

resource "aws_route_table_association" "myPublicRTAssoc" {
  count          = 2
  route_table_id = "${aws_route_table.myPublicRT.id}"
  subnet_id      = "${aws_subnet.myPublicSubnets.*.id[count.index]}"
}

resource "aws_route" "myIGWRoute" {
  route_table_id         = "${aws_route_table.myPublicRT.id}"
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = "${aws_internet_gateway.myIGW.id}"
}

# Private Routing Tables:

resource "aws_route_table" "myPrivateRT" {
  vpc_id = "${aws_vpc.myVPC.id}"

  tags = {
    tf   = 1
    Name = "${var.name_prefix}PrivateRT"
  }
}

resource "aws_route_table_association" "myPrivateRTAssoc" {
  count          = 2
  route_table_id = "${aws_route_table.myPrivateRT.id}"
  subnet_id      = "${aws_subnet.myPrivateSubnets.*.id[count.index]}"
}

resource "aws_route" "myNATRoute" {
  route_table_id         = "${aws_route_table.myPrivateRT.id}"
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = "${aws_nat_gateway.myNATGateway.id}"
}

resource "aws_security_group" "ecs_tasks_sg" {
  name        = "${var.name_prefix}SecurityGroupForECS"
  description = "allow inbound access from the ALB only"
  vpc_id      = "${aws_vpc.myVPC.id}"

  dynamic "ingress" {
    for_each = var.app_ports

    content {
      protocol    = "tcp"
      from_port   = "${ingress.value}"
      to_port     = "${ingress.value}"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}
