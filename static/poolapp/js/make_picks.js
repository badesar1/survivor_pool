document.addEventListener('DOMContentLoaded', function () {
  const makePicksForm = document.getElementById('make-picks-form');
  const contestantCards = makePicksForm.querySelectorAll('.contestant-card');
  const resetPicksButton = makePicksForm.querySelector('button[name="reset_picks"]');

  // ---------- card selection ----------
  function handleSelection(category, contestantId, selectedCard) {
    const hiddenInput = makePicksForm.querySelector(`input[name="${category}"]`);
    if (hiddenInput) hiddenInput.value = contestantId;

    const categoryCards = makePicksForm.querySelectorAll(`.contestant-card[data-category="${category}"]`);
    categoryCards.forEach(card => card.classList.remove('selected'));
    selectedCard.classList.add('selected');
  }

  contestantCards.forEach(card => {
    card.addEventListener('click', function () {
      const category = card.getAttribute('data-category');
      const contestantId = card.getAttribute('data-contestant-id');
      if (category && contestantId) handleSelection(category, contestantId, card);
    });
  });

  // ---------- idol toggle sync ----------
  const immunityCheckbox = makePicksForm.querySelector('#id_used_immunity_idol');
  if (immunityCheckbox) {
    immunityCheckbox.addEventListener('change', function () {
      const hiddenInput = makePicksForm.querySelector('input[name="used_immunity_idol"]');
      if (hiddenInput) hiddenInput.value = immunityCheckbox.checked ? 'on' : '';
    });
  }

  // ---------- reset picks ----------
  if (resetPicksButton) {
    resetPicksButton.addEventListener('click', function (e) {
      e.preventDefault();

      // Clear hidden inputs
      makePicksForm.querySelectorAll('input[type="hidden"]').forEach(input => {
        // leave CSRF alone; clear others
        if (input.name !== 'csrfmiddlewaretoken') input.value = '';
      });

      // Unselect cards
      makePicksForm.querySelectorAll('.contestant-card').forEach(card => card.classList.remove('selected'));

      // Reset idol toggle
      if (immunityCheckbox) {
        immunityCheckbox.checked = false;
        const hiddenImmunity = makePicksForm.querySelector('input[name="used_immunity_idol"]');
        if (hiddenImmunity) hiddenImmunity.value = '';
      }

      // Ensure wagers/parlay reset
      const voInput = document.getElementById('wager_vo_input');
      const imInput = document.getElementById('wager_im_input');
      const parlayToggle = document.getElementById('parlay_toggle');
      if (voInput) voInput.value = 0;
      if (imInput) imInput.value = 0;
      if (parlayToggle) parlayToggle.checked = false;
      normalizeRisk(); // sync hidden fields and meter

      // add hidden reset flag
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

      // submit
      setTimeout(() => makePicksForm.submit(), 0);
    });
  }

  // ---------- wagers & parlay ----------
  const weeklyCap = parseInt(makePicksForm.dataset.weeklyCap || "3", 10);
  const minFloor  = parseInt(makePicksForm.dataset.minFloor || "-3", 10);
  const currentPoints = parseInt(makePicksForm.dataset.currentPoints || "0", 10);

  const voInput = document.getElementById('wager_vo_input');
  const imInput = document.getElementById('wager_im_input');
  const parlayToggle = document.getElementById('parlay_toggle');

  // hidden Django fields
  const hidVO = document.getElementById('id_wager_voted_out');
  const hidIM = document.getElementById('id_wager_immunity');
  const hidParlay = document.getElementById('id_parlay');

  const riskUsedEl = document.getElementById('risk_used');

  function clamp(n, min, max){ return Math.max(min, Math.min(max, n)); }

  function normalizeRisk() {
    let vo = parseInt(voInput?.value || '0', 10); if (isNaN(vo)) vo = 0;
    let im = parseInt(imInput?.value || '0', 10); if (isNaN(im)) im = 0;

    // non-negative and per-field caps
    vo = clamp(vo, 0, weeklyCap);
    im = clamp(im, 0, weeklyCap);

    // sum ≤ weeklyCap
    if (vo + im > weeklyCap) {
      if (document.activeElement === imInput) {
        im = weeklyCap - vo;
      } else {
        vo = weeklyCap - im;
      }
    }

    // floor rule: currentPoints - (vo + im) ≥ minFloor
    const worst = currentPoints - (vo + im);
    if (worst < minFloor) {
      const allowed = Math.max(0, currentPoints - minFloor);
      if (document.activeElement === imInput) {
        im = clamp(allowed - vo, 0, weeklyCap - vo);
      } else {
        vo = clamp(allowed - im, 0, weeklyCap - im);
      }
    }

    // reflect values
    if (voInput) voInput.value = vo;
    if (imInput) imInput.value = im;
    if (riskUsedEl) riskUsedEl.textContent = String(vo + im);

    // sync hidden fields
    if (hidVO) hidVO.value = vo;
    if (hidIM) hidIM.value = im;
    if (hidParlay) hidParlay.checked = !!parlayToggle?.checked;
  }

  voInput?.addEventListener('input', normalizeRisk);
  imInput?.addEventListener('input', normalizeRisk);
  parlayToggle?.addEventListener('change', normalizeRisk);

  // initial sync
  normalizeRisk();
  makePicksForm.addEventListener('submit', normalizeRisk);
});