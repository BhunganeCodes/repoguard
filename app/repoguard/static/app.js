(function () {
  "use strict";

  var STAGE_ORDER = ["load", "plan", "assess", "cross_check", "finalize"];
  var DEMO_URL = "https://github.com/example/demo-synthetic-repo";
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
  var resultBody = document.getElementById("result-body");
  var failureBody = document.getElementById("failure-body");
  var progressRepo = document.getElementById("progress-repo");
  var progressHint = document.getElementById("progress-hint");
  var srStatus = document.getElementById("sr-status");
  var demoPill = document.getElementById("demoPill");
  var form = document.getElementById("assess-form");
  var formError = document.getElementById("form-error");
  var submitBtn = document.getElementById("submit-btn");
  var urlInput = document.getElementById("repository_url");
  var commitInput = document.getElementById("commit");
  var modeSelect = document.getElementById("mode");

  function announce(message) {
    if (srStatus) { srStatus.textContent = message; }
  }

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
    hide(resultSection);
    hide(failureSection);
    resultBody.innerHTML = "";
    failureBody.innerHTML = "";
    formSection.classList.add("hidden");
    show(progressSection);
    progressRepo.textContent = "Repository: " + payload.repository_url;
    progressHint.textContent = payload.mode === "live"
      ? "Live assessments can take several minutes — the request continues until the provider responds."
      : "";
    announce(
      payload.mode === "demo"
        ? "Assessment started — demo."
        : "Assessment started for " + payload.repository_url + "."
    );

    try {
      var response = await fetch("/api/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      var body = await response.json();
      if (!response.ok) {
        announce("Assessment failed.");
        showFailure(failureCategoryForCode(detailCode(body.detail)));
        return;
      }
      if (body.status === "failed") {
        var err = (body.result && body.result.error) || {};
        announce("Assessment failed.");
        renderFailureFromResult(err);
        renderFailedResult(body);
        return;
      }
      renderReport(body);
      announce("Assessment completed.");
    } catch (networkError) {
      announce("Assessment failed — could not reach the service.");
      renderFailure("network");
    }
  }

  function detailCode(detail) {
    if (!detail || typeof detail === "string") { return null; }
    return detail.error || null;
  }

  /* ---------- failure UX (human-readable primary message) ---------- */

  /* Presentation-only classification. The evaluation engine's failure
     vocabulary is authoritative and intact; this maps it to a small set of
     human-facing messages. Timeout detection is text-based and conservative:
     provider errors only. Provider codes are never shown as the primary
     message, but stay available under the technical surface. */
  var FAILURE_SPECS = {
    provider_unavailable: {
      title: "Live Assessment isn't configured on this demo.",
      text: "This server can't reach an LLM provider, so Live isn't available. " +
        "The Demo runs the full pipeline locally — no network, no keys.",
      cta: "demo"
    },
    provider_timeout: {
      title: "The Live Assessment took too long to complete. No score was produced.",
      text: "The provider did not respond within its timeout and the run was " +
        "recorded as failed — RepoGuard never guesses a score.",
      cta: "demo"
    },
    provider_api: {
      title: "The assessment service could not complete this request. No score was produced.",
      text: "The provider failed or returned an unusable response. The result was " +
        "recorded as failed — RepoGuard never guesses a score.",
      cta: "demo"
    },
    repository: {
      title: "RepoGuard couldn't access that repository or commit.",
      text: "Check the URL and commit SHA and try again. No score was produced.",
      cta: "reset"
    },
    network: {
      title: "Could not reach the RepoGuard service.",
      text: "The request could not be sent. Try again in a moment.",
      cta: "reset"
    },
    generic: {
      title: "The assessment could not be completed. No score was produced.",
      text: "Something unexpected happened. Try again, or run the Demo.",
      cta: "reset"
    }
  };

  function failureCategoryForCode(code) {
    if (code === "provider_unavailable") { return "provider_unavailable"; }
    if (code === "repository_invalid" || code === "repository_unavailable" ||
        code === "snapshot_error" || code === "evidence_error") { return "repository"; }
    return "generic";
  }

  function resultFailureCategory(err) {
    var kind = err.kind || "unknown";
    var message = err.message || "";
    if (kind === "provider_error" &&
        /timeout|timed out|timed-out|run out of time/i.test(message)) {
      return "provider_timeout";
    }
    var providerish = [
      "provider_error", "malformed_response", "invalid_plan", "invalid_cross_check",
      "invalid_assessment", "incomplete_assessment", "invalid_evidence"
    ];
    if (providerish.indexOf(kind) !== -1) { return "provider_api"; }
    return "generic";
  }

  function auditRows(rows) {
    return "<dl class='audit'>" + rows.map(function (row) {
      return "<dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd>";
    }).join("") + "</dl>";
  }

  function renderFailure(category, technicalRows) {
    hide(progressSection);
    var spec = FAILURE_SPECS[category] || FAILURE_SPECS.generic;
    var cta = spec.cta === "demo"
      ? "<button type='button' class='cta cta-primary' data-action='try-demo'>Try Demo</button>"
      : "";
    var technical = technicalRows && technicalRows.length
      ? "<details class='tech'><summary>Technical details</summary><div class='tech-body'>" +
        auditRows(technicalRows) + "</div></details>"
      : "";
    failureBody.innerHTML = [
      "<div class='failcard'>",
      "<h3>" + esc(spec.title) + "</h3>",
      "<p>" + esc(spec.text) + "</p>",
      cta ? "<div class='failcard-actions'>" + cta + "</div>" : "",
      technical,
      "</div>"
    ].join("");
    show(failureSection);
  }

  function renderFailureFromResult(err) {
    var category = resultFailureCategory(err);
    renderFailure(category, [
      ["Error code", err.kind || "unknown"],
      ["Detail", err.message || "no further detail recorded"]
    ].concat((err.details && err.details.length ? err.details.map(function (d) {
      return ["Detail", d];
    }) : [])));
  }

  failureBody.addEventListener("click", function (event) {
    var button = event.target && event.target.tagName === "BUTTON" &&
      event.target.getAttribute("data-action") === "try-demo"
      ? event.target
      : null;
    if (!button) { return; }
    runDemo();
  });

  function renderFailedResult(body) {
    var result = body.result;
    if (!result) { return; }
    resultBody.innerHTML = [
      evidenceDetails(body),
      auditDetails(body, result)
    ].join("");
    show(resultSection);
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

    resultBody.innerHTML = [
      demoBanner(data.demo),
      "<div class='card scorecard'><div class='scoreline'>",
      "<div class='scorebig'>" + formatScore(summary.score) +
        (summary.possible != null ? "<small> / " + esc(summary.possible) + "</small>" : "") + "</div>",
      "<div class='dims'>" + renderDims(assessment.dimensions) + "</div>",
      "</div>",
      "<p class='score-meaning'>This is RepoGuard's assessment of the repository against " +
        "the canonical RepoGuard rubric (v" + esc(result.rubric_version) +
        ") and the extracted evidence — a deterministic, reproducible measurement, " +
        "not an AI confidence value.</p></div>",
      block("Findings", renderFindings(assessment)),
      evidenceDetails(data),
      auditDetails(data, result)
    ].join("");
    show(resultSection);
    hide(progressSection);
  }

  function evidenceDetails(data) {
    var evidence = data.evidence || {};
    var items = (evidence.items || []).length;
    return [
      "<details class='tech' id='evidence-details'>",
      "<summary>Evidence <span class='tech-count'>" + items + " items</span></summary>",
      "<div class='tech-body'>",
      renderEvidence(evidence),
      "</div></details>"
    ].join("");
  }

  function auditDetails(data, result) {
    return [
      "<details class='tech' id='audit-details'>",
      "<summary>Audit trail</summary>",
      "<div class='tech-body'>",
      renderAudit(data),
      block("Assessment workflow", renderStages(result)),
      "<div class='audit-download'><a class='download-link' " +
        "href='/api/assess/" + esc(data.assessment_id) + "/download' download>" +
        "Download assessment artifact (YAML)</a></div>",
      "</div></details>"
    ].join("");
  }

  function revealEvidence(link) {
    var targetId = link.getAttribute("href").slice(1);
    var row = document.getElementById(targetId);
    if (!row) { return; }
    var details = document.getElementById("evidence-details");
    if (details && !details.open) { details.open = true; }
    row.classList.add("ev-target");
    row.setAttribute("tabindex", "-1");
    if (row.scrollIntoView) { row.scrollIntoView({ behavior: "smooth", block: "center" }); }
    row.focus();
    announce("Opened the evidence section for cited evidence " + targetId.replace(/^evidence-/, "") + ".");
  }

  resultBody.addEventListener("click", function (event) {
    var link = event.target && event.target.tagName === "A" && event.target.classList.contains("ev-link")
      ? event.target
      : null;
    if (!link) { return; }
    event.preventDefault();
    revealEvidence(link);
  });

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

  /* Severity is a presentation-only classification, never a score:
     FOUND          -> POSITIVE
     NOT_FOUND      -> WARNING
     UNCERTAIN      -> WARNING
     NOT_APPLICABLE -> neutral (shown via the canonical status chip)
   Scores are never derived here; the artifact carries no per-finding signal
   that would defensibly support CRITICAL, so it is reserved and never used. */
  function severityFor(row) {
    switch (row.status) {
      case "FOUND": return "positive";
      case "NOT_FOUND": return "warning";
      case "UNCERTAIN": return "warning";
      case "NOT_APPLICABLE": return "neutral";
      default: return "neutral";
    }
  }

  function severityChip(row) {
    var key = severityFor(row);
    if (key === "neutral") { return ""; }
    return "<span class='sev sev-" + key + "'>" + key.toUpperCase() + "</span>";
  }

  function citationsLine(citations) {
    var list = Array.isArray(citations) ? citations : [];
    if (!list.length) { return ""; }
    var links = list.map(function (id) {
      return "<a class='ev-link' href='#evidence-" + esc(id) + "'>" + esc(id) + "</a>";
    }).join(", ");
    return "<div class='cites'>Evidence: " + links + "</div>";
  }

  function findingNotes(row) {
    var out = "";
    if (row.uncertainty_reason) {
      out += "<div class='note note-uncertain'>Uncertain: " + esc(row.uncertainty_reason) + "</div>";
    }
    if (row.justification) {
      out += "<div class='note'>Justification: " + esc(row.justification) + "</div>";
    }
    return out;
  }

  function renderFindings(assessment) {
    var criteria = Array.isArray(assessment.criteria) ? assessment.criteria : [];
    if (!criteria.length) { return "<p class='muted'>No findings.</p>"; }

    var byDim = {};
    var seen = [];
    criteria.forEach(function (row) {
      var dim = row.dimension || "other";
      if (!byDim[dim]) { byDim[dim] = []; seen.push(dim); }
      byDim[dim].push(row);
    });

    var counts = {};
    criteria.forEach(function (row) {
      counts[row.status || "?"] = (counts[row.status || "?"] || 0) + 1;
    });
    var summary = criteria.length + " findings — " + Object.keys(counts).sort().map(function (status) {
      return counts[status] + " " + status;
    }).join(" · ");

    var dimOrder = (Array.isArray(assessment.dimensions) ? assessment.dimensions : [])
      .map(function (d) { return d.dimension; });
    var order = dimOrder.concat(seen.filter(function (dim) { return dimOrder.indexOf(dim) === -1; }));

    var html = "<p class='muted findings-summary'>" + esc(summary) + "</p>" +
      "<p class='muted fields-note'>Each finding links to its extracted repository evidence below.</p>";
    order.forEach(function (dim) {
      html += "<div class='dimension-group'><h4>" + esc(DIM_LABELS[dim] || dim) + "</h4>";
      byDim[dim].forEach(function (row) {
        html += "<div class='criterion'><div class='row'>" +
          "<span class='title'>" + esc(row.criterion_id) + severityChip(row) + "</span>" +
          "<span>" + chipFor(row.status) + " <span class='score'>" +
          (row.score == null ? "—" : esc(row.score)) + "</span></span>" +
        "</div>" +
        citationsLine(row.citations) +
        findingNotes(row) +
        "</div>";
      });
      html += "</div>";
    });
    return html;
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

    var rows = [];
    if (evidence.case_id) { rows.push(["Case ID", esc(evidence.case_id), true]); }
    rows = rows.concat([
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
    ]);
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
        return "<tr id='evidence-" + esc(item.evidence_id) + "'><td>" + esc(item.category) + "</td>" +
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

  /* ---------- reset / run another assessment ---------- */

  function resetAssessment() {
    hide(progressSection);
    hide(resultSection);
    hide(failureSection);
    resultBody.innerHTML = "";
    failureBody.innerHTML = "";
    progressHint.textContent = "";
    submitBtn.disabled = false;
    formError.classList.add("hidden");
    urlInput.value = "";
    commitInput.value = "";
    modeSelect.value = "demo";
    demoPill.classList.add("hidden");
    show(formSection);
    formSection.scrollIntoView({ behavior: "smooth", block: "start" });
    urlInput.focus();
    announce("New assessment form ready.");
  }

  /* ---------- form wiring ---------- */

  function runDemo() {
    urlInput.value = DEMO_URL;
    commitInput.value = "";
    modeSelect.value = "demo";
    form.requestSubmit();
  }

  function startLive() {
    present("live");
    show(formSection);
    modeSelect.value = "live";
    urlInput.focus();
    formSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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

  document.getElementById("hero-demo").addEventListener("click", runDemo);
  document.getElementById("hero-live").addEventListener("click", startLive);
  document.getElementById("demo-btn").addEventListener("click", runDemo);

  var resetResultBtn = document.getElementById("new-assessment-result");
  var resetFailureBtn = document.getElementById("new-assessment-failure");
  if (resetResultBtn) { resetResultBtn.addEventListener("click", resetAssessment); }
  if (resetFailureBtn) { resetFailureBtn.addEventListener("click", resetAssessment); }
})();