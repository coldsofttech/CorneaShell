/*
 * Cornea client: the calls a page makes to its window, written once.
 *
 *   <script src="/api/client.js"></script>
 *
 * defines window.cornea. Everything is a same-origin fetch, so the session cookie goes with it and
 * no CORS setup is needed. Served by Cornea itself, so it works under the strict content security
 * policy (no inline script is involved).
 */
(function () {
  "use strict";

  var PREFIX = "__API_PREFIX__";

  /** A call that did not work. `status` is the HTTP status; `unavailable` means "not here". */
  function CorneaError(message, status, unavailable) {
    this.name = "CorneaError";
    this.message = message;
    this.status = status;
    this.unavailable = Boolean(unavailable);
  }
  CorneaError.prototype = Object.create(Error.prototype);
  CorneaError.prototype.constructor = CorneaError;

  function request(path, method, body) {
    var options = { method: method || "GET", headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(PREFIX + path, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var detail = data && (data.error || data.detail);
          throw new CorneaError(
            typeof detail === "string" ? detail : "The request failed (" + response.status + ").",
            response.status,
            false
          );
        }
        return data;
      });
    });
  }

  var windowControls = {
    /** The window's title and whether it is maximized, minimized or frameless. */
    state: function () {
      return request("/window");
    },
    minimize: function () {
      return request("/window/minimize", "POST");
    },
    maximize: function () {
      return request("/window/maximize", "POST");
    },
    restore: function () {
      return request("/window/restore", "POST");
    },
    /** Close the window. Resolves {ok: false, blocked: true} if the app holds it open. */
    close: function (options) {
      return request("/window/close", "POST", { force: Boolean(options && options.force) });
    },
    setTitle: function (title) {
      return request("/window/title", "POST", { title: title });
    },
  };

  var cornea = {
    window: windowControls,

    /**
     * Run a native action. Resolves with its result. Rejects with a CorneaError when the action
     * is unknown or switched off, its arguments are wrong, or it is not available here (for
     * example a dialog without a window, where `error.unavailable` is true).
     */
    call: function (action, args) {
      return request("/bridge/" + encodeURIComponent(action), "POST", args || {}).then(
        function (data) {
          if (data.available === false) {
            throw new CorneaError(data.reason || "That action is not available.", 200, true);
          }
          return data.result;
        }
      );
    },

    /** The names of the actions this page may call. */
    actions: function () {
      return request("/bridge").then(function (data) {
        return data.actions;
      });
    },

    /**
     * Hold the window open while the page is busy (true), or let it close (false). While held,
     * closing is blocked and the page gets a "close-blocked" event.
     */
    closeGuard: function (enabled) {
      return request("/window/close-guard", "POST", { enabled: Boolean(enabled) });
    },

    /**
     * Listen for an event from the host, such as "close-blocked", "drop" or
     * "notification-click", or one the app sends with shell.notify(). The handler gets the
     * event's detail. Returns a function that stops listening.
     */
    on: function (name, handler) {
      var listener = function (event) {
        handler(event.detail, event);
      };
      window.addEventListener("cornea:" + name, listener);
      return function () {
        window.removeEventListener("cornea:" + name, listener);
      };
    },

    CorneaError: CorneaError,
  };

  window.cornea = Object.freeze(cornea);
})();
