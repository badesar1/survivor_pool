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

  function calculateOutcomes(vo, im, isParlay) {
    // Base points
    const baseSafe = 1;
    const baseVO = 3;
    const baseIm = 2;
    const baseTotal = baseSafe + baseVO + baseIm; // 6

    // Wager calculations
    const voWagerWin = 2 * vo;
    const voWagerLoss = -vo;
    const imWagerWin = Math.floor(1.5 * im);
    const imWagerLoss = -im;

    // Parlay bonus
    const parlayBonus = 20;

    if (isParlay) {
      // Parlay: all-or-nothing
      const best = baseTotal + parlayBonus + voWagerWin + imWagerWin;
      const worst = baseSafe + voWagerLoss + imWagerLoss; // Safe still counts, but VO+Imm = 0
      
      // Build breakdowns
      let bestParts = [`Safe +1`, `VO +3`, `Imm +2`, `Parlay +${parlayBonus}`];
      if (voWagerWin + imWagerWin > 0) {
        bestParts.push(`Wagers +${voWagerWin + imWagerWin}`);
      }
      
      let worstParts = [`Safe +1`];
      const totalWagerLoss = voWagerLoss + imWagerLoss;
      if (totalWagerLoss < 0) {
        worstParts.push(`Wagers ${totalWagerLoss}`);
      }
      
      return {
        best: best,
        worst: worst,
        bestBreakdown: bestParts.join(', '),
        worstBreakdown: worstParts.join(', ')
      };
    } else {
      // No parlay: normal scoring
      const best = baseTotal + voWagerWin + imWagerWin;
      const worst = voWagerLoss + imWagerLoss; // All wrong, no safe pick points
      
      // Build breakdowns
      let bestParts = [`Safe +1`, `VO +3`, `Imm +2`];
      if (voWagerWin + imWagerWin > 0) {
        bestParts.push(`Wagers +${voWagerWin + imWagerWin}`);
      }
      
      let worstBreakdown;
      if (vo === 0 && im === 0) {
        worstBreakdown = 'No wagers';
      } else {
        worstBreakdown = `Wager losses: ${voWagerLoss + imWagerLoss}`;
      }
      
      return {
        best: best,
        worst: worst,
        bestBreakdown: bestParts.join(', '),
        worstBreakdown: worstBreakdown
      };
    }
  }

  function updateOutcomesDisplay() {
    let vo = parseInt(voInput?.value || '0', 10); if (isNaN(vo)) vo = 0;
    let im = parseInt(imInput?.value || '0', 10); if (isNaN(im)) im = 0;
    const isParlay = parlayToggle?.checked || false;

    // Calculate with current parlay setting
    const outcomes = calculateOutcomes(vo, im, isParlay);

    // Update display - always show sign for clarity
    document.getElementById('best_case').textContent = outcomes.best >= 0 ? `+${outcomes.best}` : `${outcomes.best}`;
    document.getElementById('worst_case').textContent = outcomes.worst >= 0 ? `+${outcomes.worst}` : `${outcomes.worst}`;
    document.getElementById('best_case_breakdown').textContent = outcomes.bestBreakdown;
    document.getElementById('worst_case_breakdown').textContent = outcomes.worstBreakdown;
  }

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

    // Update outcomes calculator
    updateOutcomesDisplay();
  }

  voInput?.addEventListener('input', normalizeRisk);
  imInput?.addEventListener('input', normalizeRisk);
  parlayToggle?.addEventListener('change', normalizeRisk);

  // initial sync
  normalizeRisk();
  makePicksForm.addEventListener('submit', normalizeRisk);
});