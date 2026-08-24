// Shared fetch()-poll-until-done helper for the async update/analyze flows.
// Mirrors the desktop app's QTimer(1000ms) polling of sas_get_resource, just client-side.

function pollUntilDone(statusUrl, onTick, intervalMs) {
  intervalMs = intervalMs || 1000;
  return new Promise(function (resolve, reject) {
    var timer = setInterval(function () {
      fetch(statusUrl)
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (onTick) onTick(data);
          if (data.finished) {
            clearInterval(timer);
            resolve(data);
          }
        })
        .catch(function (err) {
          clearInterval(timer);
          reject(err);
        });
    }, intervalMs);
  });
}

function postJSON(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(function (resp) { return resp.json(); });
}
