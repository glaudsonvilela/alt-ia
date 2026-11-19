document.documentElement.dataset.altAgentExtension = 'true';

let lastActive;
function reportAgentState() {
  const active = document.documentElement.dataset.altAgentActive === 'true';
  if (active === lastActive) return;
  lastActive = active;
  chrome.runtime.sendMessage({ type: 'agent-state', active }).catch(() => {});
}

new MutationObserver(reportAgentState).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ['data-alt-agent-active'],
});
reportAgentState();
window.addEventListener('pagehide', () => {
  chrome.runtime.sendMessage({ type: 'agent-state', active: false }).catch(() => {});
});
