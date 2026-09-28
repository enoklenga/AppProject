from django import template

from apps.notifications.selectors import (
    recent_notifications_for_user,
    unread_notification_count,
)


register = template.Library()


@register.inclusion_tag(
    "notifications/_notification_bell.html"
)
def notification_bell(user):
    """
    Campanella globale nell'header.

    Mostra:
    - numero notifiche non lette;
    - ultime 6 notifiche.
    """

    if (
        not user
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
    ):
        return {
            "notifications": [],
            "unread_count": 0,
        }

    return {
        "notifications": (
            recent_notifications_for_user(
                user=user,
                limit=6,
            )
        ),
        "unread_count": (
            unread_notification_count(
                user=user
            )
        ),
    }