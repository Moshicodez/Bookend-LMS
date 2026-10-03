// Auto-dismiss flash messages after 4 seconds
document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.remove(), 4000);
});
