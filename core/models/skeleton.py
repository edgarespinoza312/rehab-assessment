from dataclasses import dataclass, field
from typing import Dict

from .joint_type import JointType
from .joint import Joint


@dataclass
class Skeleton:
    """
    Represents an entire body pose.
    """

    joints: Dict[JointType, Joint] = field(default_factory=dict)

    timestamp: float = 0.0

    frame_number: int = 0

    def add_joint(self, joint: Joint):
        """
        Adds or replaces a joint.
        """
        self.joints[joint.name] = joint

    def get_joint(self, joint_type: JointType):
        """
        Returns a joint by type.
        """
        return self.joints.get(joint_type)
    
    def has_joint(self, joint_type: JointType) -> bool:
        """
        Returns True if the requested joint exists.
        """
        return joint_type in self.joints
    
    def joint_count(self) -> int:
        """
        Returns the number of tracked joints.
        """
        return len(self.joints)

    def clear(self):
        """
        Removes all joints.
        """
        self.joints.clear()
        