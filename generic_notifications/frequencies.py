from abc import ABC
from typing import Type

from .registry import registry


class BaseFrequency(ABC):
    """
    Represents a frequency option for notifications.
    """

    key: str
    name: str
    is_realtime: bool
    description: str

    def __str__(self) -> str:
        return self.name


def register(cls: Type[BaseFrequency]) -> Type[BaseFrequency]:
    """
    Decorator that registers a NotificationFrequency subclass.

    Usage:
        @register
        class WeeklyFrequency(NotificationFrequency):
            key = "weekly"
            name = "Weekly digest"
            is_realtime = False
            description = "Bundle notifications into a weekly email"
    """
    # Register the class
    registry.register_frequency(cls)

    # Return the class unchanged
    return cls


@register
class RealtimeFrequency(BaseFrequency):
    key = "realtime"
    name = "Real-time"
    is_realtime = True
    description = "Send immediately when notifications are created"


@register
class DailyFrequency(BaseFrequency):
    key = "daily"
    name = "Daily digest"
    is_realtime = False
    description = "Bundle notifications into a daily digest"
