// Temporary Hermes gather instrumentation helper.
// Replace __INGEST_PATH__, __TOKEN_HEADER__, __TOKEN__, and __INVESTIGATION__ before use.
// Keep this helper local to the investigation and remove it after the report is captured.

const gatherReport = {
  path: '__INGEST_PATH__',
  tokenHeader: '__TOKEN_HEADER__',
  token: '__TOKEN__',
  investigation: '__INVESTIGATION__',
};

function getGatherRoute() {
  return typeof window !== 'undefined' ? window.location.pathname : '';
}

function getGatherUrl() {
  return typeof window !== 'undefined' ? window.location.href : '';
}

export async function sendGatherEvent(label, data = {}, extras = {}) {
  if (!gatherReport.path || gatherReport.path.includes('__INGEST_PATH__')) {
    return;
  }
  try {
    await fetch(gatherReport.path, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        [gatherReport.tokenHeader]: gatherReport.token,
      },
      body: JSON.stringify({
        type: extras.type || 'log',
        level: extras.level || 'info',
        label,
        message: extras.message || '',
        route: extras.route || getGatherRoute(),
        url: extras.url || getGatherUrl(),
        data,
        meta: {
          source: 'temporary gather instrumentation',
          investigation: gatherReport.investigation,
          ...(extras.meta || {}),
        },
      }),
    });
  } catch (error) {
    // Avoid breaking the reproduced flow if the report endpoint is unavailable.
    console.warn('sendGatherEvent failed', error);
  }
}

export function makeGatherChangeLogger() {
  let lastSignature = '';
  return function sendWhenChanged(label, data, signature = JSON.stringify(data), extras = {}) {
    if (signature === lastSignature) {
      return;
    }
    lastSignature = signature;
    void sendGatherEvent(label, data, extras);
  };
}
