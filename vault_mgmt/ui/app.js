const toast = document.getElementById('toast');

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.remove('hidden');
  toast.style.borderColor = isError ? '#f08e8e' : '#2a3550';
  setTimeout(() => toast.classList.add('hidden'), 2600);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Request failed');
  }

  return response.json();
}

function renderOverview(state) {
  document.getElementById('agent-state-pill').textContent = `${state.telemetry.state} · ${state.mode}`;
  document.getElementById('mission').textContent = state.mission;
  document.getElementById('guidance-input').value = state.guidance_notes;
  document.getElementById('mode-select').value = state.mode;
  document.getElementById('posture-select').value = state.posture;
  document.getElementById('max-position').value = state.policies.max_position_size_usd;
  document.getElementById('max-daily-loss').value = state.policies.max_daily_loss_usd;
  document.getElementById('confidence-threshold').value = state.policies.confidence_threshold;
  document.getElementById('allow-market-orders').checked = state.policies.allow_market_orders;
  document.getElementById('require-approval').checked = state.policies.require_human_approval;

  const stats = [
    ['Agent', state.telemetry.agent_id],
    ['Strategy', state.telemetry.strategy_name],
    ['P&L USD', state.telemetry.pnl_usd.toFixed(2)],
    ['Exposure USD', state.telemetry.exposure_usd.toFixed(2)],
    ['Open Positions', String(state.telemetry.open_positions)],
    ['Posture', state.posture],
  ];

  document.getElementById('overview-stats').innerHTML = stats
    .map(([label, value]) => `
      <div class="stat">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
      </div>
    `)
    .join('');

  document.getElementById('guidance-actions').innerHTML = state.recommended_actions
    .map(
      (action) => `
        <div class="action">
          <div class="action-header">
            <strong>${action.title}</strong>
            <span class="badge">${action.state}</span>
          </div>
          <p class="muted">${action.rationale}</p>
          <div class="action-buttons">
            <button onclick="setGuidanceAction('${action.id}', 'accepted')">Accept</button>
            <button onclick="setGuidanceAction('${action.id}', 'rejected')">Reject</button>
            <button onclick="setGuidanceAction('${action.id}', 'deferred')">Defer</button>
          </div>
        </div>
      `
    )
    .join('');

  document.getElementById('audit-log').innerHTML = state.audit_log
    .map(
      (entry) => `
        <div class="audit-item">
          <strong>${entry.event}</strong>
          <p>${entry.detail}</p>
          <div class="muted">${new Date(entry.at).toLocaleString()} · ${entry.actor}</div>
        </div>
      `
    )
    .join('');
}

async function refresh() {
  const state = await request('/api/manager');
  renderOverview(state);
}

async function setGuidanceAction(actionId, state) {
  try {
    const updated = await request('/api/manager/guidance/action', {
      method: 'POST',
      body: JSON.stringify({ action_id: actionId, state }),
    });
    renderOverview(updated);
    showToast(`Guidance action set to ${state}`);
  } catch (error) {
    showToast(error.message, true);
  }
}

window.setGuidanceAction = setGuidanceAction;

document.getElementById('save-guidance').addEventListener('click', async () => {
  try {
    const updated = await request('/api/manager/guidance', {
      method: 'POST',
      body: JSON.stringify({ notes: document.getElementById('guidance-input').value }),
    });
    renderOverview(updated);
    showToast('Guidance saved');
  } catch (error) {
    showToast(error.message, true);
  }
});

document.getElementById('save-mode').addEventListener('click', async () => {
  try {
    const updated = await request('/api/manager/mode', {
      method: 'POST',
      body: JSON.stringify({ mode: document.getElementById('mode-select').value }),
    });
    renderOverview(updated);
    showToast('Mode updated');
  } catch (error) {
    showToast(error.message, true);
  }
});

document.getElementById('save-posture').addEventListener('click', async () => {
  try {
    const updated = await request('/api/manager/posture', {
      method: 'POST',
      body: JSON.stringify({ posture: document.getElementById('posture-select').value }),
    });
    renderOverview(updated);
    showToast('Posture updated');
  } catch (error) {
    showToast(error.message, true);
  }
});

document.getElementById('save-policies').addEventListener('click', async () => {
  try {
    const updated = await request('/api/manager/policies', {
      method: 'POST',
      body: JSON.stringify({
        max_position_size_usd: Number(document.getElementById('max-position').value),
        max_daily_loss_usd: Number(document.getElementById('max-daily-loss').value),
        confidence_threshold: Number(document.getElementById('confidence-threshold').value),
        allow_market_orders: document.getElementById('allow-market-orders').checked,
        require_human_approval: document.getElementById('require-approval').checked,
      }),
    });
    renderOverview(updated);
    showToast('Policies updated');
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelectorAll('[data-intervention]').forEach((button) => {
  button.addEventListener('click', async () => {
    try {
      const updated = await request('/api/manager/intervention', {
        method: 'POST',
        body: JSON.stringify({ action: button.dataset.intervention }),
      });
      renderOverview(updated);
      showToast(`Intervention applied: ${button.dataset.intervention}`);
    } catch (error) {
      showToast(error.message, true);
    }
  });
});

refresh().catch((error) => showToast(error.message, true));
