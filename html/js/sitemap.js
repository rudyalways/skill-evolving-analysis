/** Highlight comparison-table links on docs hub */
document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('last-refreshed');
  if (el) el.textContent = new Date().toLocaleString();
});
