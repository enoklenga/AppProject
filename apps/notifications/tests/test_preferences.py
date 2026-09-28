def test_comment_notification_disabled(self):

    self.user.notification_preferences.task_commented = False

    self.user.notification_preferences.save()

    notify_task_commented(
        comment=self.comment
    )

    self.assertFalse(
        Notification.objects.filter(
            destinatario=self.user,
            tipo=(
                Notification.Tipo
                .TASK_COMMENTED
            ),
        ).exists()
    )