(function () {
  "use strict";

  var LIFECYCLE = ["queued", "snapshotting", "extracting", "assessing", "scoring"];
  var STAGE_ORDER = ["load", "plan", "assess", "cross_check", "finalize"];
  var DIM_LABELS = {
    architecture: "Architecture",
    testing: "Testing",
    maintainability: "Maintainability",
    dependencies: "Dependencies",
    documentation: "Documentation"
  };

  var formSection = document.getElementById("assessForm");
  var progressSection = document.getElementById("progress");
  var resultSection = document.getElementById("result");
  var failureSection = document.getElementById("failure");
  var demoPill = document.getElementById("demoPill");
  var form = document.getElementById("assess-form");
  var formError = document.getElementById("form-error");
  var submitBtn = document.getElementById("submit-btn");
  var urlInput = document.getElementById("repository_url");
  var commitInput = document.getElementById("commit");
  var modeSelect = document.getElementById("mode");

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function show(node) { node.classList.remove("hidden"); }
  function hide(node) { node.classList.add("hidden"); }

  function chipFor(status) {
    return '<span class="chip ' + esc(status) + '">' + esc(status) + "</span>";
  }

  function present(mode) {
    demoPill.classList.toggle("hidden", mode !== "demo");
    demoPill.textContent = "DEMO ASSESSMENT";
  }

  function setMessage(node, message) {
    if (message) { node.textContent = message; show(node); }
    else { hide(node); }
  }

  async function submit(payload) {
    setMessage(formError, null);
    present(payload.mode);
    hide(failureSection);
    hide(resultSection);
    formSection.classList.add("hidden");
    show(progressSection);
    startLifecycle();

    try {
      var response = await fetch("/api/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      var body = await response.json();
      stopLifecycle();
      if (!response.ok) {
        showFailure("Request failed", body.detail || "The assessment request was rejected.");
        return;
      }
      if (body.status === "failed") {
        var err = (body.result && body.result.error) || {};
        showFailure(err.kind || "assessment failed", err.message, err.details);
        renderAudit(body);
        renderEvidence(body.evidence);
        renderStages(body.result);
        return;
      }
      show(resultSection);
      hide(progressSection);
      renderReport(body);
    } catch (networkError) {
      stopLifecycle();
      showFailure("Network error", "Could not reach the RepoGuard API: " + networkError.message);
    }
  }

  /* ---------- in-flight lifecycle (honest: synchronous, so this is a
     placeholder until the pipeline's real stage trace arrives) ---------- */

  var lifecycleTimer = null;
  var lifecycleIndex = 0;

  function startLifecycle() {
    var items = Array.prototype.slice.call(document.querySelectorAll("#lifecycle li"));
    items.forEach(function (li) { li.classList.remove("active", "done"); });
    lifecycleIndex = 0;
    lifecycleTimer = setInterval(function () {
      var ring = LIFECYCLE.concat(["completed"]);
      if (lifecycleIndex > ring.length) { hide(progressSection); show(progressSection); }
      items.forEach(function (li, i) {
        li.classList.remove("active", "done");
        if (i < lifecycleIndex) { li.classList.add("done"); }
      });
      var current = items[lifecycleIndex];
      if (current) { current.classList.add("active"); }
      lifecycleIndex += 1;
    }, 650);
  }

  function stopLifecycle() {
    if (lifecycleTimer) { clearInterval(lifecycleTimer); lifecycleTimer = null; }
  }

  /* ---------- failure render ---------- */

  function showFailure(kind, message, details) {
    hide(progressSection);
    var lines = ["<div class='failcard'>",
      "<h3>" + esc(kind) + "</h3>",
      "<p>" + esc(message) + "</p>"].join("");
    if (details && details.length) {
      lines += "<ul>" + details.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") + "</ul>";
    }
    lines += "</div>";
    failureSection.innerHTML = lines;
    show(failureSection);
    show(resultSection ? resultSection : failureSection);
  }

  function detailsBlock(notes) {
    if (!notes) { return ""; }
    return "<div class='cites'>" + esc(notes) + "</div>";
  }

  /* ---------- report render ---------- */

  function renderReport(data) {
    var result = data.result || {};
    var assessment = result.assessment || {};
    var summary = assessment.summary || {};
    var evidence = data.evidence || {};

    resultSection.innerHTML = [
      demoBanner(data.demo),
      "<div class='card'><div class='scoreline'>",
      "<div class='scorebig'>" + formatScore(summary.score) + "<small> / 100</small></div>",
      "<div class='dims'>" + renderDims(assessment.dimensions) + "</div>",
      "</div>",
      "<p class='muted'>Overall score with " + Number(assessment.criteria ? assessment.criteria.length : 0) +
        " criteria scored across the five engineering dimensions.</p></div>",
      renderFindings(assessment),
      block("Audit & provenance", renderAudit(data)),
      block("Assessment workflow", renderStages(result)),
      block("Evidence", renderEvidence(evidence))
    ].join("");
    show(resultSection);
    hide(progressSection);
  }

  function demoBanner(isDemo) {
    if (!isDemo) { return ""; }
    return "<div class='demobanner'><strong>DEMO ASSESSMENT</strong><span>This result uses the deterministic synthetic demo — it is not an assessment of a real repository.</span></div>";
  }

  function formatScore(value) {
    var n = Number(value);
    if (!isFinite(n)) { return "—"; }
    return n.toFixed(1);
  }

  function renderDims(dimensions) {
    if (!Array.isArray(dimensions)) { return ""; }
    return dimensions.map(function (d) {
      var max = Number(d.maximum) || 0;
      var earned = Number(d.earned) || 0;
      var pct = max > 0 ? Math.min(100, Math.round((earned / max) * 100)) : 0;
      return "<div class='dimrow'>" +
        "<div class='dimlabel'><span>" + esc(DIM_LABELS[d.dimension] || d.dimension) + "</span>" +
        "<span>" + esc(d.earned) + " / " + esc(d.maximum) + "</span></div>" +
        "<div class='bar'><span style='width:" + pct + "%'></span></div>" +
      "</div>";
    }).join("");
  }

  function renderFindings(assessment) {
    var criteria = Array.isArray(assessment.criteria) ? assessment.criteria : [];
    var byDim = {};
    criteria.forEach(function (row) {
      var dim = row.dimension || "other";
      (byDim[dim] = byDim[dim] || []).push(row);
    });
    var html = "";
    Object.keys(byDim).sort().forEach(function (dim) {
      var rows = byDim[dim];
      var earned = rows.reduce(function (acc, r) { return acc + (Number(r.score) || 0); }, 0);
      html += "<div class='dimension-group'><h4>" + esc(DIM_LABELS[dim] || dim) +
        " <span class='dim-earned'>" + earned + " / 20</span></h4>";
      rows.forEach(function (row) {
        html += "<div class='criterion'><div class='row'>" +
          "<span class='title'>" + esc(row.criterion_id) + "</span>" +
          "<span>" + chipFor(row.status) + " <span class='score'>" +
          (row.score == null ? "—" : esc(row.score)) + "</span></span>" +
        "</div>" +
        (row.uncertainty_reason ? "<div class='cites'>" + esc(row.uncertainty_reason) + "</div>" : "") +
        (row.justification ? "<div class='cites'>" + esc(row.justification) + "</div>" : "") +
        "<div class='cites'>cites: " + esc((row.citations || []).join(", ")) + "</div>" +
        "</div>";
      });
      html += "</div>";
    });
    return block("Findings by dimension", html);
  }

  function block(title, innerHtml) {
    return "<section class='block'><h3>" + esc(title) + "</h3>" + innerHtml + "</section>";
  }

  function renderAudit(data) {
    var result = data.result || {};
    var evidence = data.evidence || {};
    var runtime = result.runtime || {};
    var provider = result.provider || {};
    var assessment = result.assessment || {};
    var config = provider.config || {};

    var rows = [
      ["Repository", evidence.name + " — " + evidence.repository_url, true],
      ["Commit (requested / verified)", esc(evidence.requested_commit) + " / " + esc(evidence.verified_commit)],
      ["Snapshot content hash", evidence.snapshot_content_hash],
      ["Evidence", esc(evidence.evidence_identity) + " (" + (evidence.items || []).length + " items)"],
      ["Rubric version", result.rubric_version],
      ["Assessment identity", assessment.assessment_identity],
      ["Result identity", result.result_identity],
      ["RepoGuard / prompt", result.repoguard_version + " / " + result.prompt_version],
      ["Model", esc(provider.name) + " — " + esc(provider.model)],
      ["Requested at", esc(runtime.requested_at)]
    ];
    if (config.base_url) { rows.push(["Provider base URL", config.base_url]); }
    if (runtime.latency_ms != null) {
      rows.push(["Latency", number(runtime.latency_ms / 1000) + " s"]);
    }
    if (assessment.summary && assessment.summary.pending && assessment.summary.pending.length) {
      rows.push(["Pending", esc(assessment.summary.pending.length)]);
    }
    return "<dl class='audit'>" + rows.map(function (row) {
      return "<dt>" + esc(row[0]) + "</dt><dd" + (row[2] ? " class='wide'" : "") + ">" + row[1] + "</dd>";
    }).join("") + "</dl>";
  }

  function renderStages(result) {
    var stages = (result.process && result.process.stages) || [];
    var items = stages.map(function (stage) {
      return "<li class='" + esc(stage.status) + "'>" + esc(stage.stage) + "</li>";
    });
    if (!items.length && result.error) {
      items = ["<li class='failed'>" + esc(result.error.kind) + "</li>"];
    }
    return "<ul class='stage-list'>" + items.join("") + "</ul>";
  }

  function renderEvidence(evidence) {
    var items = (evidence.items || []).slice();
    items.sort(function (a, b) {
      return (a.category || "").localeCompare(b.category || "") ||
        (a.evidence_id || "").localeCompare(b.evidence_id || "");
    });
    if (!items.length) { return "<p class='muted'>No evidence items.</p>"; }
    var found = items.filter(function (i) { return i.status === "FOUND"; }).length;
    return [
      "<p class='muted'>" + esc(evidence.evidence_identity) + " — " +
        items.length + " items, " + found + " found</p>",
      "<table><thead><tr><th>category</th><th>evidence</th><th>status</th><th>source paths</th></tr></thead><tbody>" +
      items.map(function (item) {
        return "<tr><td>" + esc(item.category) + "</td>" +
          "<td>" + esc(item.evidence_id) + "<div style='color:var(--muted);font-size:12px;'>" + esc(item.observation) + "</div></td>" +
          "<td>" + chipFor(item.status) + "</td>" +
          "<td>" + esc((item.source_paths || []).join(", ")) + "</td></tr>";
      }).join("") +
      "</tbody></table>"
    ].join("");
  }

  function number(value) {
    var n = Number(value);
    return isFinite(n) ? n.toFixed(1) : "—";
  }

  /* ---------- form wiring ---------- */

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submitBtn.disabled = true;
    var payload = {
      repository_url: urlInput.value.trim(),
      commit: commitInput.value.trim() || null,
      mode: modeSelect.value
    };
    submit(payload).then(function () { submitBtn.disabled = false; });
  });

  document.getElementById("demo-btn").addEventListener("click", function () {
    urlInput.value = "https://github.com/example/demo-synthetic-repo";
    commitInput.value = "";
    modeSelect.value = "demo";
    form.requestSubmit();
  });
})();