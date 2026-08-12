from backend.services.avatar.base import AvatarAdapter
from backend.services.avatar.huggingface_space import (
    HuggingFaceSpaceAvatarAdapter,
    HuggingFaceSpaceError,
)

__all__ = ["AvatarAdapter", "HuggingFaceSpaceAvatarAdapter", "HuggingFaceSpaceError"]
