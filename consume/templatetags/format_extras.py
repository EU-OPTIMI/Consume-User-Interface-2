from django import template

register = template.Library()


@register.filter(name='clean_timestamp')
def clean_timestamp(value):
    """
    Trim ISO-8601 timestamps like 2025-11-10T11:45:10.065+0000
    down to 2025-11-10T11:45:10 for friendlier display.
    """
    if not value or not isinstance(value, str):
        return value
    if 'T' in value and len(value) >= 19:
        return value[:19]
    return value
