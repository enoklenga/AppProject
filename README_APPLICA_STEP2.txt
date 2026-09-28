NOKIHUB — BACKEND STEP 2

Prerequisito: applicare questo pacchetto sopra il progetto che ha gia superato lo Step 1.

1. Estrarre il contenuto nella root di lef-timesheetProject con sovrascrittura.
2. Non sono previste nuove migration di schema.
3. Eseguire:

   docker compose exec web python manage.py test tests.domain.test_backend_integrity_step2 tests.integration.test_password_enforcement --keepdb -v 2
   docker compose exec web python manage.py check
   docker compose exec web python manage.py makemigrations --check --dry-run
   docker compose exec web python manage.py test apps.documents.tests apps.notifications.tests apps.phases.tests apps.planning.tests apps.tasks.tests tests.api tests.domain tests.integration tests.operations tests.timesheets --keepdb -v 1

Nota: i failure UI/branding gia noti non fanno parte di questo Step 2.
