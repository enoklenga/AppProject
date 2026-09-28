document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("task-form");

    if (!form) {
        return;
    }

    const projectSelect = document.getElementById("id_commessa");
    const phaseSelect = document.getElementById("id_fase");
    const assigneeSelect = document.getElementById("id_assegnato_a");

    if (!projectSelect || !phaseSelect || !assigneeSelect) {
        return;
    }

    const phasesEndpoint = form.dataset.phasesUrl;
    const assigneesEndpoint = form.dataset.assigneesUrl;


    function resetPhases() {
        phaseSelect.innerHTML =
            '<option value="">Seleziona una fase</option>';
    }


    function resetAssignees() {
        assigneeSelect.innerHTML =
            '<option value="">Seleziona un utente</option>';
    }


    async function loadPhases(projectId) {
        resetPhases();
        resetAssignees();

        if (!projectId) {
            phaseSelect.disabled = true;
            assigneeSelect.disabled = true;
            return;
        }

        phaseSelect.disabled = true;
        assigneeSelect.disabled = true;

        try {
            const params = new URLSearchParams({
                commessa: projectId,
            });

            const response = await fetch(
                `${phasesEndpoint}?${params.toString()}`,
                {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                }
            );

            if (!response.ok) {
                throw new Error("Errore caricamento fasi");
            }

            const data = await response.json();

            data.results.forEach((fase) => {
                const option = document.createElement("option");

                option.value = fase.id;
                option.textContent = fase.label;

                phaseSelect.appendChild(option);
            });

        } catch (error) {
            console.error(error);

        } finally {
            phaseSelect.disabled = false;
        }
    }


    async function loadAssignees(phaseId) {
        resetAssignees();

        if (!phaseId) {
            assigneeSelect.disabled = true;
            return;
        }

        assigneeSelect.disabled = true;

        try {
            const params = new URLSearchParams({
                fase: phaseId,
            });

            const response = await fetch(
                `${assigneesEndpoint}?${params.toString()}`,
                {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                }
            );

            if (!response.ok) {
                throw new Error("Errore caricamento assegnatari");
            }

            const data = await response.json();

            data.results.forEach((utente) => {
                const option = document.createElement("option");

                option.value = utente.id;
                option.textContent = utente.label;

                assigneeSelect.appendChild(option);
            });

        } catch (error) {
            console.error(error);

        } finally {
            assigneeSelect.disabled = false;
        }
    }


    projectSelect.addEventListener("change", () => {
        loadPhases(projectSelect.value);
    });


    phaseSelect.addEventListener("change", () => {
        loadAssignees(phaseSelect.value);
    });


    /*
     * Stato iniziale.
     * Non cancelliamo i valori se Django sta ripresentando
     * il form dopo un errore di validazione.
     */
    if (!projectSelect.value) {
        phaseSelect.disabled = true;
        assigneeSelect.disabled = true;
    } else if (!phaseSelect.value) {
        assigneeSelect.disabled = true;
    }
});