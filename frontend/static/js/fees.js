(() => {
  const dialog = document.querySelector("[data-fee-dialog]");
  const form = document.querySelector("[data-fee-dialog-form]");
  if (!dialog || !form) return;

  const summary = dialog.querySelector("[data-fee-dialog-summary]");
  const closeButton = dialog.querySelector("[data-fee-dialog-cancel]");

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-fee-confirm]");
    if (!trigger) return;
    event.preventDefault();

    form.reset();
    form.action = trigger.dataset.action;
    form.elements.loan_id.value = trigger.dataset.loanId || "";
    form.elements.fee_type.value = trigger.dataset.feeType || "";
    form.elements.next.value = trigger.dataset.next || "";
    summary.textContent = `${trigger.dataset.member}: ${trigger.dataset.book} — ${trigger.dataset.feeLabel} — ${trigger.dataset.amount}`;
    dialog.showModal();
  });

  closeButton.addEventListener("click", () => dialog.close());
})();
