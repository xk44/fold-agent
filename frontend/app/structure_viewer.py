from __future__ import annotations

import json


def list_structure_artifacts(artifacts: list[dict] | None) -> list[dict]:
    candidates = artifacts or []
    return [
        artifact
        for artifact in candidates
        if artifact.get("artifact_type") == "alphafold_model_cif"
        or str(artifact.get("filename") or "").lower().endswith((".cif", ".mmcif", ".pdb"))
    ]


def select_structure_artifact(artifacts: list[dict] | None) -> dict | None:
    candidates = list_structure_artifacts(artifacts)
    priority = (
        lambda artifact: artifact.get("artifact_type") == "alphafold_model_cif",
        lambda artifact: str(artifact.get("filename") or "").lower().endswith((".cif", ".mmcif")),
        lambda artifact: str(artifact.get("filename") or "").lower().endswith(".pdb"),
    )
    for predicate in priority:
        match = next((artifact for artifact in candidates if predicate(artifact)), None)
        if match:
            return match
    return None


def viewer_format_for_artifact(
    artifact: dict | None, structure_job_payload: dict | None = None
) -> str:
    output_format = ((structure_job_payload or {}).get("confidence_metrics") or {}).get(
        "output_format"
    )
    if output_format in {"mmcif", "cif"}:
        return "mcif"
    if output_format == "pdb":
        return "pdb"
    filename = str((artifact or {}).get("filename") or "").lower()
    if filename.endswith((".cif", ".mmcif")):
        return "mcif"
    return "pdb"


def format_structure_artifact_option(
    artifact: dict, structure_job_payload: dict | None = None
) -> str:
    return (
        f"{artifact.get('artifact_type') or 'structure_artifact'} · "
        f"{viewer_format_for_artifact(artifact, structure_job_payload)} · "
        f"{artifact.get('filename') or artifact.get('path') or 'unknown'}"
    )


def format_structure_confidence_summary(
    structure_job_payload: dict | None,
) -> dict[str, str]:
    metrics = (structure_job_payload or {}).get("confidence_metrics") or {}
    model_path = (
        metrics.get("model_cif")
        or metrics.get("pdb_file")
        or (structure_job_payload or {}).get("output_path")
        or "n/a"
    )
    return {
        "ranking_score": (
            f"{metrics.get('ranking_score'):.2f}"
            if metrics.get("ranking_score") is not None
            else "n/a"
        ),
        "ptm": f"{metrics.get('ptm'):.2f}" if metrics.get("ptm") is not None else "n/a",
        "iptm": (f"{metrics.get('iptm'):.2f}" if metrics.get("iptm") is not None else "n/a"),
        "output_format": str(metrics.get("output_format") or "n/a"),
        "source_url": str(metrics.get("source_url") or "n/a"),
        "model_path": str(model_path),
    }


def format_structure_confidence_operator_summary(
    structure_job_payload: dict | None,
) -> str:
    summary = format_structure_confidence_summary(structure_job_payload)
    prefix = (
        "Structure confidence ready"
        if all(summary.get(key) != "n/a" for key in ("ranking_score", "ptm", "iptm"))
        else "Structure confidence incomplete"
    )
    return " · ".join(
        [
            prefix,
            f"ranking_score={summary['ranking_score']}",
            f"ptm={summary['ptm']}",
            f"iptm={summary['iptm']}",
            f"format={summary['output_format']}",
            f"source={summary['source_url']}",
            f"model={summary['model_path']}",
        ]
    )


def choose_compare_artifact(
    artifacts: list[dict] | None, selected_artifact: dict | None
) -> dict | None:
    candidates = list_structure_artifacts(artifacts)
    selected_path = (selected_artifact or {}).get("path")
    return next(
        (artifact for artifact in candidates if artifact.get("path") != selected_path),
        None,
    )


