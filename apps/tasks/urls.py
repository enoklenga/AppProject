from django.urls import path

from . import views


app_name = "tasks"


urlpatterns = [
    # =====================================================
    # LE MIE ATTIVITÀ
    # =====================================================

    path(
        "mie/",
        views.my_task_list,
        name="my-task-list",
    ),

    # =====================================================
    # GESTIONE ATTIVITÀ
    # =====================================================

    path(
        "",
        views.task_list,
        name="task-list",
    ),

    path(
        "nuova/",
        views.task_create,
        name="task-create",
    ),

    # =====================================================
    # ENDPOINT ASSEGNATARI
    # Deve stare prima del pattern <uuid:pk>
    # =====================================================
    path(
         "fasi/",
        views.project_phases,
        name="project-phases",
    ),
    
    path(
        "assegnatari-fase/",
        views.phase_assignees,
        name="phase-assignees",
    ),
    
    path(
        "assegnatari/",
        views.project_assignees,
        name="project-assignees",
    ),

    # =====================================================
    # DETTAGLIO
    # =====================================================

    path(
        "<uuid:pk>/",
        views.task_detail,
        name="task-detail",
    ),

    path(
        "<uuid:pk>/modifica/",
        views.task_update,
        name="task-update",
    ),

    path(
        "<uuid:pk>/stato/",
        views.task_status_update,
        name="task-status-update",
    ),

    path(
        "<uuid:pk>/commenti/nuovo/",
        views.task_comment_create,
        name="task-comment-create",
    ),

    path(
        "<uuid:pk>/elimina/",
        views.task_delete_view,
        name="task-delete",
    ),
   
]