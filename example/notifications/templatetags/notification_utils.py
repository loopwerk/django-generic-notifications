from django import template

register = template.Library()


@register.filter
def dict_get(dictionary, key):
    """Get a value from a dictionary by key."""
    return dictionary.get(key)
