(function () {
  if (window.__ctPlayProxyRunContextPatched) {
    return;
  }
  window.__ctPlayProxyRunContextPatched = true;

  var RUN_QUERY_PARAM = '__ct_play_run';
  var INSPECT_AUTH_QUERY_PARAM = '__ct_inspect_auth';
  var INSPECT_TARGET_QUERY_PARAM = '__ct_inspect_target';
  var INSPECT_OVERLAY_QUERY_PARAM = '__ct_input_overlay';
  var INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM = '__ct_input_key';
  var INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM = '__ct_input_payload';
  var PLAY_FRESHNESS_INDICATOR_ID = 'ct-play-freshness-indicator';
  var DEBUG_LOGIN_STRATEGY = 'debug-login';
  var DIRECT_PROXY_PREFIX = '/play-proxy/';
  var PROJECT_PROXY_PREFIX = '/play-project/';
  var ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+.-]*:/;
  var debugLoginRetryHandle = 0;
  var debugLoginAttempts = 0;
  var debugLoginCompleted = false;
  var inspectTargetApplied = false;

  function getRunContextLoaderAttribute(attributeName) {
    if (!document || typeof document.getElementById !== 'function') {
      return '';
    }
    var loader = document.getElementById('ct-play-proxy-run-context-loader');
    if (!loader || typeof loader.getAttribute !== 'function') {
      return '';
    }
    var value = loader.getAttribute(attributeName);
    return typeof value === 'string' ? value.trim() : '';
  }

  function getInjectedRunId() {
    return getRunContextLoaderAttribute('data-ct-play-run');
  }

  function getInjectedProjectId() {
    return getRunContextLoaderAttribute('data-ct-play-project');
  }

  function getInjectedPipelineId() {
    return getRunContextLoaderAttribute('data-ct-play-pipeline');
  }

  function getInjectedPlayStatus() {
    return getRunContextLoaderAttribute('data-ct-play-status');
  }

  function getInjectedPlayReadyAt() {
    return getRunContextLoaderAttribute('data-ct-play-ready-at');
  }

  function getInjectedPlayUpdatedAt() {
    return getRunContextLoaderAttribute('data-ct-play-updated-at');
  }

  function getInjectedRunCreatedAt() {
    return getRunContextLoaderAttribute('data-ct-play-run-created-at');
  }

  function usesStableCompatibilityUrls() {
    return getRunContextLoaderAttribute('data-ct-play-url-mode') === 'stable-compatibility';
  }

  function summarizeFreshnessIdentifier(value) {
    var normalized = String(value || '').trim();
    if (!normalized) {
      return '';
    }
    return normalized.length > 16
      ? normalized.slice(0, 12)
      : normalized;
  }

  function formatFreshnessTimestamp(value) {
    var normalized = String(value || '').trim();
    if (!normalized) {
      return '';
    }
    var parsed = new Date(normalized);
    if (!parsed || !isFinite(parsed.getTime())) {
      return '';
    }
    return parsed.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC');
  }

  function readPlayFreshnessMetadata() {
    return {
      projectId: getInjectedProjectId(),
      pipelineId: getInjectedPipelineId(),
      runId: getInjectedRunId() || getRunId(),
      status: getInjectedPlayStatus(),
      readyAt: getInjectedPlayReadyAt(),
      updatedAt: getInjectedPlayUpdatedAt(),
      runCreatedAt: getInjectedRunCreatedAt()
    };
  }

  function createFreshnessIndicatorLine(text, emphasis) {
    if (!document || typeof document.createElement !== 'function') {
      return null;
    }
    var line = document.createElement('div');
    line.textContent = text;
    if (line.style) {
      line.style.fontWeight = emphasis ? '600' : '400';
      line.style.opacity = emphasis ? '1' : '0.92';
      line.style.whiteSpace = 'nowrap';
    }
    return line;
  }

  function ensurePlayFreshnessIndicator() {
    if (!document || typeof document.getElementById !== 'function' || typeof document.createElement !== 'function') {
      return;
    }
    if (!document.body || typeof document.body.appendChild !== 'function') {
      if (window && typeof window.setTimeout === 'function') {
        window.setTimeout(ensurePlayFreshnessIndicator, 0);
      }
      return;
    }
    var metadata = readPlayFreshnessMetadata();
    if (!metadata.runId && !metadata.pipelineId && !metadata.updatedAt && !metadata.runCreatedAt) {
      return;
    }

    var indicator = document.getElementById(PLAY_FRESHNESS_INDICATOR_ID);
    if (indicator) {
      return;
    }
    indicator = document.createElement('div');
    indicator.id = PLAY_FRESHNESS_INDICATOR_ID;
    indicator.setAttribute('aria-label', 'Play freshness indicator');
    if (indicator.style) {
      indicator.style.position = 'fixed';
      indicator.style.top = '12px';
      indicator.style.right = '12px';
      indicator.style.zIndex = '2147483647';
      indicator.style.pointerEvents = 'none';
      indicator.style.background = 'rgba(15, 23, 42, 0.88)';
      indicator.style.color = '#f8fafc';
      indicator.style.border = '1px solid rgba(148, 163, 184, 0.45)';
      indicator.style.borderRadius = '14px';
      indicator.style.boxShadow = '0 14px 40px rgba(15, 23, 42, 0.28)';
      indicator.style.padding = '10px 12px';
      indicator.style.font = '12px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      indicator.style.display = 'flex';
      indicator.style.flexDirection = 'column';
      indicator.style.gap = '2px';
      indicator.style.maxWidth = 'calc(100vw - 24px)';
      indicator.style.textAlign = 'right';
    }

    var titleLine = createFreshnessIndicatorLine('Live Play', true);
    if (titleLine) {
      indicator.appendChild(titleLine);
    }
    if (metadata.projectId) {
      var projectLine = createFreshnessIndicatorLine('Project ' + metadata.projectId, false);
      if (projectLine) {
        indicator.appendChild(projectLine);
      }
    }
    var buildRunParts = [];
    if (metadata.pipelineId) {
      buildRunParts.push('Build ' + summarizeFreshnessIdentifier(metadata.pipelineId));
    }
    if (metadata.runId) {
      buildRunParts.push('Session ' + summarizeFreshnessIdentifier(metadata.runId));
    }
    if (buildRunParts.length > 0) {
      var identityLine = createFreshnessIndicatorLine(buildRunParts.join(' | '), false);
      if (identityLine) {
        indicator.appendChild(identityLine);
      }
    }
    var freshnessValue = metadata.readyAt || metadata.updatedAt || metadata.runCreatedAt;
    var freshnessLabel = metadata.readyAt ? 'Ready ' : (metadata.updatedAt ? 'Updated ' : 'Started ');
    var formattedFreshness = formatFreshnessTimestamp(freshnessValue);
    if (formattedFreshness) {
      var freshnessLine = createFreshnessIndicatorLine(freshnessLabel + formattedFreshness, false);
      if (freshnessLine) {
        indicator.appendChild(freshnessLine);
      }
    }
    if (metadata.status) {
      var normalizedStatus = String(metadata.status).replace(/[_-]+/g, ' ').trim();
      if (normalizedStatus) {
        var statusLine = createFreshnessIndicatorLine('Status ' + normalizedStatus, false);
        if (statusLine) {
          indicator.appendChild(statusLine);
        }
      }
    }

    indicator.title = [
      metadata.projectId ? 'Project: ' + metadata.projectId : '',
      metadata.pipelineId ? 'Build: ' + metadata.pipelineId : '',
      metadata.runId ? 'Session: ' + metadata.runId : '',
      formattedFreshness ? freshnessLabel.trim() + ': ' + formattedFreshness : '',
      metadata.status ? 'Status: ' + String(metadata.status) : ''
    ].filter(Boolean).join('\n');
    document.body.appendChild(indicator);
  }

  function parseCurrentDirectProxyLocation() {
    try {
      var parsed = new URL(window.location.href);
      if (!parsed.pathname.startsWith(DIRECT_PROXY_PREFIX)) {
        return null;
      }
      var withoutPrefix = parsed.pathname.slice(DIRECT_PROXY_PREFIX.length);
      var slashIndex = withoutPrefix.indexOf('/');
      var runId = slashIndex >= 0 ? withoutPrefix.slice(0, slashIndex) : withoutPrefix;
      if (!runId) {
        return null;
      }
      var targetPath = slashIndex >= 0 ? withoutPrefix.slice(slashIndex) : '/';
      if (!targetPath || targetPath.charAt(0) !== '/') {
        targetPath = '/' + (targetPath || '');
      }
      return {
        runId: runId,
        targetPath: targetPath,
        search: parsed.search || '',
        hash: parsed.hash || ''
      };
    } catch (error) {
      return null;
    }
  }

  function parseCurrentProjectProxyLocation() {
    try {
      var parsed = new URL(window.location.href);
      if (!parsed.pathname.startsWith(PROJECT_PROXY_PREFIX)) {
        return null;
      }
      var withoutPrefix = parsed.pathname.slice(PROJECT_PROXY_PREFIX.length);
      var slashIndex = withoutPrefix.indexOf('/');
      var projectId = slashIndex >= 0 ? withoutPrefix.slice(0, slashIndex) : withoutPrefix;
      if (!projectId) {
        return null;
      }
      var targetPath = slashIndex >= 0 ? withoutPrefix.slice(slashIndex) : '/';
      if (!targetPath || targetPath.charAt(0) !== '/') {
        targetPath = '/' + (targetPath || '');
      }
      return {
        projectId: decodeURIComponent(projectId),
        targetPath: targetPath,
        search: parsed.search || '',
        hash: parsed.hash || ''
      };
    } catch (error) {
      return null;
    }
  }

  function buildProjectProxyBasePath(projectId) {
    if (!projectId) {
      return PROJECT_PROXY_PREFIX.slice(0, -1);
    }
    return PROJECT_PROXY_PREFIX + encodeURIComponent(String(projectId || ''));
  }

  function buildDirectProxyBasePath(runId) {
    if (!runId) {
      return DIRECT_PROXY_PREFIX.slice(0, -1);
    }
    return DIRECT_PROXY_PREFIX + encodeURIComponent(String(runId || ''));
  }

  function buildCompatibilityUrl(targetPath, search, hash, runId) {
    if (usesStableCompatibilityUrls()) {
      return '' + (targetPath || '/') + (search || '') + (hash || '');
    }
    if (!runId) {
      return '' + (targetPath || '/') + (search || '') + (hash || '');
    }
    try {
      var parsed = new URL(String(targetPath || '/') + (search || '') + (hash || ''), window.location.origin);
      parsed.searchParams.set(RUN_QUERY_PARAM, runId);
      return '' + (parsed.pathname || '/') + (parsed.search || '') + (parsed.hash || '');
    } catch (error) {
      return '' + (targetPath || '/') + (search || '') + (hash || '');
    }
  }

  function getRunId() {
    try {
      var parsed = new URL(window.location.href);
      var value = parsed.searchParams.get(RUN_QUERY_PARAM);
      if (typeof value === 'string' && value.trim()) {
        return value.trim();
      }
      var directLocation = parseCurrentDirectProxyLocation();
      if (directLocation) {
        return directLocation.runId;
      }
      return getInjectedRunId();
    } catch (error) {
      return getInjectedRunId();
    }
  }

  function getInspectAuthStrategy() {
    try {
      var parsed = new URL(window.location.href);
      var value = parsed.searchParams.get(INSPECT_AUTH_QUERY_PARAM);
      return typeof value === 'string' ? value.trim().toLowerCase() : '';
    } catch (error) {
      return '';
    }
  }

  function getInspectTarget() {
    try {
      var parsed = new URL(window.location.href);
      var value = parsed.searchParams.get(INSPECT_TARGET_QUERY_PARAM);
      return typeof value === 'string' ? value.trim() : '';
    } catch (error) {
      return '';
    }
  }

  function readCurrentPreservedInspectContext() {
    try {
      var parsed = new URL(window.location.href);
      var authStrategy = parsed.searchParams.get(INSPECT_AUTH_QUERY_PARAM);
      var target = parsed.searchParams.get(INSPECT_TARGET_QUERY_PARAM);
      return {
        authStrategy: typeof authStrategy === 'string' ? authStrategy.trim() : '',
        target: typeof target === 'string' ? target.trim() : ''
      };
    } catch (error) {
      return {
        authStrategy: '',
        target: ''
      };
    }
  }

  function readCurrentPreservedOverlayContext() {
    try {
      var parsed = new URL(window.location.href);
      var enabledRaw = parsed.searchParams.get(INSPECT_OVERLAY_QUERY_PARAM);
      var payload = parsed.searchParams.get(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM);
      var storageKey = parsed.searchParams.get(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM);
      var enabled = typeof enabledRaw === 'string' ? enabledRaw.trim().toLowerCase() : '';
      var normalizedPayload = typeof payload === 'string' ? payload.trim() : '';
      var overlayRequested = Boolean(
        normalizedPayload
        && (!enabled || enabled === '1' || enabled === 'true')
      );
      return {
        overlayRequested: overlayRequested,
        payload: overlayRequested ? normalizedPayload : '',
        storageKey: overlayRequested && typeof storageKey === 'string'
          ? storageKey.trim()
          : ''
      };
    } catch (error) {
      return {
        overlayRequested: false,
        payload: '',
        storageKey: ''
      };
    }
  }

  function formatLikeInput(parsed, input) {
    if (input instanceof URL) {
      return parsed;
    }
    var raw = String(input || '');
    if (!raw) {
      return raw;
    }
    if (raw.startsWith('//') || ABSOLUTE_URL_PATTERN.test(raw)) {
      return parsed.toString();
    }
    return '' + (parsed.pathname || '/') + (parsed.search || '') + (parsed.hash || '');
  }

  function preserveRunIdInUrl(input, runId, options) {
    if (!runId) {
      return input;
    }
    if (typeof input !== 'string' && !(input instanceof URL)) {
      return input;
    }

    try {
      var parsed = input instanceof URL
        ? new URL(input.toString())
        : new URL(String(input || ''), window.location.href);
      if (parsed.origin !== window.location.origin) {
        return input;
      }
      parsed.searchParams.set(RUN_QUERY_PARAM, runId);
      if (options && options.includeInspectContext) {
        var context = readCurrentPreservedInspectContext();
        if (context.authStrategy) {
          parsed.searchParams.set(INSPECT_AUTH_QUERY_PARAM, context.authStrategy);
        }
        if (context.target) {
          parsed.searchParams.set(INSPECT_TARGET_QUERY_PARAM, context.target);
        }
      }
      if (options && options.includeOverlayContext) {
        var overlayContext = readCurrentPreservedOverlayContext();
        if (overlayContext.overlayRequested && overlayContext.payload) {
          parsed.searchParams.set(INSPECT_OVERLAY_QUERY_PARAM, '1');
          parsed.searchParams.set(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM, overlayContext.payload);
          if (overlayContext.storageKey) {
            parsed.searchParams.set(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM, overlayContext.storageKey);
          }
        }
      }
      return formatLikeInput(parsed, input);
    } catch (error) {
      return input;
    }
  }

  function preserveCompatibilityContextInUrl(input, options) {
    if (typeof input !== 'string' && !(input instanceof URL)) {
      return input;
    }

    try {
      var parsed = input instanceof URL
        ? new URL(input.toString())
        : new URL(String(input || ''), window.location.href);
      if (parsed.origin !== window.location.origin) {
        return input;
      }
      if (options && options.includeInspectContext) {
        var context = readCurrentPreservedInspectContext();
        if (context.authStrategy) {
          parsed.searchParams.set(INSPECT_AUTH_QUERY_PARAM, context.authStrategy);
        }
        if (context.target) {
          parsed.searchParams.set(INSPECT_TARGET_QUERY_PARAM, context.target);
        }
      }
      if (options && options.includeOverlayContext) {
        var overlayContext = readCurrentPreservedOverlayContext();
        if (overlayContext.overlayRequested && overlayContext.payload) {
          parsed.searchParams.set(INSPECT_OVERLAY_QUERY_PARAM, '1');
          parsed.searchParams.set(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM, overlayContext.payload);
          if (overlayContext.storageKey) {
            parsed.searchParams.set(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM, overlayContext.storageKey);
          }
        }
      }
      return formatLikeInput(parsed, input);
    } catch (error) {
      return input;
    }
  }

  function preserveProjectIdInUrl(input, projectId, options) {
    if (!projectId) {
      return input;
    }
    if (typeof input !== 'string' && !(input instanceof URL)) {
      return input;
    }

    try {
      var parsed = input instanceof URL
        ? new URL(input.toString())
        : new URL(String(input || ''), window.location.href);
      if (parsed.origin !== window.location.origin) {
        return input;
      }
      var basePath = buildProjectProxyBasePath(projectId);
      if (!(parsed.pathname === basePath || parsed.pathname.indexOf(basePath + '/') === 0)) {
        parsed.pathname = basePath + (parsed.pathname || '/');
      }
      if (options && options.includeInspectContext) {
        var context = readCurrentPreservedInspectContext();
        if (context.authStrategy) {
          parsed.searchParams.set(INSPECT_AUTH_QUERY_PARAM, context.authStrategy);
        }
        if (context.target) {
          parsed.searchParams.set(INSPECT_TARGET_QUERY_PARAM, context.target);
        }
      }
      if (options && options.includeOverlayContext) {
        var overlayContext = readCurrentPreservedOverlayContext();
        if (overlayContext.overlayRequested && overlayContext.payload) {
          parsed.searchParams.set(INSPECT_OVERLAY_QUERY_PARAM, '1');
          parsed.searchParams.set(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM, overlayContext.payload);
          if (overlayContext.storageKey) {
            parsed.searchParams.set(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM, overlayContext.storageKey);
          }
        }
      }
      return formatLikeInput(parsed, input);
    } catch (error) {
      return input;
    }
  }

  function preserveRunIdViaDirectProxyInUrl(input, runId, options) {
    if (!runId) {
      return input;
    }
    if (typeof input !== 'string' && !(input instanceof URL)) {
      return input;
    }

    try {
      var parsed = input instanceof URL
        ? new URL(input.toString())
        : new URL(String(input || ''), window.location.href);
      if (parsed.origin !== window.location.origin) {
        return input;
      }
      if (
        parsed.pathname.indexOf(DIRECT_PROXY_PREFIX) !== 0
        && parsed.pathname.indexOf(PROJECT_PROXY_PREFIX) !== 0
      ) {
        var basePath = buildDirectProxyBasePath(runId);
        if (!(parsed.pathname === basePath || parsed.pathname.indexOf(basePath + '/') === 0)) {
          parsed.pathname = basePath + (parsed.pathname || '/');
        }
      }
      if (options && options.includeInspectContext) {
        var context = readCurrentPreservedInspectContext();
        if (context.authStrategy) {
          parsed.searchParams.set(INSPECT_AUTH_QUERY_PARAM, context.authStrategy);
        }
        if (context.target) {
          parsed.searchParams.set(INSPECT_TARGET_QUERY_PARAM, context.target);
        }
      }
      if (options && options.includeOverlayContext) {
        var overlayContext = readCurrentPreservedOverlayContext();
        if (overlayContext.overlayRequested && overlayContext.payload) {
          parsed.searchParams.set(INSPECT_OVERLAY_QUERY_PARAM, '1');
          parsed.searchParams.set(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM, overlayContext.payload);
          if (overlayContext.storageKey) {
            parsed.searchParams.set(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM, overlayContext.storageKey);
          }
        }
      }
      return formatLikeInput(parsed, input);
    } catch (error) {
      return input;
    }
  }

  function preserveCurrentProxyContextInUrl(input, options) {
    var projectLocation = parseCurrentProjectProxyLocation();
    if (projectLocation && projectLocation.projectId) {
      return preserveProjectIdInUrl(input, projectLocation.projectId, {
        includeInspectContext: !(options && options.includeInspectContext === false),
        includeOverlayContext: !(options && options.includeOverlayContext === false)
      });
    }
    var runId = getRunId();
    if (!runId) {
      return input;
    }
    if (usesStableCompatibilityUrls()) {
      return preserveCompatibilityContextInUrl(input, {
        includeInspectContext: !(options && options.includeInspectContext === false),
        includeOverlayContext: !(options && options.includeOverlayContext === false)
      });
    }
    return preserveRunIdInUrl(input, runId, {
      includeInspectContext: !(options && options.includeInspectContext === false),
      includeOverlayContext: !(options && options.includeOverlayContext === false)
    });
  }

  function preserveCurrentProxyTransportContextInUrl(input, options) {
    var runId = getRunId();
    if (runId) {
      return preserveRunIdViaDirectProxyInUrl(input, runId, {
        includeInspectContext: !(options && options.includeInspectContext === false),
        includeOverlayContext: !(options && options.includeOverlayContext === false)
      });
    }
    var projectLocation = parseCurrentProjectProxyLocation();
    if (projectLocation && projectLocation.projectId) {
      return preserveProjectIdInUrl(input, projectLocation.projectId, {
        includeInspectContext: !(options && options.includeInspectContext === false),
        includeOverlayContext: !(options && options.includeOverlayContext === false)
      });
    }
    return input;
  }

  function normalizeComparablePort(protocol, port) {
    var rawPort = typeof port === 'string' ? port.trim() : String(port || '').trim();
    if (rawPort) {
      return rawPort;
    }
    var normalizedProtocol = String(protocol || '').toLowerCase();
    if (normalizedProtocol === 'http:' || normalizedProtocol === 'ws:') {
      return '80';
    }
    if (normalizedProtocol === 'https:' || normalizedProtocol === 'wss:') {
      return '443';
    }
    return '';
  }

  function isEquivalentWebSocketProtocol(socketProtocol, pageProtocol) {
    var normalizedSocketProtocol = String(socketProtocol || '').toLowerCase();
    var normalizedPageProtocol = String(pageProtocol || '').toLowerCase();
    if (!normalizedSocketProtocol || !normalizedPageProtocol) {
      return false;
    }
    if (normalizedSocketProtocol === 'ws:') {
      return normalizedPageProtocol === 'http:' || normalizedPageProtocol === 'ws:';
    }
    if (normalizedSocketProtocol === 'wss:') {
      return normalizedPageProtocol === 'https:' || normalizedPageProtocol === 'wss:';
    }
    return normalizedSocketProtocol === normalizedPageProtocol;
  }

  function isSameOriginWebSocketUrl(parsed) {
    if (!parsed) {
      return false;
    }
    try {
      var current = new URL(window.location.href);
      return String(parsed.hostname || '').toLowerCase() === String(current.hostname || '').toLowerCase()
        && normalizeComparablePort(parsed.protocol, parsed.port) === normalizeComparablePort(current.protocol, current.port)
        && isEquivalentWebSocketProtocol(parsed.protocol, current.protocol);
    } catch (error) {
      return false;
    }
  }

  function preserveCurrentProxyTransportContextInWebSocketUrl(input, options) {
    if (typeof input !== 'string' && !(input instanceof URL)) {
      return input;
    }

    var rawValue = input instanceof URL ? input.toString() : String(input || '');
    if (!rawValue) {
      return input;
    }

    var isAbsolute = rawValue.startsWith('//') || ABSOLUTE_URL_PATTERN.test(rawValue);
    if (!isAbsolute) {
      return preserveCurrentProxyTransportContextInUrl(input, options);
    }

    try {
      var parsed = input instanceof URL
        ? new URL(input.toString())
        : new URL(rawValue, window.location.href);
      if (!isSameOriginWebSocketUrl(parsed)) {
        return input;
      }
      var nextRelativeUrl = preserveCurrentProxyTransportContextInUrl(
        '' + (parsed.pathname || '/') + (parsed.search || '') + (parsed.hash || ''),
        options
      );
      if (typeof nextRelativeUrl !== 'string' || !nextRelativeUrl) {
        return input;
      }
      var nextAbsoluteUrl = new URL(nextRelativeUrl, window.location.href);
      if (parsed.protocol === 'ws:' || parsed.protocol === 'wss:') {
        nextAbsoluteUrl.protocol = parsed.protocol;
      }
      return nextAbsoluteUrl.toString();
    } catch (error) {
      return input;
    }
  }

  function readNodeAttribute(node, attributeName) {
    if (!node) {
      return '';
    }
    if (typeof node.getAttribute === 'function') {
      var fromAttribute = node.getAttribute(attributeName);
      if (typeof fromAttribute === 'string') {
        return fromAttribute;
      }
    }
    if (attributeName === 'action' && typeof node.action === 'string') {
      return node.action;
    }
    if (attributeName === 'formaction' && typeof node.formAction === 'string') {
      return node.formAction;
    }
    return '';
  }

  function writeNodeAttribute(node, attributeName, value) {
    if (!node || typeof value !== 'string' || !value) {
      return;
    }
    if (typeof node.setAttribute === 'function') {
      try {
        node.setAttribute(attributeName, value);
      } catch (error) {
        // Ignore attribute assignment failures and still try DOM properties below.
      }
    }
    if (attributeName === 'action') {
      try {
        node.action = value;
      } catch (error) {
        // Ignore property assignment failures.
      }
      return;
    }
    if (attributeName === 'formaction') {
      try {
        node.formAction = value;
      } catch (error) {
        // Ignore property assignment failures.
      }
    }
  }

  function rewriteNodeNavigationAttribute(node, attributeName, fallbackUrl) {
    if (!node) {
      return '';
    }
    var rawValue = readNodeAttribute(node, attributeName);
    var sourceValue = rawValue || (typeof fallbackUrl === 'string' ? fallbackUrl : '');
    if (!sourceValue) {
      return '';
    }
    var nextValue = preserveCurrentProxyContextInUrl(sourceValue);
    if (typeof nextValue === 'string' && nextValue && nextValue !== rawValue) {
      writeNodeAttribute(node, attributeName, nextValue);
    }
    return nextValue;
  }

  function patchHistoryMethod(methodName) {
    var historyObject = window.history;
    var original = historyObject && historyObject[methodName];
    if (typeof original !== 'function') {
      return;
    }

    historyObject[methodName] = function patchedHistoryMethod(state, title, url) {
      var nextUrl = url == null ? url : preserveCurrentProxyContextInUrl(url);
      var result = original.call(this, state, title, nextUrl);
      scheduleInspectAuthHandling(0);
      return result;
    };
  }

  function patchLocationMethod(methodName) {
    var locationObject = window.location;
    var original = locationObject && locationObject[methodName];
    if (typeof original !== 'function') {
      return;
    }

    try {
      locationObject[methodName] = function patchedLocationMethod(url) {
        var nextUrl = url == null ? url : preserveCurrentProxyContextInUrl(url);
        return original.call(this, nextUrl);
      };
    } catch (error) {
      // Ignore readonly location methods in stricter browser environments.
    }
  }

  function isSameWindowAnchor(node) {
    if (!node || typeof node.getAttribute !== 'function') {
      return false;
    }
    if (node.tagName !== 'A') {
      return false;
    }
    var target = node.getAttribute('target');
    return !target || target === '_self';
  }

  function shouldIgnoreHref(rawHref) {
    if (typeof rawHref !== 'string' || !rawHref) {
      return true;
    }
    if (rawHref.startsWith('#')) {
      return true;
    }
    return rawHref.startsWith('javascript:')
      || rawHref.startsWith('mailto:')
      || rawHref.startsWith('tel:')
      || rawHref.startsWith('data:');
  }

  function isSameWindowForm(node) {
    if (!node) {
      return false;
    }
    if (String(node.tagName || '').toUpperCase() !== 'FORM') {
      return false;
    }
    var target = typeof node.getAttribute === 'function'
      ? node.getAttribute('target')
      : node.target;
    return !target || target === '_self';
  }

  function rewriteFormSubmissionTarget(form, submitter) {
    if (!isSameWindowForm(form)) {
      return;
    }
    var fallbackAction = currentRelativeLocationWithoutContext() || window.location.href || '/';
    rewriteNodeNavigationAttribute(form, 'action', fallbackAction);
    if (!submitter) {
      return;
    }
    var rawSubmitterAction = readNodeAttribute(submitter, 'formaction');
    if (rawSubmitterAction) {
      rewriteNodeNavigationAttribute(submitter, 'formaction', '');
    }
  }

  function patchFormMethod(methodName) {
    var Form = window.HTMLFormElement;
    if (!Form || !Form.prototype || typeof Form.prototype[methodName] !== 'function') {
      return;
    }
    var original = Form.prototype[methodName];
    Form.prototype[methodName] = function patchedFormMethod() {
      rewriteFormSubmissionTarget(this, arguments[0] || null);
      return original.apply(this, arguments);
    };
  }

  function ensureCompatibilityLocation() {
    var directLocation = parseCurrentDirectProxyLocation();
    var nextUrl = '';
    if (directLocation) {
      nextUrl = buildCompatibilityUrl(
        directLocation.targetPath,
        directLocation.search,
        directLocation.hash,
        directLocation.runId
      );
    } else {
      var projectLocation = parseCurrentProjectProxyLocation();
      var injectedRunId = getInjectedRunId();
      if (projectLocation && injectedRunId) {
        nextUrl = buildCompatibilityUrl(
          projectLocation.targetPath,
          projectLocation.search,
          projectLocation.hash,
          injectedRunId
        );
      }
    }
    if (!nextUrl) {
      return;
    }
    try {
      var current = new URL(window.location.href);
      var currentRelative = '' + (current.pathname || '/') + (current.search || '') + (current.hash || '');
      if (currentRelative === nextUrl) {
        return;
      }
    } catch (error) {
      // Ignore URL parse errors and still attempt to rewrite below.
    }
    if (window.history && typeof window.history.replaceState === 'function') {
      window.history.replaceState(window.history.state, '', nextUrl);
      return;
    }
    if (window.location && typeof window.location.replace === 'function') {
      window.location.replace(nextUrl);
    }
  }

  function patchFetch() {
    if (typeof window.fetch !== 'function') {
      return;
    }
    var originalFetch = window.fetch;
    window.fetch = function patchedFetch(input, init) {
      if (typeof Request !== 'undefined' && input instanceof Request) {
        var nextRequestUrl = preserveCurrentProxyTransportContextInUrl(input.url, {
          includeInspectContext: false,
          includeOverlayContext: false
        });
        if (typeof nextRequestUrl === 'string' && nextRequestUrl && nextRequestUrl !== input.url) {
          try {
            return originalFetch.call(this, new Request(nextRequestUrl, input), init);
          } catch (error) {
            // Fall back to the original request below if cloning fails.
          }
        }
      }
      var nextInput = preserveCurrentProxyTransportContextInUrl(input, {
        includeInspectContext: false,
        includeOverlayContext: false
      });
      return originalFetch.call(this, nextInput, init);
    };
  }

  function patchXmlHttpRequest() {
    var Xhr = window.XMLHttpRequest;
    if (!Xhr || !Xhr.prototype || typeof Xhr.prototype.open !== 'function') {
      return;
    }
    var originalOpen = Xhr.prototype.open;
    Xhr.prototype.open = function patchedXmlHttpRequestOpen(method, url) {
      var nextUrl = preserveCurrentProxyTransportContextInUrl(url, {
        includeInspectContext: false,
        includeOverlayContext: false
      });
      var args = Array.prototype.slice.call(arguments);
      args[1] = nextUrl;
      return originalOpen.apply(this, args);
    };
  }

  function patchWebSocket() {
    var NativeWebSocket = window.WebSocket;
    if (typeof NativeWebSocket !== 'function') {
      return;
    }
    function PatchedWebSocket(url, protocols) {
      var nextUrl = preserveCurrentProxyTransportContextInWebSocketUrl(url, {
        includeInspectContext: false,
        includeOverlayContext: false
      });
      if (arguments.length >= 2) {
        return new NativeWebSocket(nextUrl, protocols);
      }
      return new NativeWebSocket(nextUrl);
    }
    PatchedWebSocket.prototype = NativeWebSocket.prototype;
    ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(function copyConstant(name) {
      if (Object.prototype.hasOwnProperty.call(NativeWebSocket, name)) {
        PatchedWebSocket[name] = NativeWebSocket[name];
      }
    });
    window.WebSocket = PatchedWebSocket;
  }

  function normalizeLocationPathname(pathname) {
    var value = typeof pathname === 'string' ? pathname.trim() : '';
    if (!value) {
      return '/';
    }
    return value.charAt(0) === '/' ? value : '/' + value;
  }

  function stripCurrentProjectProxyPrefix(pathname) {
    var normalizedPathname = normalizeLocationPathname(pathname);
    var projectLocation = parseCurrentProjectProxyLocation();
    if (!projectLocation || !projectLocation.projectId) {
      return normalizedPathname;
    }
    var basePath = buildProjectProxyBasePath(projectLocation.projectId);
    if (normalizedPathname === basePath) {
      return '/';
    }
    if (normalizedPathname.indexOf(basePath + '/') === 0) {
      return normalizedPathname.slice(basePath.length) || '/';
    }
    return normalizedPathname;
  }

  function isAuthLikePathname(pathname) {
    var normalized = stripCurrentProjectProxyPrefix(pathname);
    return normalized === '/login' || normalized.indexOf('/login/') === 0;
  }

  function currentRelativeLocationWithoutContext() {
    try {
      var parsed = new URL(window.location.href);
      var projectLocation = parseCurrentProjectProxyLocation();
      if (projectLocation && projectLocation.projectId) {
        var basePath = buildProjectProxyBasePath(projectLocation.projectId);
        if (parsed.pathname === basePath) {
          parsed.pathname = '/';
        } else if (parsed.pathname.indexOf(basePath + '/') === 0) {
          parsed.pathname = parsed.pathname.slice(basePath.length) || '/';
        }
      }
      parsed.searchParams.delete(RUN_QUERY_PARAM);
      parsed.searchParams.delete(INSPECT_AUTH_QUERY_PARAM);
      parsed.searchParams.delete(INSPECT_TARGET_QUERY_PARAM);
      parsed.searchParams.delete(INSPECT_OVERLAY_QUERY_PARAM);
      parsed.searchParams.delete(INSPECT_OVERLAY_STORAGE_KEY_QUERY_PARAM);
      parsed.searchParams.delete(INSPECT_OVERLAY_PAYLOAD_QUERY_PARAM);
      return '' + (parsed.pathname || '/') + (parsed.search || '') + (parsed.hash || '');
    } catch (error) {
      return '';
    }
  }

  function dispatchInputEvents(input) {
    if (!input || typeof input.dispatchEvent !== 'function' || typeof Event !== 'function') {
      return;
    }
    try {
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (error) {
      // Ignore event construction issues in older environments.
    }
  }

  function assignInputValue(input, nextValue) {
    if (!input) {
      return;
    }
    try {
      input.value = nextValue;
    } catch (error) {
      // Ignore assignment failures and keep trying to submit below.
    }
    dispatchInputEvents(input);
  }

  function trySubmitDebugLoginForm() {
    if (!document || typeof document.querySelectorAll !== 'function') {
      return false;
    }
    var inputs = Array.prototype.slice.call(document.querySelectorAll('input'));
    var usernameInput = null;
    var passwordInput = null;
    for (var i = 0; i < inputs.length; i += 1) {
      var input = inputs[i];
      if (!input || typeof input.type !== 'string') {
        continue;
      }
      var inputType = String(input.type || '').toLowerCase();
      var inputName = String(input.name || '').toLowerCase();
      var autocomplete = String(input.autocomplete || '').toLowerCase();
      if (!passwordInput && inputType === 'password') {
        passwordInput = input;
      } else if (
        !usernameInput
        && (autocomplete === 'username' || inputName.indexOf('user') >= 0 || inputType === 'text' || inputType === 'email')
      ) {
        usernameInput = input;
      }
    }
    if (!passwordInput && !usernameInput) {
      return false;
    }

    assignInputValue(usernameInput, '');
    assignInputValue(passwordInput, '');

    var buttons = Array.prototype.slice.call(document.querySelectorAll('button, input[type="submit"]'));
    for (var j = 0; j < buttons.length; j += 1) {
      var button = buttons[j];
      if (!button) {
        continue;
      }
      var tagName = String(button.tagName || '').toUpperCase();
      var buttonType = String(button.type || '').toLowerCase();
      var isSubmitButton = (tagName === 'BUTTON' && (!buttonType || buttonType === 'submit'))
        || (tagName === 'INPUT' && buttonType === 'submit');
      if (isSubmitButton && typeof button.click === 'function') {
        button.click();
        return true;
      }
    }

    var form = (passwordInput && passwordInput.form) || (usernameInput && usernameInput.form) || null;
    if (form) {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
        return true;
      }
      if (typeof form.submit === 'function') {
        form.submit();
        return true;
      }
    }
    return false;
  }

  function maybeRestoreInspectTarget() {
    if (inspectTargetApplied) {
      debugLoginCompleted = true;
      return;
    }
    var target = getInspectTarget();
    if (!target) {
      inspectTargetApplied = true;
      debugLoginCompleted = true;
      return;
    }
    if (isAuthLikePathname(window.location.pathname)) {
      return;
    }
    var currentRelative = currentRelativeLocationWithoutContext();
    if (!currentRelative || currentRelative === target) {
      inspectTargetApplied = true;
      debugLoginCompleted = true;
      return;
    }
    inspectTargetApplied = true;
    var nextUrl = preserveCurrentProxyContextInUrl(target, {
      includeInspectContext: true,
      includeOverlayContext: true
    });
    if (window.location && typeof window.location.replace === 'function') {
      window.location.replace(nextUrl);
    }
  }

  function handleInspectAuthFlow() {
    debugLoginRetryHandle = 0;
    if (getInspectAuthStrategy() !== DEBUG_LOGIN_STRATEGY) {
      return;
    }
    if (isAuthLikePathname(window.location.pathname)) {
      if (debugLoginCompleted) {
        return;
      }
      if (debugLoginAttempts >= 20) {
        return;
      }
      debugLoginAttempts += 1;
      if (!trySubmitDebugLoginForm()) {
        scheduleInspectAuthHandling(200);
        return;
      }
      scheduleInspectAuthHandling(900);
      return;
    }
    maybeRestoreInspectTarget();
  }

  function scheduleInspectAuthHandling(delayMs) {
    if (debugLoginRetryHandle) {
      window.clearTimeout(debugLoginRetryHandle);
    }
    debugLoginRetryHandle = window.setTimeout(handleInspectAuthFlow, Math.max(0, Number(delayMs) || 0));
  }

  ensureCompatibilityLocation();
  patchHistoryMethod('pushState');
  patchHistoryMethod('replaceState');
  patchLocationMethod('assign');
  patchLocationMethod('replace');
  patchFormMethod('submit');
  patchFormMethod('requestSubmit');
  patchFetch();
  patchXmlHttpRequest();
  patchWebSocket();

  document.addEventListener('click', function handleClick(event) {
    if (event.defaultPrevented || event.button !== 0) {
      return;
    }
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }

    var node = event.target;
    while (node && node.nodeType === 1) {
      if (node.tagName === 'A') {
        break;
      }
      node = node.parentElement;
    }
    if (!isSameWindowAnchor(node)) {
      return;
    }

    var rawHref = node.getAttribute('href');
    if (shouldIgnoreHref(rawHref)) {
      return;
    }

    var nextHref = preserveCurrentProxyContextInUrl(rawHref);
    if (typeof nextHref === 'string' && nextHref && nextHref !== rawHref) {
      node.setAttribute('href', nextHref);
    }
  }, true);

  document.addEventListener('submit', function handleSubmit(event) {
    if (!event || event.defaultPrevented) {
      return;
    }
    rewriteFormSubmissionTarget(event.target, event.submitter || null);
  }, true);

  scheduleInspectAuthHandling(0);
  ensurePlayFreshnessIndicator();
  if (document && typeof document.addEventListener === 'function') {
    document.addEventListener('DOMContentLoaded', function onDomContentLoaded() {
      scheduleInspectAuthHandling(0);
      ensurePlayFreshnessIndicator();
    });
  }
})();
