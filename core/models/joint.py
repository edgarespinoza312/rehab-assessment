from dataclasses import dataclass

from .joint_type import JointType

@dataclass
class Joint:
    """
    Represents a single anatomical joint.
    """

    name: JointType

    x: float
    y: float
    z: float = 0.0

    visibility: float = 1.0
    confidence: float = 1.0

    @property
    def position(self):
        """
        Returns the (x, y) coordinates.
        """
        return (self.x, self.y)

    @property
    def position_3d(self):
        """
        Returns the (x, y, z) coordinates.
        """
        return (self.x, self.y, self.z)