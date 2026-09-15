"""Require explicit configuration from the launch parameter file."""

from rclpy.parameter import Parameter


def parameter(node, name, kind):
    """Declare a typed parameter without a hidden code default."""
    node.declare_parameter(name, kind)
    return node.get_parameter(name).value


def positive(node, name):
    value = parameter(node, name, Parameter.Type.DOUBLE)
    if value <= 0:
        raise ValueError(f'{name} must be positive')
    return value


def depth(node):
    value = parameter(node, 'qos_depth', Parameter.Type.INTEGER)
    if value <= 0:
        raise ValueError('qos_depth must be positive')
    return value
