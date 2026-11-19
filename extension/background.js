const companionUrl = 'https://ai.bigbanana.io/agent-companion.html';
let queue = Promise.resolve();

function serial(task) {
  queue = queue.then(task).catch(() => {});
}

async function closeCompanion() {
  const { companionWindowId } = await chrome.storage.session.get('companionWindowId');
  if (companionWindowId) {
    await chrome.windows.remove(companionWindowId).catch(() => {});
    await chrome.storage.session.remove('companionWindowId');
  }
}

async function reconcile() {
  const { agentTabId, companionWindowId } = await chrome.storage.session.get(['agentTabId', 'companionWindowId']);
  if (!agentTabId) return closeCompanion();
  const agentTab = await chrome.tabs.get(agentTabId).catch(() => null);
  if (!agentTab?.url?.startsWith('https://ai.bigbanana.io/')) {
    await chrome.storage.session.remove('agentTabId');
    return closeCompanion();
  }
  const browserWindow = await chrome.windows.getLastFocused({ windowTypes: ['normal'] }).catch(() => null);
  if (!browserWindow) return;
  const [activeTab] = await chrome.tabs.query({ active: true, windowId: browserWindow.id });
  if (activeTab?.id === agentTabId) return closeCompanion();
  if (companionWindowId) {
    const existing = await chrome.windows.get(companionWindowId).catch(() => null);
    if (existing) return;
    await chrome.storage.session.remove('companionWindowId');
  }
  const width = 400;
  const height = 390;
  const popup = await chrome.windows.create({
    url: companionUrl,
    type: 'popup',
    focused: true,
    width,
    height,
    left: Math.max(0, browserWindow.left + browserWindow.width - width - 16),
    top: Math.max(0, browserWindow.top + browserWindow.height - height - 36),
  });
  if (popup?.id) await chrome.storage.session.set({ companionWindowId: popup.id });
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'agent-state' || !sender.tab?.id || sender.tab.url?.includes('/agent-companion.html')) return;
  serial(async () => {
    const { agentTabId } = await chrome.storage.session.get('agentTabId');
    if (message.active) await chrome.storage.session.set({ agentTabId: sender.tab.id });
    else if (agentTabId === sender.tab.id) await chrome.storage.session.remove('agentTabId');
    await reconcile();
  });
});

chrome.tabs.onActivated.addListener(({ windowId }) => {
  serial(async () => {
    const { companionWindowId } = await chrome.storage.session.get('companionWindowId');
    if (windowId !== companionWindowId) await reconcile();
  });
});
chrome.windows.onFocusChanged.addListener(() => {
  serial(reconcile);
});
chrome.tabs.onRemoved.addListener((tabId) => {
  serial(async () => {
    const { agentTabId } = await chrome.storage.session.get('agentTabId');
    if (tabId === agentTabId) {
      await chrome.storage.session.remove('agentTabId');
      await closeCompanion();
    }
  });
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (!changeInfo.url || changeInfo.url.startsWith('https://ai.bigbanana.io/')) return;
  serial(async () => {
    const { agentTabId } = await chrome.storage.session.get('agentTabId');
    if (tabId === agentTabId) {
      await chrome.storage.session.remove('agentTabId');
      await closeCompanion();
    }
  });
});
chrome.windows.onRemoved.addListener((windowId) => {
  serial(async () => {
    const { companionWindowId } = await chrome.storage.session.get('companionWindowId');
    if (windowId === companionWindowId) await chrome.storage.session.remove('companionWindowId');
  });
});
