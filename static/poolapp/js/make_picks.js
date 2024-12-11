// poolapp/static/poolapp/js/make_picks.js

document.addEventListener('DOMContentLoaded', function () {
    const makePicksForm = document.getElementById('make-picks-form');
    const contestantCards = makePicksForm.querySelectorAll('.contestant-card');
    const resetPicksButton = makePicksForm.querySelector('button[name="reset_picks"]');
    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]');
    // if (csrfToken) {
    //     console.log("CSRF token found:", csrfToken.value);
    // } else {
    //     console.error("CSRF token missing from form!");
    // }

    // Function to handle selection
    function handleSelection(category, contestantId, selectedCard) {
        // Update the hidden input field
        const hiddenInput = makePicksForm.querySelector(`input[name="${category}"]`);
        if (hiddenInput) {
            hiddenInput.value = contestantId;
        }

        // Remove 'selected' class from all cards in this category
        const categoryCards = makePicksForm.querySelectorAll(`.contestant-card[data-category="${category}"]`);
        categoryCards.forEach(card => {
            card.classList.remove('selected');
        });

        // Add 'selected' class to the clicked card
        selectedCard.classList.add('selected');
    }

    // Add click event listeners to all contestant cards
    contestantCards.forEach(card => {
        card.addEventListener('click', function () {
            // Determine which category this card belongs to
            const category = card.getAttribute('data-category');
            const contestantId = card.getAttribute('data-contestant-id');

            if (category && contestantId) {
                handleSelection(category, contestantId, card);
            }
        });
    });

    // Handle Reset Picks Button
    if (resetPicksButton) {
        resetPicksButton.addEventListener('click', function (e) {
            e.preventDefault(); // Prevent form submission
            
            // Clear hidden inputs
            makePicksForm.querySelectorAll('input[type="hidden"]').forEach(input => {
                input.value = '';
            });
            // console.log("Submitting the form0...");

            // Remove 'selected' class from all cards
            makePicksForm.querySelectorAll('.contestant-card').forEach(card => {
                card.classList.remove('selected');
            });

            // Uncheck immunity idol checkbox if present
            const immunityCheckbox = makePicksForm.querySelector('#id_used_immunity_idol');
            if (immunityCheckbox) {
                immunityCheckbox.checked = false;
                const hiddenImmunityInput = makePicksForm.querySelector('input[name="used_immunity_idol"]');
                if (hiddenImmunityInput) {
                    hiddenImmunityInput.value = '';
                }
            }

            // Create or update hidden input for 'reset_picks'
            let resetInput = makePicksForm.querySelector('input[name="reset_picks"]');
            if (!resetInput) {
                resetInput = document.createElement('input');
                resetInput.type = 'hidden';
                resetInput.name = 'reset_picks';
                resetInput.value = 'on';
                makePicksForm.appendChild(resetInput);
            } else {
                resetInput.value = 'on';
            }

            // Ensure CSRF token is included
            const csrfTokenValue = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
            if (csrfTokenValue) {
                let csrfInput = makePicksForm.querySelector('input[name="csrfmiddlewaretoken"]');
                if (!csrfInput) {
                    csrfInput = document.createElement('input');
                    csrfInput.type = 'hidden';
                    csrfInput.name = 'csrfmiddlewaretoken';
                    csrfInput.value = csrfTokenValue;
                    makePicksForm.appendChild(csrfInput);
                } else {
                    csrfInput.value = csrfTokenValue;
                }
            } else {
                console.error("CSRF token missing! Aborting submission.");
                return;
            }

            // Debugging outputs
            console.log("CSRF token before submission:", csrfTokenValue);
            const formData = new FormData(makePicksForm);
            for (const [key, value] of formData.entries()) {
                console.log(`${key}: ${value}`);
            }

            // Submit the form
            setTimeout(() => makePicksForm.submit(), 0);
            
        });
    }

    // Handle "Use an Immunity Idol" Checkbox
    const immunityCheckbox = makePicksForm.querySelector('#id_used_immunity_idol');
    if (immunityCheckbox) {
        immunityCheckbox.addEventListener('change', function () {
            const hiddenInput = makePicksForm.querySelector('input[name="used_immunity_idol"]');
            if (hiddenInput) {
                hiddenInput.value = immunityCheckbox.checked ? 'on' : '';
            }
        });
    }
});