def build_structure_viewer_html(structure_text: str, file_format: str) -> str:
    escaped_structure = json.dumps(structure_text)
    escaped_format = json.dumps(file_format)
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <style>
      html, body, #viewer {{
        margin: 0;
        width: 100%;
        height: 100%;
        background: #0b0f14;
        overflow: hidden;
      }}
      .hud {{
        position: absolute;
        top: 12px;
        left: 12px;
        z-index: 10;
        color: #dbe7f5;
        font-family: Inter, system-ui, sans-serif;
        font-size: 12px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        background: rgba(11, 15, 20, 0.72);
        border: 1px solid rgba(120, 160, 200, 0.28);
        border-radius: 10px;
        padding: 8px 10px;
        backdrop-filter: blur(12px);
      }}
    </style>
    <script src=\"https://3dmol.org/build/3Dmol-min.js\"></script>
  </head>
  <body>
    <div class=\"hud\">3D structure viewer</div>
    <div id=\"viewer\"></div>
    <script>
      const structureText = {escaped_structure};
      const host = document.getElementById("viewer");
      if (!window.$3Dmol) {{
        host.innerHTML =
          '<div style="color:#ff9b9b;padding:16px;font-family:sans-serif;">' +
          '3Dmol.js failed to load.</div>';
      }} else {{
        const viewer = $3Dmol.createViewer(host, {{ backgroundColor: '#0b0f14' }});
        viewer.addModel(structureText, {escaped_format});
        viewer.setStyle(
          {{}},
          {{ cartoon: {{ color: 'spectrum' }}, stick: {{ radius: 0.18 }} }}
        );
        viewer.zoomTo();
        viewer.render();
      }}
    </script>
  </body>
</html>
"""


def build_compare_structure_viewer_html(
    left_structure_text: str,
    left_format: str,
    left_label: str,
    right_structure_text: str,
    right_format: str,
    right_label: str,
) -> str:
    escaped_left_structure = json.dumps(left_structure_text)
    escaped_left_format = json.dumps(left_format)
    escaped_left_label = json.dumps(left_label)
    escaped_right_structure = json.dumps(right_structure_text)
    escaped_right_format = json.dumps(right_format)
    escaped_right_label = json.dumps(right_label)
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <style>
      html, body {{
        margin: 0;
        width: 100%;
        height: 100%;
        background: #0b0f14;
        overflow: hidden;
        color: #dbe7f5;
        font-family: Inter, system-ui, sans-serif;
      }}
      .shell {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        width: 100%;
        height: 100%;
        padding: 8px;
        box-sizing: border-box;
      }}
      .pane {{
        position: relative;
        min-height: 520px;
        border: 1px solid rgba(120, 160, 200, 0.2);
        border-radius: 12px;
        overflow: hidden;
        background: #0b0f14;
      }}
      .viewer {{
        width: 100%;
        height: 100%;
      }}
      .hud {{
        position: absolute;
        top: 12px;
        left: 12px;
        z-index: 10;
        font-size: 12px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        background: rgba(11, 15, 20, 0.72);
        border: 1px solid rgba(120, 160, 200, 0.28);
        border-radius: 10px;
        padding: 8px 10px;
        backdrop-filter: blur(12px);
      }}
    </style>
    <script src=\"https://3dmol.org/build/3Dmol-min.js\"></script>
  </head>
  <body>
    <div class=\"shell\">
      <div class=\"pane\">
        <div class=\"hud\">Compare structures · left · <span id=\"left-label\"></span></div>
        <div id=\"left-viewer\" class=\"viewer\"></div>
      </div>
      <div class=\"pane\">
        <div class=\"hud\">Compare structures · right · <span id=\"right-label\"></span></div>
        <div id=\"right-viewer\" class=\"viewer\"></div>
      </div>
    </div>
    <script>
      const leftStructureText = {escaped_left_structure};
      const rightStructureText = {escaped_right_structure};
      document.getElementById("left-label").textContent = {escaped_left_label};
      document.getElementById("right-label").textContent = {escaped_right_label};
      if (!window.$3Dmol) {{
        const fallbackHtml =
          '<div style="color:#ff9b9b;padding:16px;">' +
          '3Dmol.js failed to load.</div>';
        document.getElementById("left-viewer").innerHTML = fallbackHtml;
        document.getElementById("right-viewer").innerHTML = fallbackHtml;
      }} else {{
        const leftHost = document.getElementById("left-viewer");
        const rightHost = document.getElementById("right-viewer");
        const leftViewer = $3Dmol.createViewer(
          leftHost,
          {{ backgroundColor: '#0b0f14' }}
        );
        leftViewer.addModel(leftStructureText, {escaped_left_format});
        leftViewer.setStyle(
          {{}},
          {{ cartoon: {{ color: 'spectrum' }}, stick: {{ radius: 0.18 }} }}
        );
        leftViewer.zoomTo();
        leftViewer.render();
        const rightViewer = $3Dmol.createViewer(
          rightHost,
          {{ backgroundColor: '#0b0f14' }}
        );
        rightViewer.addModel(rightStructureText, {escaped_right_format});
        rightViewer.setStyle(
          {{}},
          {{ cartoon: {{ color: 'spectrum' }}, stick: {{ radius: 0.18 }} }}
        );
        rightViewer.zoomTo();
        rightViewer.render();
      }}
    </script>
  </body>
</html>
"""
