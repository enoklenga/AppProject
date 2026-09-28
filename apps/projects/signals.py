from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.phases.models import FaseCommessa

from .models import Commessa


@receiver(post_save, sender=Commessa)
def ensure_general_phase(sender, instance, created, **kwargs):
    """Ogni commessa dispone sempre di un Teamwork operativo minimo."""
    if created:
        FaseCommessa.objects.get_or_create(
            commessa=instance,
            nome="Generale",
            defaults={
                "sistema": True,
                "data_inizio": instance.data_inizio,
                "data_fine_prevista": instance.data_fine_prevista,
                "ordine": 0,
                "stato": FaseCommessa.Stato.DA_INIZIARE,
                "creata_da": None,
            },
        )
