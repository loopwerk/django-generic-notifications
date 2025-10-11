from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .channels import BaseChannel
    from .frequencies import BaseFrequency
    from .types import NotificationType


class NotificationRegistry:
    """
    Central registry for notification types, channels, and email frequencies.
    Allows apps to register their own notification types and delivery channels.
    """

    def __init__(self) -> None:
        self._type_classes: dict[str, Type["NotificationType"]] = {}
        self._channel_classes: dict[str, Type["BaseChannel"]] = {}
        self._frequency_classes: dict[str, Type["BaseFrequency"]] = {}
        self._registered_class_ids: set[int] = set()

    def _register(self, cls, base_class, registry_dict: dict, class_type_name: str, force: bool = False) -> None:
        """Generic registration method for all registry types"""
        class_id = id(cls)
        if class_id in self._registered_class_ids and not force:
            return  # Already registered this class

        try:
            if not issubclass(cls, base_class):
                raise ValueError(f"Must register a {class_type_name} subclass")
        except TypeError:
            raise ValueError(f"Must register a {class_type_name} subclass")

        if not hasattr(cls, "key") or not cls.key:
            raise ValueError(f"{class_type_name} class must have a key attribute")

        registry_dict[cls.key] = cls
        self._registered_class_ids.add(class_id)

    def register_type(self, notification_type_class: Type["NotificationType"], force: bool = False) -> None:
        """Register a notification type class"""
        from .types import NotificationType

        self._register(notification_type_class, NotificationType, self._type_classes, "NotificationType", force)

    def register_channel(self, channel_class: Type["BaseChannel"], force: bool = False) -> None:
        """Register a notification channel class"""
        from .channels import BaseChannel

        self._register(channel_class, BaseChannel, self._channel_classes, "BaseChannel", force)

    def register_frequency(self, frequency_class: Type["BaseFrequency"], force: bool = False) -> None:
        """Register a frequency option class"""
        from .frequencies import BaseFrequency

        self._register(frequency_class, BaseFrequency, self._frequency_classes, "BaseFrequency", force)

    def get_type(self, key: str) -> Type["NotificationType"]:
        """Get a registered notification type class by key"""
        return self._type_classes[key]

    def get_channel(self, key: str) -> Type["BaseChannel"]:
        """Get a registered channel class by key"""
        return self._channel_classes[key]

    def get_frequency(self, key: str) -> Type["BaseFrequency"]:
        """Get a registered frequency class by key"""
        return self._frequency_classes[key]

    def get_all_types(self) -> list[Type["NotificationType"]]:
        """Get all registered notification type classes"""
        return list(self._type_classes.values())

    def get_all_channels(self) -> list[Type["BaseChannel"]]:
        """Get all registered channel classes"""
        return list(self._channel_classes.values())

    def get_all_frequencies(self) -> list[Type["BaseFrequency"]]:
        """Get all registered frequency classes"""
        return list(self._frequency_classes.values())

    def get_realtime_frequencies(self) -> list[Type["BaseFrequency"]]:
        """Get all frequencies marked as realtime"""
        return [cls for cls in self._frequency_classes.values() if cls.is_realtime]

    def unregister_type(self, type_class: Type["NotificationType"]) -> bool:
        """
        Unregister a notification type by class.

        Args:
            type_class: The notification type class to remove

        Returns:
            bool: True if a type was removed, False if key didn't exist
        """
        return self._type_classes.pop(type_class.key, None) is not None

    def unregister_channel(self, channel_class: Type["BaseChannel"]) -> bool:
        """
        Unregister a channel by class.

        Args:
            channel_class: The channel class to remove

        Returns:
            bool: True if a channel was removed, False if key didn't exist
        """
        return self._channel_classes.pop(channel_class.key, None) is not None

    def unregister_frequency(self, frequency_class: Type["BaseFrequency"]) -> bool:
        """
        Unregister a frequency by class.

        Args:
            frequency_class: The frequency class to remove

        Returns:
            bool: True if a frequency was removed, False if key didn't exist
        """
        return self._frequency_classes.pop(frequency_class.key, None) is not None

    def clear_types(self) -> None:
        """Remove all registered notification types."""
        self._type_classes.clear()

    def clear_channels(self) -> None:
        """Remove all registered channels."""
        self._channel_classes.clear()

    def clear_frequencies(self) -> None:
        """Remove all registered frequencies."""
        self._frequency_classes.clear()


# Global registry instance
registry = NotificationRegistry()
