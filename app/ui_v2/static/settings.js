/* Settings: providers, model routing, gates and keys.
 *
 * Every endpoint here is behind require_admin (loopback, or a bearer token), so
 * a 403 is a normal answer rather than an error -- it means "you are not on the
 * machine this runs on", and the page says so instead of showing a stack.
 */
(function (RF) {
  "use strict";

  var el;

  /* Each profile carries its own `fields` schema -- key, label, type, help --
   * so the form is generated from what the adapter actually accepts rather than
   * a hardcoded case per adapter. A new adapter gets an editor for free. */
  function editProfile(kind, profile, adapters) {
    var isNew = !profile;
    profile = profile || { adapter: adapters[0], settings: {}, fields: [] };
    var values = Object.assign({}, profile.settings || {});
    var inputs = {};

    var nameInput = el("input", { class: "input", value: profile.name || "",
                                  disabled: !isNew, placeholder: "a short name" });
    var adapterSelect = el("select", { class: "select", disabled: !isNew },
      adapters.map(function (a) {
        return el("option", { value: a, selected: a === profile.adapter }, a);
      }));

    var fieldHost = el("div", { class: "stack", "data-gap": "3" });

    /* The schema says what each field *is* -- select, bool, keyname, voice,
     * number, text -- and rendering everything as a text box throws that away.
     * "Structured output" is three fixed values; typing one is a way to get it
     * wrong. */
    function drawFields(fields) {
      inputs = {};
      RF.dom.mount(fieldHost, (fields || []).map(function (field) {
        var value = values[field.key];
        var control = buildControl(kind, field, value, profile);
        inputs[field.key] = control;
        return el("label", { class: "field" },
          el("span", { class: "field__label" }, field.label || field.key),
          control.node,
          field.help ? el("span", { class: "field__hint" }, field.help) : null);
      }));
    }
    drawFields(profile.fields);

    /* Changing the adapter changes which fields exist, so the form follows it
     * rather than showing the previous adapter's shape. */
    adapterSelect.addEventListener("change", function () {
      var match = (window.__RF_PROFILES || []).filter(function (p) {
        return p.adapter === adapterSelect.value;
      })[0];
      drawFields(match ? match.fields : []);
    });

    var handle = RF.dom.dialog(RF.dom.frag(
      el("div", { class: "dialog__head" },
        el("h2", { class: "card__title" },
           isNew ? "New " + (kind === "llm" ? "model" : "voice") + " profile"
                 : "Edit " + profile.name)),
      el("div", { class: "dialog__body stack", "data-gap": "4" },
        el("label", { class: "field" },
          el("span", { class: "field__label" }, "Name"),
          nameInput,
          el("span", { class: "field__hint" },
             isNew ? "Letters, digits, - and _."
                   : "A profile's name and adapter cannot change: its settings mean "
                     + "different things to different adapters, and reinterpreting a "
                     + "base_url silently is worse than making a new one.")),
        el("label", { class: "field" },
          el("span", { class: "field__label" }, "Adapter"),
          adapterSelect),
        fieldHost),
      el("div", { class: "dialog__foot" },
        el("button", { class: "btn btn--ghost",
                       onclick: function () { handle.close(); } }, "Cancel"),
        el("button", { class: "btn btn--primary", onclick: function () {
          var name = nameInput.value.trim();
          if (!name) return;
          var settings = {};
          Object.keys(inputs).forEach(function (key) {
            var read = inputs[key].read();
            if (read === "" || read === null || read === undefined) return;
            settings[key] = read;
          });
          handle.close();
          RF.api.put("/api/settings/" + kind + "/profiles/" + encodeURIComponent(name), {
            adapter: adapterSelect.value,
            model: settings.model || "",
            base_url: settings.base_url || null,
            api_key_env: settings.api_key_env || null,
            settings: settings,
          })
            .then(function () { RF.dom.toast(name + " saved", { kind: "ok" }); load(); })
            .catch(function (error) {
              RF.dom.toast(error.message, { kind: "error", timeout: 12000 });
            });
        } }, "Save"))
    ), { label: isNew ? "New profile" : "Edit " + profile.name });
    nameInput.focus();
  }

  /* One control per declared type. `read()` is what the caller uses, so the
   * dialog never has to know which widget a field turned into. */
  function buildControl(kind, field, value, profile) {
    if (field.type === "select") {
      var select = el("select", { class: "select" },
        (field.options || []).map(function (option) {
          return el("option", { value: option, selected: String(value) === option }, option);
        }));
      return { node: select, read: function () { return select.value; } };
    }

    if (field.type === "bool") {
      var box = el("input", { type: "checkbox", checked: value === true });
      return {
        node: el("span", { class: "switch" }, box, el("span", { class: "switch__track" })),
        read: function () { return box.checked; },
      };
    }

    if (field.type === "voice") {
      // Populated from the provider itself when it can be reached; a plain text
      // box otherwise, because a voice id typed by hand still works and an
      // unreachable provider must not block editing the rest of the profile.
      var input = el("input", { class: "input", value: value == null ? "" : String(value),
                                list: "voices-" + field.key });
      var list = el("datalist", { id: "voices-" + field.key });
      var wrap = el("span", { class: "field__control" }, input, list);
      if (profile && profile.name) {
        RF.api.get("/api/settings/" + kind + "/profiles/" +
                   encodeURIComponent(profile.name) + "/voices")
          .then(function (result) {
            RF.dom.mount(list, (result.voices || []).map(function (voice) {
              return el("option", { value: voice.id || voice.voice_id || voice },
                        voice.name || "");
            }));
          })
          .catch(function () { /* unreachable provider; the text box still works */ });
      }
      return { node: wrap, read: function () { return input.value.trim(); } };
    }

    if (field.type === "number") {
      var number = el("input", { class: "input", type: "number", step: field.step || "any",
                                 value: value == null ? "" : String(value) });
      return {
        node: number,
        read: function () {
          var raw = number.value.trim();
          return raw === "" ? null : Number(raw);
        },
      };
    }

    // keyname and text. keyname offers the variables already in use, since a
    // key saved under a name no profile references does nothing.
    var text = el("input", { class: "input", value: value == null ? "" : String(value),
                             list: field.type === "keyname" ? "known-keynames" : null,
                             placeholder: field.type === "keyname" ? "SOMETHING_API_KEY" : null });
    return { node: text, read: function () { return text.value.trim(); } };
  }

  function removeProfile(kind, profile) {
    RF.dom.confirm({
      title: "Delete " + profile.name + "?",
      body: "Any reel configured to use it falls back to whichever profile is active.",
      confirmLabel: "Delete", danger: true,
    }).then(function (yes) {
      if (!yes) return;
      RF.api.del("/api/settings/" + kind + "/profiles/" + encodeURIComponent(profile.name))
        .then(function () { RF.dom.toast(profile.name + " deleted", { kind: "ok" }); load(); })
        .catch(function (error) {
          RF.dom.toast(error.message, { kind: "error", timeout: 10000 });
        });
    });
  }

  function profileList(kind, block, adapters) {
    var profiles = block.profiles || [];
    return el("div", { class: "card card--flush" },
      el("div", { class: "card__head" },
        el("span", { class: "card__title grow" },
           kind === "llm" ? "Language models" : "Voices"),
        el("span", { class: "badge" }, "active: " + (block.active || "none")),
        el("button", { class: "btn btn--sm",
          onclick: function () { editProfile(kind, null, adapters); } },
           RF.icon("plus", { size: 14 }), "Add")),
      el("table", { class: "table" },
        el("thead", null, el("tr", null,
          el("th", null, "profile"), el("th", null, "adapter"),
          el("th", null, "model"), el("th", null, "key"), el("th", null, ""))),
        el("tbody", null, profiles.map(function (p) {
          var on = p.name === block.active;
          var key = p.key || {};
          return el("tr", null,
            el("th", null, p.name, " ",
               on ? el("span", { class: "chip chip--done" }, "active") : null),
            el("td", { class: "muted" }, p.adapter || ""),
            el("td", { class: "mono truncate" }, p.model || ""),
            el("td", null, p.api_key_env
              ? el("span", { class: "field__hint" },
                   key.state === "set" ? (key.masked || "set") : "not set")
              : el("span", { class: "field__hint" }, "none needed")),
            el("td", { class: "table__num" },
              el("button", { class: "iconbtn", title: "Test this profile",
                onclick: function (event) { test(kind, p.name, event.currentTarget); },
              }, RF.icon("refresh", { size: 15 })),
              el("button", { class: "iconbtn", title: "Edit",
                onclick: function () { editProfile(kind, p, adapters); },
              }, RF.icon("settings", { size: 15 })),
              el("button", { class: "iconbtn", title: "Delete",
                onclick: function () { removeProfile(kind, p); },
              }, RF.icon("trash", { size: 15 })),
              on ? null : el("button", { class: "btn btn--sm",
                onclick: function () { activate(kind, p.name); } }, "Use")));
        }))));
  }

  function activate(kind, name) {
    // `name` is an embedded Body field, not a query parameter -- sending it in
    // the query returns "name: Field required", which reads like the UI failed
    // to pass a name at all rather than passing it in the wrong place.
    RF.api.post("/api/settings/" + kind + "/active", { name: name })
      .then(function () { RF.dom.toast(name + " is now active", { kind: "ok" }); load(); })
      .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
  }

  function test(kind, name, button) {
    button.dataset.busy = "1";
    RF.api.post("/api/settings/" + kind + "/profiles/" + encodeURIComponent(name) + "/test", {})
      .then(function (result) {
        // The probe answers `reachable` and, separately, `authenticated` --
        // reading a non-existent `ok` reported every provider as unreachable,
        // including the two that answered. They are separate questions: a local
        // vLLM needs no key, and a hosted one can be up and still refuse you.
        var message;
        if (!result.reachable) {
          message = "not reachable — " + (result.error || "no answer") +
                    (result.base_url ? " (" + result.base_url + ")" : "");
        } else if (result.authenticated === false) {
          message = "reachable, but the key was refused" +
                    (result.api_key_env ? " — check " + result.api_key_env : "");
        } else {
          message = "reachable" +
                    (result.available_models && result.available_models.length
                       ? " — " + result.available_models.length + " models" : "");
        }
        RF.dom.toast(name + ": " + message,
                     { kind: result.reachable && result.authenticated !== false
                             ? "ok" : "error", timeout: 10000 });
      })
      .catch(function (error) {
        RF.dom.toast(name + ": " + error.message, { kind: "error", timeout: 9000 });
      })
      .then(function () { delete button.dataset.busy; });
  }

  /* Which model does what. Worth its own control rather than a read-only
   * table: the whole point of roles is that storyboard codegen wants the
   * strongest model available while the cheap stages do not, and that is a
   * decision people revise. */
  function rolesCard(settings) {
    var block = settings.llm || {};
    var roles = block.roles || {};
    var names = block.role_names || Object.keys(roles);
    var profiles = block.profiles || [];
    if (!names.length) return null;

    var picks = {};

    function save() {
      var payload = {};
      names.forEach(function (role) {
        var value = picks[role].value;
        payload[role] = value ? { profile: value } : {};
      });
      RF.api.put("/api/settings/llm/roles", payload)
        .then(function () { RF.dom.toast("routing saved", { kind: "ok" }); load(); })
        .catch(function (error) {
          RF.dom.toast(error.message, { kind: "error", timeout: 10000 });
        });
    }

    return el("div", { class: "card stack", "data-gap": "4" },
      el("div", null,
        el("div", { class: "card__title" }, "Which model does what"),
        el("div", { class: "field__hint" },
           "Left unset, a stage uses whichever profile is active. Storyboard " +
           "codegen is the one worth pointing at the strongest model you have.")),

      el("div", { class: "stack", "data-gap": "3" },
        names.map(function (role) {
          var current = (roles[role] || {}).profile || "";
          var select = el("select", { class: "select", onchange: save },
            [el("option", { value: "" }, "use the active profile (" +
                                          (block.active || "none") + ")")]
              .concat(profiles.map(function (p) {
                return el("option", { value: p.name, selected: p.name === current },
                          p.name + (p.model ? " — " + p.model : ""));
              })));
          picks[role] = select;
          return el("label", { class: "field" },
            el("span", { class: "field__label" }, RF.stages.label(role)),
            select);
        })),

      /* `presets` is an object keyed by name, each carrying a label and a
       * sentence explaining the trade -- which is the useful part. Treating it
       * as an array threw the explanation away and then failed on .map. */
      el("div", { class: "stack", "data-gap": "2" },
        el("span", { class: "field__hint" }, "Or start from a preset"),
        el("div", { class: "grid", dataset: { min: "220" } },
          Object.keys(block.presets || {}).map(function (key) {
            var preset = block.presets[key] || {};
            return el("button", { class: "choicecard", type: "button",
              onclick: function () { applyPreset(key, preset.label || key); } },
              el("span", { class: "choicecard__title" }, preset.label || key),
              preset.description
                ? el("span", { class: "choicecard__body" }, preset.description) : null);
          }))));
  }

  function applyPreset(key, label) {
    RF.api.post("/api/settings/llm/roles/preset/" + encodeURIComponent(key), {})
      .then(function () { RF.dom.toast(label + " applied", { kind: "ok" }); load(); })
      .catch(function (error) {
        RF.dom.toast(error.message, { kind: "error", timeout: 10000 });
      });
  }

  /* ElevenLabs rotates keys on its own when one runs out of credit; this is for
   * choosing one deliberately, or clearing the pin to let it rotate again. */
  function ttsKeyCard(settings) {
    var tts = settings.tts || {};
    var active = (tts.profiles || []).filter(function (p) {
      return p.name === tts.active;
    })[0];
    if (!active || active.adapter !== "elevenlabs") return null;
    var keys = (active.credits && active.credits.keys) || active.keys;
    if (!keys || !keys.length) return null;

    return el("div", { class: "card stack", "data-gap": "3" },
      el("div", { class: "card__title" }, "ElevenLabs keys"),
      el("div", { class: "field__hint" },
         "A key that runs out of credit is rotated past automatically. Pin one " +
         "to use it deliberately, or clear the pin to rotate again."),
      el("div", { class: "cluster", "data-gap": "2" },
        keys.map(function (key, index) {
          var label = key.label || key.name || ("key " + (index + 1));
          return el("button", { class: "btn btn--sm" + (key.pinned ? " btn--primary" : ""),
            onclick: function () { pinKey(label); } },
            label + (key.remaining !== undefined ? " · " + key.remaining + " left" : ""));
        }),
        el("button", { class: "btn btn--sm btn--quiet",
          onclick: function () { pinKey(null); } }, "Rotate automatically")));
  }

  function pinKey(label) {
    var path = "/api/config/tts/key" + (label ? "?label=" + encodeURIComponent(label) : "");
    RF.api.post(path, {})
      .then(function () {
        RF.dom.toast(label ? "pinned to " + label : "rotating automatically", { kind: "ok" });
        load();
      })
      .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
  }

  var STAGES = ["ingest", "content", "cover", "audio", "align",
                "storyboard", "render", "verify", "package"];

  function gatesCard(settings) {
    var manual = (((settings.approval || {}).manual_stages) || []).slice();

    function setGates(stages, message) {
      return RF.api.put("/api/settings/approval", { manual_stages: stages })
        .then(function () { RF.dom.toast(message, { kind: "ok" }); load(); })
        .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
    }

    function toggle(stage) {
      var index = manual.indexOf(stage);
      if (index === -1) manual.push(stage); else manual.splice(index, 1);
      setGates(manual, "gates saved");
    }

    return el("div", { class: "card stack", "data-gap": "3" },
      el("div", { class: "card__title" }, "Review gates"),
      el("div", { class: "field__hint" },
         "A reel pauses after each of these and waits for you. It matters more " +
         "with a queue: a queued reel that stops at a gate releases the slot and " +
         "lets the next one start, so five reels with two gates each drain in " +
         "minutes into five reels awaiting review."),
      el("div", { class: "cluster", "data-gap": "2" },
        STAGES.map(function (stage) {
          var on = manual.indexOf(stage) !== -1;
          return el("button", {
            class: "chip " + (on ? "chip--review" : ""),
            "aria-pressed": String(on),
            title: on ? "Pausing here — click to run straight through"
                      : "Running straight through — click to pause here",
            onclick: function () { toggle(stage); },
          }, RF.stages.label(stage));
        })),
      el("div", { class: "cluster", "data-gap": "2" },
        el("button", { class: "btn btn--sm btn--quiet", onclick: function () {
          setGates([], "gates cleared");
        } }, "Run straight through"),
        el("button", { class: "btn btn--sm btn--quiet", onclick: function () {
          setGates(STAGES.slice(), "pausing at every stage");
        } }, "Pause everywhere")));
  }

  function secretsCard(rows) {
    rows = rows || [];
    return el("div", { class: "card card--flush" },
      el("div", { class: "card__head" },
        el("span", { class: "card__title grow" }, "API keys"),
        el("span", { class: "field__hint" }, "stored locally, never sent back")),
      rows.length
        ? el("table", { class: "table table--dense" },
            el("tbody", null, rows.map(function (row) {
              return el("tr", null,
                el("th", { class: "mono" }, row.name),
                el("td", null,
                   row.state === "set"
                     ? el("span", { class: "chip chip--done" },
                          row.masked || "set")
                     : el("span", { class: "muted" }, "not set"),
                   row.source ? el("span", { class: "field__hint" },
                                   " from " + row.source) : null,
                   /* A key set here does nothing while an environment variable
                    * of the same name exists, because the environment wins.
                    * Saying so beats wondering why a saved key had no effect. */
                   row.shadowed ? el("div", { class: "field__hint warn" },
                     "an environment variable of this name is set and takes "
                     + "precedence over anything saved here") : null),
                el("td", { class: "table__num" },
                  el("button", { class: "btn btn--sm", onclick: function () {
                    editSecret(row);
                  } }, row.state === "set" ? "Replace" : "Set"),
                  row.state === "set" ? el("button", { class: "btn btn--sm btn--quiet",
                    onclick: function () { clearSecret(row); } }, "Clear") : null));
            })))
        : el("div", { class: "card__body muted" }, "No keys are needed by the "
            + "profiles you have configured."));
  }

  function editSecret(row) {
    var input = el("input", { class: "input", type: "password",
                              placeholder: row.name, autocomplete: "off" });
    var handle = RF.dom.dialog(RF.dom.frag(
      el("div", { class: "dialog__head" },
        el("h2", { class: "card__title" },
           (row.state === "set" ? "Replace " : "Set ") + row.name)),
      el("div", { class: "dialog__body stack", "data-gap": "3" },
        input,
        el("div", { class: "field__hint" },
           "Written to data/secrets.json with owner-only permissions. It is never "
           + "returned by any endpoint — only whether it is set, and a masked form.")),
      el("div", { class: "dialog__foot" },
        el("button", { class: "btn btn--ghost", onclick: function () { handle.close(); } },
           "Cancel"),
        el("button", { class: "btn btn--primary", onclick: function () {
          var value = input.value.trim();
          if (!value) return;
          handle.close();
          RF.api.put("/api/settings/secrets", { name: row.name, value: value })
            .then(function () { RF.dom.toast(row.name + " saved", { kind: "ok" }); load(); })
            .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
        } }, "Save"))
    ), { label: "Set " + row.name });
    input.focus();
  }

  function clearSecret(row) {
    RF.dom.confirm({
      title: "Clear " + row.name + "?",
      body: "Anything using it stops working until it is set again.",
      confirmLabel: "Clear", danger: true,
    }).then(function (yes) {
      if (!yes) return;
      RF.api.del("/api/settings/secrets/" + encodeURIComponent(row.name))
        .then(function () { RF.dom.toast(row.name + " cleared", { kind: "ok" }); load(); })
        .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
    });
  }

  function load() {
    var host = document.querySelector("[data-settings]");
    return Promise.all([
      RF.api.get("/api/settings"),
      RF.api.get("/api/config/profiles"),
      RF.api.get("/api/settings/secrets").catch(function () { return { secrets: [] }; }),
    ]).then(function (results) {
      var settings = results[0] || {};
      var profiles = results[1] || {};
      var secrets = (results[2] || {}).secrets || [];
      // the profile editor reads `fields` off whichever adapter is chosen
      window.__RF_PROFILES = (settings.llm.profiles || []).concat(settings.tts.profiles || []);
      var keyNames = secrets.map(function (row) { return row.name; });
      RF.dom.mount(host, [
        el("h1", { class: "section__title" }, "Settings"),
        el("datalist", { id: "known-keynames" }, keyNames.map(function (name) {
          return el("option", { value: name });
        })),
        profileList("llm", settings.llm || {}, settings.llm.adapters || []),
        profileList("tts", settings.tts || {}, settings.tts.adapters || []),
        rolesCard(settings),
        ttsKeyCard(settings),
        gatesCard(settings),
        secretsCard(secrets),
      ].filter(Boolean));
    }).catch(function (error) {
      var body = error.status === 403
        ? el("div", { class: "callout callout--info" },
            el("div", null,
              el("div", { class: "callout__title" }, "Settings are local-only"),
              el("div", null, "These controls answer only to a request from the " +
                 "machine ReelForge runs on, or one carrying the admin token. " +
                 "That is deliberate: they hold API keys.")))
        : el("div", { class: "callout callout--error" },
            el("div", null,
              el("div", { class: "callout__title" }, "Settings could not be loaded"),
              el("div", null, error.message)));
      RF.dom.mount(host, [el("h1", { class: "section__title" }, "Settings"), body]);
    });
  }

  RF.shell.ready(function () { el = RF.dom.el; RF.stages.refresh(); load(); });
})(window.RF || (window.RF = {}));
