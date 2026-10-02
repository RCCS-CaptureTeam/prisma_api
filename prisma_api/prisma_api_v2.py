"""
PrISMa API v2 client wrappers.

Mirrors the v2 REST surface documented in
integration/prisma-v2/prisma_cloud_apis_v2/api_v2_examples.md

All methods authenticate using the same API key as the v1 client.
List endpoints return pandas DataFrames by default; set
``return_format='json'`` for raw list-of-dicts output instead.

Usage:
    import prisma_api
    api = prisma_api.init()        # standard v1 init
    api.v2.get_isotherm(mof='ABEXEM', molecule='CO2')
"""

from __future__ import annotations

import pandas as pd
import requests
from typing import Any
from pathlib import Path
from urllib.parse import urlencode
import warnings
import copy
import json
from collections import Counter
import re
import math
import subprocess
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit


_BASE_PROD = "https://prisma-platform.org/api/v2"
_DEFAULT_BUNDLE = object()
_DEFAULT_UPLOAD_TIMEOUT = 120

# AutoPrism table wrappers: method name -> (endpoint, wrapper key in the
# collection payload). The wrapper key is also accepted by the single-table
# upserts, e.g. ``{"zeopp_metrics": [...]}``.
_AUTOPRISM_TABLES = {
    "upsert_adsorption_singlepoint": ("/adsorption-singlepoint/", "adsorption_singlepoints"),
    "upsert_heat_capacity": ("/heat-capacity/", "heat_capacities"),
    "upsert_isotherm_h2": ("/isotherm-h2/", "isotherm_H2s"),
    "upsert_mofchecker": ("/mofchecker/", "mofchecker"),
    "upsert_zeopp_metrics": ("/zeopp-metrics/", "zeopp_metrics"),
}

# Material bundle sections, in the order the API emits them. Every section is a
# list except ``mof_h2``, which is a single object or None.
_BUNDLE_SECTIONS = (
    "cifs", "isotherms", "water_kpis", "carbon_zeopp",
    "carbon_zeopp_experimental", "adsorption_singlepoint", "heat_capacity",
    "isotherm_h2", "mofchecker", "zeopp_metrics", "mof_h2", "h2_results",
)
# Server-side hard cap; over this the bundle endpoint returns 400 rather
# than truncating.
_BUNDLE_MAX_MATERIALS = 200
# Sections the bundle upsert endpoint writes. The rest are read-only there and
# have their own dedicated PUT endpoints; an empty one is a no-op, a populated
# one is an error.
_BUNDLE_WRITABLE_SECTIONS = (
    "cifs", "isotherms", "water_kpis", "carbon_zeopp",
    "carbon_zeopp_experimental", "zeopp_metrics", "mof_h2", "h2_results",
)
_BUNDLE_READONLY_SECTIONS = {
    "adsorption_singlepoint": "upsert_adsorption_singlepoint",
    "heat_capacity": "upsert_heat_capacity",
    "isotherm_h2": "upsert_isotherm_h2",
    "mofchecker": "upsert_mofchecker",
}
# Read-bundle keys with no write meaning — dropped silently by the endpoint.
_BUNDLE_IGNORED_KEYS = ("_schema", "sections", "counts")


class PrismaAPIv2:
    """
    Thin wrapper around the PrISMa v2 REST endpoints.
    Instantiated automatically as ``api.v2`` by the v1 prisma_api class.
    """

    def __init__(self, key: str, dev: bool = False, dev_host_port: str = "",
                 return_format: str = "json",
                 upload_timeout: int = _DEFAULT_UPLOAD_TIMEOUT):
        self._key = key
        self._dev = dev
        self._dev_host_port = dev_host_port
        self._return_format = return_format  # 'dataframe' | 'json'
        # Default timeout (seconds) for PUT upserts; override per call with
        # ``timeout=`` on the upsert methods that accept it.
        self.upload_timeout = upload_timeout

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        if self._dev:
            return f"http://localhost:{self._dev_host_port}/api/v2"
        return _BASE_PROD

    def set_return_format(self, fmt: str) -> None:
        """
        Set the output format for all list endpoints.

        Args:
            fmt: ``'dataframe'`` (default) — return ``pd.DataFrame``.
                 ``'json'``      — return a plain ``list[dict]``.
        """
        if fmt not in ("dataframe", "json"):
            raise ValueError("return_format must be 'dataframe' or 'json'")
        self._return_format = fmt

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        """Absolute URL for a v2 path, honouring dev mode."""
        return (
            f"http://localhost:{self._dev_host_port}/api/v2{path}"
            if self._dev
            else f"{_BASE_PROD}{path}"
        )

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET request to the v2 API."""
        resp = requests.get(self._url(path), params=params,
                            headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict | list, timeout: int = 120) -> Any:
        """POST request to the v2 API."""
        resp = requests.post(self._url(path), json=data,
                             headers=self._headers(), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _request_bytes(self, path: str, params: dict, use_post: bool = False,
                       timeout: int = 300) -> requests.Response:
        """
        Fetch a binary response (e.g. ``output=zip``) without decoding it.

        Returns the raw ``requests.Response`` so callers keep ``Content-Type``
        and ``Content-Disposition``.
        """
        if use_post:
            resp = requests.post(self._url(path), json=params,
                                 headers=self._headers(), timeout=timeout)
        else:
            resp = requests.get(self._url(path), params=params,
                                headers=self._headers(), timeout=timeout)
        resp.raise_for_status()
        return resp

    def _send(self, method: str, path: str, params: dict | None = None,
              json_body: Any = None, files: dict | None = None,
              timeout: int = 120) -> requests.Response:
        """
        Issue a request and return the raw response.

        Used where the caller needs the status code (207 partial success) or
        sends multipart form data — for which the JSON ``Content-Type`` header
        must be omitted so requests can set the multipart boundary.
        """
        headers = {"X-API-Key": self._key} if files else self._headers()
        resp = requests.request(method.upper(), self._url(path), params=params,
                                json=json_body, files=files, headers=headers,
                                timeout=timeout)
        resp.raise_for_status()
        return resp

    def _put(self, path: str, data: list, timeout: int | None = None) -> dict:
        """PUT (upsert) request. NaN/inf and numpy values are made JSON-safe."""
        resp = requests.put(self._url(path), json=_json_safe(data),
                            headers=self._headers(),
                            timeout=timeout or self.upload_timeout)
        resp.raise_for_status()
        return resp.json()

    def _to_df(self, response: Any, key: str = "results") -> "pd.DataFrame | list":
        """Convert a list-endpoint response envelope to a DataFrame or list of dicts."""
        records = response.get(key, response) if isinstance(response, dict) else response
        records = records or []
        if self._return_format == "json":
            return records
        return pd.DataFrame(records) if records else pd.DataFrame()

    def _resolve_cif_url_df(self, data: "pd.DataFrame | list") -> "pd.DataFrame | list":
        """Prepend the base URL to any relative cif_url values in a DataFrame or list of dicts."""
        base = self._base_url().rstrip("/").rsplit("/api/v2", 1)[0]
        if isinstance(data, pd.DataFrame):
            if "cif_url" not in data.columns:
                return data
            data = data.copy()
            data["cif_url"] = data["cif_url"].apply(
                lambda v: f"{base}{v}" if isinstance(v, str) and v.startswith("/") else v
            )
            return data
        # list of dicts
        return [
            {**r, "cif_url": f"{base}{r['cif_url']}"}
            if isinstance(r.get("cif_url"), str) and r["cif_url"].startswith("/")
            else r
            for r in data
        ]

    def _resolve_cif_url_dict(self, d: dict) -> dict:
        """Prepend the base URL to a relative cif_url value in a detail dict."""
        if isinstance(d.get("cif_url"), str) and d["cif_url"].startswith("/"):
            base = self._base_url().rstrip("/").rsplit("/api/v2", 1)[0]
            d = {**d, "cif_url": f"{base}{d['cif_url']}"}
        return d

    def _parse_cif_text(self, cif_text: str) -> dict[str, Any]:
        """Parse CIF text into a compact structured dict for notebook-friendly use."""
        lines = cif_text.splitlines()
        fields: dict[str, str] = {}
        for line in lines:
            s = line.strip()
            if not s or not s.startswith("_") or " " not in s:
                continue
            key, value = s.split(None, 1)
            fields[key] = value.strip()

        return {
            "line_count": len(lines),
            "field_count": len(fields),
            "fields": fields,
            "preview": lines[:20],
            "raw": cif_text,
        }

    def _coerce_scalar(self, value: Any) -> Any:
        """Best-effort conversion of scalar API values to native Python types."""
        if not isinstance(value, str):
            return value

        text = value.strip()
        if text == "":
            return value

        lowered = text.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

        # Strict integer parsing first to avoid converting floats like '1.0' to int.
        if re.fullmatch(r"[+-]?\d+", text):
            try:
                return int(text)
            except ValueError:
                pass

        # Support decimal/scientific notation.
        if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?", text):
            try:
                return float(text)
            except ValueError:
                pass

        # Parse JSON list/dict payloads often returned as strings.
        if (text.startswith("[") and text.endswith("]")) or (
            text.startswith("{") and text.endswith("}")
        ):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, (list, dict)):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Parse ISO-ish datetime strings.
        if any(sep in text for sep in ("-", "T", ":")):
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                pass

        return value

    def _coerce_scope_types(self, payload: Any) -> Any:
        """Normalize scope endpoint payload values to useful runtime types."""
        if isinstance(payload, dict):
            return {k: self._coerce_scalar(v) for k, v in payload.items()}

        if isinstance(payload, list):
            if payload and all(isinstance(item, dict) for item in payload):
                return [{k: self._coerce_scalar(v) for k, v in row.items()} for row in payload]
            return [self._coerce_scalar(v) for v in payload]

        if isinstance(payload, pd.DataFrame):
            df = payload.copy()
            for col in df.columns:
                df[col] = df[col].map(self._coerce_scalar)
                non_null = df[col].dropna()
                if len(non_null) > 0 and non_null.map(lambda v: isinstance(v, datetime)).all():
                    df[col] = pd.to_datetime(df[col], errors="coerce")
            return df

        return payload

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """GET /api/v2/health/ — returns status dict."""
        return self._get("/health/")

    def get_flowsheet(self, name: str = "dac_min") -> dict:
        """
        GET /api/v2/flowsheets/{name}/

        Returns the DB-normalised flowsheet payload for the named object.
        """
        return self._get(f"/flowsheets/{name}/")

    def get_flowsheet_bundle(self, name: str = "dac_min") -> dict:
        """
        GET /api/v2/flowsheets/{name}/bundle/

        Returns the bundled flowsheet payload for the named object.
        """
        return self._get(f"/flowsheets/{name}/bundle/")

    def upsert_flowsheets(
        self,
        flowsheets: pd.DataFrame | list[dict],
        screening_analysis_name: str | None = None,
        on_exists: str = "append",
        appendix: str = "_v4",
    ) -> dict:
        """
        PUT /api/v2/flowsheets/upsert/

        Modes:
            * append (default): ``?on_exists=append&appendix=<suffix>``
            * overwrite:        ``?on_exists=overwrite``

        Args:
            flowsheets: DataFrame or list of dict payload records.
            screening_analysis_name: Optional analysis identifier forwarded to the
                API for upsert attribution/routing. For production uploads this
                should be set and should match one of the nested screening
                analysis names returned by ``list_case_studies()``.
            on_exists:  Conflict mode; one of ``'append'`` or ``'overwrite'``.
            appendix:   Suffix used only in append mode (default ``'_v4'``).

        Returns:
            API response dict.
        """
        if on_exists not in ("append", "overwrite"):
            raise ValueError("on_exists must be 'append' or 'overwrite'")

        records = (
            flowsheets.to_dict(orient="records")
            if isinstance(flowsheets, pd.DataFrame)
            else flowsheets
        )
        cleaned_screening_name = (screening_analysis_name or "").strip()

        query_params: dict[str, str] = (
            {"on_exists": "overwrite"}
            if on_exists == "overwrite"
            else {"on_exists": "append", "appendix": appendix}
        )

        if cleaned_screening_name:
            query_params["screening_analysis_name"] = cleaned_screening_name
        else:
            warnings.warn(
                "Uploading flowsheets without screening_analysis_name is intended "
                "for experimentation only and is not recommended for production. "
                "Provide screening_analysis_name matching one of the nested "
                "screening analysis names returned by list_case_studies().",
                UserWarning,
                stacklevel=2,
            )

        query = urlencode(query_params)
        path = f"/flowsheets/upsert/?{query}"

        return self._put(path, records)

    # ── Catalog ───────────────────────────────────────────────────────────────

    def list_materials(self, name: str | None = None,
                       limit: int = 10_000) -> pd.DataFrame:
        """
        GET /api/v2/materials/

        Fetches all matching materials using an internal paginate-in-loop
        strategy (page size 500) so that result sets larger than the server
        default are returned transparently.

        Args:
            name:   Case-insensitive substring filter on material name.
            limit:  Maximum total records to return across all pages
                    (default 10 000).  Pass ``limit=0`` for no cap.

        Returns:
            List of materials (format controlled by ``set_return_format``).
            Each record includes the following fields:

            * ``id`` / ``name`` / ``cif_url``
            * ``material_id`` — same as ``name``, used as the slug identifier
            * ``material_backend`` — always ``'tabular_binary_iast'``
            * ``gas_basis`` — ``['CO2','N2','H2O']`` if Water KPI data exist, else ``['CO2','N2']``
            * ``supports_humid_ternary`` — ``None`` (reserved)
            * ``tags`` — ``[]`` (reserved)
            * ``provenance`` — always ``'tabular_material'``
            * ``lifecycle`` — ``{"object_kind": "catalog", "version": "legacy.v1"}``
            * ``metadata`` — ``{"django_tables": [...], "source": "live_db"}``
            * ``source_path`` — ``None`` (reserved)
        """
        page_size = 500
        all_records: list = []
        offset = 0
        while True:
            fetch = page_size if (limit == 0) else min(page_size, limit - len(all_records))
            params = _compact(name=name, limit=fetch, offset=offset)
            raw = self._get("/materials/", params)
            page: list = raw.get("results", raw) if isinstance(raw, dict) else (raw or [])
            all_records.extend(page)
            if len(page) < fetch:
                break
            offset += fetch
            if limit != 0 and len(all_records) >= limit:
                break
        server = self._base_url().rsplit("/api/v2", 1)[0]
        print(f"{len(all_records)} materials loaded from {server}")
        return self._resolve_cif_url_df(self._to_df({"results": all_records}))

    def list_cifs(self, tag: str | None = None) -> list[str]:
        """
        GET /api/v2/list_cifs/

        List CIF-backed MOF records.

        Args:
            tag: Optional tag to filter CIFs by. If omitted, all CIFs are returned.

        Returns:
            List of MOF names matching ``tag``.
        """
        response = self._get("/cifs/", _compact(tag=tag))
        records = response.get("results", response) if isinstance(response, dict) else response
        records = records or []
        return [r["mof"] if isinstance(r, dict) else r for r in records]

    def get_cifs(self, mof: str | list[str],
                 structured: bool = True,
                 pandas: bool = True,
                 save_dir: str | None = None) -> dict | list[dict] | requests.Response | list[requests.Response] | str | list[str]:
        """
        GET /api/v2/cifs/files/

        Fetch CIF payload(s) for one or more MOF names.

        Args:
            mof: One MOF name (str) or list of MOF names.
            structured: Request structured JSON response from the API.
                        Defaults to ``True``.
            pandas: Convert pandas-suitable structured fields to
                    ``pd.DataFrame`` when ``structured=True``.
                    Defaults to ``True``.
            save_dir: Optional directory to save downloaded CIF attachment(s).
                      Only used when ``structured=False``.

        Returns:
            If ``structured=True``: nested dict for single MOF or list of nested
            dicts for multiple MOFs, with null-valued keys removed and tabular
            list-of-dict sections converted to ``pd.DataFrame``.
            If ``structured=False``: streamed CIF response(s), or saved path(s)
            when ``save_dir`` is provided.
        """
        if structured and save_dir is not None:
            raise ValueError("save_dir is only supported when structured=False.")

        output_dir = Path(save_dir).expanduser() if save_dir is not None else None
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)

        # Field-aware conversion keeps nested structures readable while
        # still promoting genuinely tabular sections to DataFrames.
        _TABULAR_FIELD_NAMES = {
            "tags",
            "elements",
            "citations",
            "references",
            "authors",
            "atom_site",
            "atom_sites",
            "symmetry_operations",
            "symmetry_equiv_pos",
            "bonds",
            "angles",
            "torsions",
            "contacts",
            "void_fractions",
            "channels",
            "coordination",
            "topology",
        }

        def _is_scalar(value: Any) -> bool:
            return isinstance(value, (str, int, float, bool)) or value is None

        def _looks_like_tabular_records(records: list[dict]) -> bool:
            if not records:
                return False
            keys = [set(r.keys()) for r in records if isinstance(r, dict)]
            if len(keys) != len(records):
                return False
            shared = set.intersection(*keys) if keys else set()
            if not shared:
                return False
            scalar_hits = 0
            total = 0
            for row in records:
                for value in row.values():
                    total += 1
                    if _is_scalar(value):
                        scalar_hits += 1
            return total > 0 and (scalar_hits / total) >= 0.8

        def _should_convert_to_df(path: tuple[str, ...], records: list[dict]) -> bool:
            if not pandas:
                return False
            if not _looks_like_tabular_records(records):
                return False
            field_name = path[-1].lower() if path else ""
            if field_name in {"atoms", "geom_bonds", "commit_history"}:
                return True
            if field_name in _TABULAR_FIELD_NAMES:
                return True
            if field_name.endswith(("_table", "_rows", "_records", "_sites")):
                return True
            if field_name.startswith(("atoms_", "bond_", "symmetry_", "cell_")):
                return True
            return False

        def _clean_and_convert(value: Any, path: tuple[str, ...] = ()) -> Any:
            if isinstance(value, dict):
                cleaned = {
                    k: _clean_and_convert(v, path + (k,))
                    for k, v in value.items()
                    if v is not None
                }
                return cleaned
            if isinstance(value, list):
                cleaned_list = [_clean_and_convert(v, path) for v in value]
                if cleaned_list and all(isinstance(x, dict) for x in cleaned_list):
                    if _should_convert_to_df(path, cleaned_list):
                        return pd.DataFrame(cleaned_list)
                return cleaned_list
            return value

        def _extract_filename(resp: requests.Response, fallback_mof: str) -> str:
            cd = resp.headers.get("Content-Disposition", "")
            marker = "filename="
            if marker in cd:
                filename = cd.split(marker, 1)[1].strip().strip('"')
                if filename:
                    return filename
            return f"{fallback_mof}.cif"

        def _one(mof_name: str) -> dict | requests.Response | str:
            if not isinstance(mof_name, str) or not mof_name.strip():
                raise TypeError("Each 'mof' value must be a non-empty string.")
            mof_name = mof_name.strip()
            url = f"{self._base_url()}/cifs/files/"
            resp = requests.get(
                url,
                params={"mof": mof_name, "structured": str(structured).lower()},
                headers=self._headers(),
                timeout=120,
                stream=not structured,
            )
            resp.raise_for_status()

            if structured:
                return _clean_and_convert(resp.json())

            if output_dir is not None:
                filename = _extract_filename(resp, mof_name)
                target = output_dir / filename
                with target.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                resp.close()
                return str(target)
            return resp

        if isinstance(mof, str):
            return _one(mof)
        if isinstance(mof, list):
            return [_one(name) for name in mof]
        raise TypeError("'mof' must be a string or list of strings.")

    def get_material(
        self,
        material_id: int | None = None,
        *,
        name: str | list[str] | None = None,
        bundle: list[str] | None | object = _DEFAULT_BUNDLE,
        sim_or_exp: str | None = None,
        good_structure: bool | None = None,
        limit: int = 500,
        offset: int = 0,
        include_cif_text: bool = False,
        cif_timeout: int = 60,
    ) -> dict | list[dict]:
        """
        GET /api/v2/materials/{material_id}/

        Return one or more material detail records, optionally bundled with
        related isotherms / Zeo++ / water KPIs / CIF metadata.

        Resolution modes:
            * ``material_id`` (int): fetch one material by PK.
            * ``name`` (str): fetch one material by name match resolution.
            * ``name`` (list[str]): fetch many materials, one per name.

        Bundle behavior:
            * omitted ``bundle``: include all bundles
              ``['isotherms', 'zeopp', 'water_kpis', 'cif']``
            * ``bundle=None``: include no additional bundled data (root only)
            * explicit list: include only requested bundle sections.

        Returns:
            dict for a single material lookup; list[dict] for ``name=list[str]``.
        """

        def _resolve_one_by_name(material_name: str) -> dict:
            matches = self._get(
                "/materials/",
                _compact(name=material_name, limit=50),
            ).get("results", [])
            exact_matches = [m for m in matches if m.get("name") == material_name]
            candidates = exact_matches if exact_matches else matches
            if len(candidates) > 1:
                names = [m.get("name") for m in candidates]
                raise ValueError(
                    f"'{material_name}' matched {len(candidates)} materials: {names}. "
                    "Use a more specific name."
                )
            if not candidates:
                raise ValueError(f"No material matched '{material_name}'.")
            return candidates[0]

        def _as_records_local(result: Any) -> list[dict]:
            if isinstance(result, pd.DataFrame):
                return result.to_dict(orient="records")
            if isinstance(result, list):
                return result
            return []

        def _resolve_bundle_list(bundle_arg: list[str] | None | object) -> list[str]:
            if bundle_arg is _DEFAULT_BUNDLE:
                selected = ["isotherms", "zeopp", "water_kpis", "cif"]
            elif bundle_arg is None:
                selected = []
            else:
                selected = [str(b).strip().lower() for b in bundle_arg]
            allowed = {"isotherms", "zeopp", "water_kpis", "cif"}
            unknown = [b for b in selected if b not in allowed]
            if unknown:
                raise ValueError(
                    f"Unknown bundle key(s): {unknown}. "
                    "Allowed: ['isotherms','zeopp','water_kpis','cif']"
                )
            return selected

        def _build_material_payload(base_record: dict, selected_bundles: list[str]) -> dict:
            root = self._resolve_cif_url_dict(self._get(f"/materials/{int(base_record['id'])}/"))
            out = dict(root)
            mof_name = root.get("name")

            if "isotherms" in selected_bundles:
                out["isotherms"] = _as_records_local(self.get_isotherm(
                    mof=mof_name,
                    sim_or_exp=sim_or_exp,
                    good_structure=good_structure,
                    limit=limit,
                    offset=offset,
                ))

            if "zeopp" in selected_bundles:
                zeopp_sim = _as_records_local(self.get_carbon_zeopp(
                    mof=mof_name,
                    good_structure=good_structure,
                    limit=limit,
                    offset=offset,
                ))
                zeopp_exp = _as_records_local(self.get_carbon_zeopp_experimental(
                    mof=mof_name,
                    limit=limit,
                    offset=offset,
                ))
                out["zeopp"] = [
                    {**r, "_zeopp_source": "simulated"} for r in zeopp_sim
                ] + [
                    {**r, "_zeopp_source": "experimental"} for r in zeopp_exp
                ]

            if "water_kpis" in selected_bundles:
                out["water_kpis"] = _as_records_local(self.get_water_kpis(
                    mof=mof_name,
                    sim_or_exp=sim_or_exp,
                    good_structure=good_structure,
                    limit=limit,
                    offset=offset,
                ))

            if "cif" in selected_bundles:
                material_psdi = self.get_material_psdi(int(base_record["id"]))
                cif_url = material_psdi.get("cif_url") or root.get("cif_url")
                cif_filename = material_psdi.get("cif_filename")
                if not cif_filename and isinstance(cif_url, str) and cif_url:
                    cif_filename = cif_url.rsplit("/", 1)[-1]

                cif_payload: dict[str, Any] = {
                    "url": cif_url,
                    "filename": cif_filename,
                }
                if include_cif_text and isinstance(cif_url, str) and cif_url:
                    resp = requests.get(cif_url, headers=self._headers(), timeout=cif_timeout)
                    resp.raise_for_status()
                    cif_payload["text"] = self._parse_cif_text(resp.text)
                out["cif"] = cif_payload

            return out

        if (material_id is None) == (name is None):
            raise ValueError("Provide exactly one of material_id or name")

        selected_bundles = _resolve_bundle_list(bundle)

        if material_id is not None:
            base = {"id": int(material_id)}
            return _build_material_payload(base, selected_bundles)

        if isinstance(name, str):
            base = _resolve_one_by_name(name)
            return _build_material_payload(base, selected_bundles)

        if isinstance(name, list):
            if not all(isinstance(n, str) for n in name):
                raise TypeError("name list must contain only strings")
            bases = [_resolve_one_by_name(n) for n in name]
            return [_build_material_payload(b, selected_bundles) for b in bases]

        raise TypeError("name must be a string or list of strings")

    def get_materials_psdi(self, name: str | None = None,
                           limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/materials-psdi/

        Extended material list including full crystallographic and PSDI fields:
        chemical formulae, SMILES, space group, cell geometry, CIF URL/filename.

        Args:
            name:   Case-insensitive substring filter on material name.
            limit:  Max records to return (default 500).
            offset: Pagination offset.

        Returns:
            DataFrame with one row per material.
        """
        params = _compact(name=name, limit=limit, offset=offset)
        return self._resolve_cif_url_df(self._to_df(self._get("/materials-psdi/", params)))

    def get_material_psdi(self, material_id: int) -> dict:
        """
        GET /api/v2/materials-psdi/{material_id}/

        Full extended MOF record: all crystallographic fields, CIF URL/filename,
        linker/node chemistry (SMILES, formulae, PubChem pipeline outputs),
        and element composition.

        Args:
            material_id: Integer PK of the material.

        Returns:
            dict with all PSDI fields plus nested 'elements' list.
        """
        return self._resolve_cif_url_dict(self._get(f"/materials-psdi/{material_id}/"))

    def get_material_property_bundle(self, mof: str | None = None,
                                     sim_or_exp: str | None = None,
                                     good_structure: bool | None = None,
                                     limit: int = 500,
                                     offset: int = 0,
                                     query: dict[str, dict[str, Any]] | None = None,
                                     name: str | None = None) -> dict:
        """
        Fetch all science data for a given MOF in a single call.

        Aggregates isotherms, simulated Zeo++, experimental Zeo++ and
        water KPIs into one dict, applying consistent filters across all
        four sub-queries.

        Args:
            mof:            MOF name (substring match applied to all sub-queries).
                            Kept for backward compatibility; ``name`` is an alias.
            sim_or_exp:     'sim' or 'exp' filter for isotherms and water KPIs.
            good_structure: Good-structure filter for isotherms, water KPIs
                            and simulated Zeo++.
            limit:          Max records per sub-query (default 500).
            offset:         Pagination offset for all sub-queries.
            query:          Optional advanced parameter map for endpoint-specific
                            filtering. Supported keys:
                            ``materials``, ``isotherms``, ``zeopp_simulated``,
                            ``zeopp_experimental``, ``water_kpis``, and
                            ``common``.

                            ``common`` is merged into all four science endpoints.
                            Endpoint-specific keys override defaults.

        Returns:
            dict with keys:
                'isotherms'          – isotherm records
                'zeopp_simulated'    – simulated Zeo++ records
                'zeopp_experimental' – experimental Zeo++ records
                'water_kpis'         – water KPI records

        Raises:
            ValueError: if the name matches more than one material — use an
                exact name or a more specific substring.
        """
        if mof is None and name is None:
            raise TypeError("Provide either 'mof' or 'name'.")
        if mof is not None and name is not None:
            raise TypeError("Provide only one of 'mof' or 'name', not both.")
        mof = name if mof is None else mof

        if query is not None and not isinstance(query, dict):
            raise TypeError("query must be a dict[str, dict] or None")

        query = query or {}

        common_filters = query.get("common", {}) or {}
        if not isinstance(common_filters, dict):
            raise TypeError("query['common'] must be a dict when provided")

        def _merge_filters(defaults: dict[str, Any], key: str) -> dict[str, Any]:
            endpoint_filters = query.get(key, {}) or {}
            if not isinstance(endpoint_filters, dict):
                raise TypeError(f"query['{key}'] must be a dict when provided")
            merged = {**defaults, **common_filters, **endpoint_filters}
            return _compact(**merged)

        matches = self._get(
            "/materials/",
            _merge_filters({"name": mof, "limit": 50}, "materials"),
        ).get("results", [])
        # The API name filter is a substring match — narrow to exact matches only
        exact_matches = [m for m in matches if m["name"] == mof]
        # Fall back to substring matches only if there is no exact match
        # (supports callers who intentionally pass a substring)
        candidates = exact_matches if exact_matches else matches
        if len(candidates) > 1:
            names = [m["name"] for m in candidates]
            raise ValueError(
                f"'{mof}' matched {len(candidates)} materials: {names}. "
                "Use a more specific name."
            )
        true_name = candidates[0]["name"] if candidates else mof

        # Fields in water_kpis that carry DB integer PKs for MOF / Molecule
        # (capitalised keys) duplicate the human-readable 'mof' / 'molecule'
        # string fields and are stripped here to keep the bundle clean.
        _WK_DROP = frozenset({"MOF", "Molecule"})

        def _drop_wk_id_fields(records):
            if isinstance(records, list):
                return [{k: v for k, v in r.items() if k not in _WK_DROP} for r in records]
            import pandas as pd
            if isinstance(records, pd.DataFrame):
                return records.drop(columns=[c for c in _WK_DROP if c in records.columns])
            return records

        good_structure_q = None if good_structure is None else str(good_structure).lower()

        bundle = {
            "isotherms": self._to_df(self._get(
                "/isotherms/",
                _merge_filters({
                    "mof": mof,
                    "sim_or_exp": sim_or_exp,
                    "good_structure": good_structure_q,
                    "limit": limit,
                    "offset": offset,
                }, "isotherms"),
            )),
            "zeopp_simulated": self._to_df(self._get(
                "/carbon-zeopp/",
                _merge_filters({
                    "mof": mof,
                    "good_structure": good_structure_q,
                    "limit": limit,
                    "offset": offset,
                }, "zeopp_simulated"),
            )),
            "zeopp_experimental": self._to_df(self._get(
                "/carbon-zeopp-experimental/",
                _merge_filters({
                    "mof": mof,
                    "limit": limit,
                    "offset": offset,
                }, "zeopp_experimental"),
            )),
            "water_kpis": _drop_wk_id_fields(self._to_df(self._get(
                "/water-kpis/",
                _merge_filters({
                    "mof": mof,
                    "sim_or_exp": sim_or_exp,
                    "good_structure": good_structure_q,
                    "limit": limit,
                    "offset": offset,
                }, "water_kpis"),
            ))),
        }
        label = true_name if true_name == mof else f"{true_name} (matched from partial string: '{mof}')"
        print(f"Property bundle for '{label}':")
        for key, val in bundle.items():
            print(f"  {key:25s}: {len(val)} records")
        return bundle

    def get_material_bundle(
        self,
        mof: str,
        sim_or_exp: str | None = None,
        good_structure: bool | None = None,
        limit: int = 500,
        offset: int = 0,
        query: dict[str, dict[str, Any]] | None = None,
        include_cif: bool = False,
        include_cif_text: bool = False,
        cif_timeout: int = 60,
    ) -> dict:
        """
        Fetch material detail, PSDI detail, and science bundle in one call flow.

        Args:
            mof:              MOF name.
            sim_or_exp:       Optional 'sim' or 'exp' filter for bundle endpoints.
            good_structure:   Optional structure-quality filter for bundle endpoints.
            limit:            Max records per bundle endpoint.
            offset:           Pagination offset for bundle endpoints.
            query:            Advanced per-endpoint filters forwarded to
                              ``get_material_property_bundle``.
            include_cif:      If True, include CIF metadata (URL/filename).
            include_cif_text: If True, download and include CIF text content.
            cif_timeout:      Timeout in seconds for CIF download.

        Returns:
            dict with keys:
                'material'        – output of ``get_material``
                'material_psdi'   – output of ``get_material_psdi``
                'property_bundle' – output of ``get_material_property_bundle``
                'cif'             – optional CIF metadata plus structured text dict

        Raises:
            ValueError: if the name resolves to multiple materials or no material.
        """
        matches = self._get(
            "/materials/",
            _compact(name=mof, limit=50),
        ).get("results", [])

        exact_matches = [m for m in matches if m.get("name") == mof]
        candidates = exact_matches if exact_matches else matches
        if len(candidates) > 1:
            names = [m.get("name") for m in candidates]
            raise ValueError(
                f"'{mof}' matched {len(candidates)} materials: {names}. "
                "Use a more specific name."
            )
        if not candidates:
            raise ValueError(f"No material matched '{mof}'.")

        selected = candidates[0]
        material_id = int(selected["id"])
        true_name = selected.get("name", mof)

        material = self.get_material(material_id, bundle=None)
        material_psdi = self.get_material_psdi(material_id)
        property_bundle = self.get_material_property_bundle(
            true_name,
            sim_or_exp=sim_or_exp,
            good_structure=good_structure,
            limit=limit,
            offset=offset,
            query=query,
        )

        result: dict[str, Any] = {
            "material": material,
            "material_psdi": material_psdi,
            "property_bundle": property_bundle,
        }

        if include_cif:
            cif_url = material_psdi.get("cif_url") or material.get("cif_url")
            cif_filename = material_psdi.get("cif_filename")
            if not cif_filename and isinstance(cif_url, str) and cif_url:
                cif_filename = cif_url.rsplit("/", 1)[-1]

            cif_payload: dict[str, Any] = {
                "url": cif_url,
                "filename": cif_filename,
            }

            if include_cif_text and isinstance(cif_url, str) and cif_url:
                resp = requests.get(cif_url, headers=self._headers(), timeout=cif_timeout)
                resp.raise_for_status()
                cif_payload["text"] = self._parse_cif_text(resp.text)

            result["cif"] = cif_payload
        else:
            result["cif"] = None
        return result

    def get_material_bundles(
        self,
        names: str | list[str] | None = None,
        ids: int | list[int] | None = None,
        sections: str | list[str] | None = None,
        exclude: str | list[str] | None = None,
        include_cif_content: bool = False,
        match: str = "exact",
        output: str = "json",
        save_path: str | Path | None = None,
        use_post: bool = False,
        timeout: int = 300,
    ) -> dict | Path:
        """
        Fetch complete material bundles — every per-material section in one call.

        Wraps the server-side bundle endpoints, which return all twelve science
        sections for a material without the client fanning out across
        ``/isotherms/``, ``/water-kpis/``, ``/cifs/`` and the rest:

        * ``GET /api/v2/materials/{material_id}/bundle/`` — one material
        * ``GET /api/v2/materials/bundle/``               — many materials

        Args:
            names:   Material name, or list of names. A plain string returns
                     that material's bundle; a list returns the bulk envelope.
            ids:     Material id, or list of ids. A plain ``int`` returns that
                     material's bundle via the single-material route.
            sections: Section names to include (list or comma-separated string).
                     Default: all twelve.
            exclude: Section names to drop (list or comma-separated string).
            include_cif_content: Embed raw CIF text in ``cifs[].content``.
            match:   ``'exact'`` (default) or ``'contains'`` — applies to ``names``.
            output:  ``'json'`` (default) or ``'zip'``. ``'zip'`` downloads one
                     ``<name>.json`` per material plus a ``manifest.json``.
            save_path: Destination for ``output='zip'`` — a file path, or a
                     directory in which the server-supplied filename is used.
                     Defaults to the current working directory.
            use_post: Send the request as a POST with a JSON body instead of a
                     query string. Useful when a long name list would overflow
                     the URL.
            timeout: Request timeout in seconds (default 300, for large zips).

        Returns:
            * ``names`` given as a string (or ``ids`` as a plain int) —
              the single bundle dict::

                  {"_schema": "prisma_v2.material.bundle.v1",
                   "sections": [...], "material": {...},
                   "cifs": [...], "isotherms": [...], ..., "counts": {...}}

              Every section is a list except ``mof_h2``, which is a single
              object or ``None``. A section with no data is ``[]``; a section
              dropped via ``sections``/``exclude`` is absent entirely — read
              the response's ``sections`` key rather than assuming all twelve.

            * ``names``/``ids`` given as lists — the bulk envelope::

                  {"_schema": ..., "count": 2, "missing": ["NoSuchMaterial"],
                   "sections": [...], "results": [ {...}, {...} ]}

              ``missing`` is a partial-success signal, not an error: names and
              ids that matched nothing are listed there and the call still
              succeeds.

            * ``output='zip'`` — the ``Path`` the archive was written to.

        Raises:
            ValueError: on an unknown section name, an invalid ``match`` /
                ``output`` value, a non-integer id, no names or ids given, a
                zip request over the 200-material cap, or a single-material
                request that matched nothing (or, with ``match='contains'``,
                more than one material).
            requests.HTTPError: passed through from the API — 403 for a bad
                API key, 400 for a request the server rejects.

        Notes:
            Requests over 200 materials are split into batches of 200 (the
            server's hard cap, which it answers with a 400 rather than
            truncating) and the envelopes merged. ``output='zip'`` is a single
            request, so it is capped at 200.

        Examples:
            >>> api.v2.get_material_bundles('Zeolite_13X')['counts']
            {'cifs': 2, 'isotherms': 4, 'water_kpis': 7, ...}
            >>> bundle = api.v2.get_material_bundles(84368)   # by id
            >>> envelope = api.v2.get_material_bundles(['Zeolite_13X', 'ABEXEM'])
            >>> pd.DataFrame(envelope['results'][0]['isotherms'])
            >>> api.v2.get_material_bundles(['Zeolite_13X'], output='zip',
            ...                             save_path='bundles.zip')
        """
        if output not in ("json", "zip"):
            raise ValueError("output must be 'json' or 'zip'")
        if match not in ("exact", "contains"):
            raise ValueError("match must be 'exact' or 'contains'")

        # A bare int in `names` is accepted as an id, so `get_material_bundles(84368)`
        # does the obvious thing.
        if ids is None and isinstance(names, int) and not isinstance(names, bool):
            names, ids = None, names

        single_name = isinstance(names, str)
        single_id = isinstance(ids, int) and not isinstance(ids, bool)
        name_list = _as_material_names(names)
        id_list = _as_material_ids(ids)
        if not name_list and not id_list:
            raise ValueError(
                "Provide at least one material name (str or list[str]) or id."
            )

        # Section filters and the CIF switch are shared by both routes. Note the
        # download switch is `output=zip`, never `format=zip` — DRF reserves
        # `?format=` for content negotiation and 404s on an unknown value before
        # the view runs, so no `format` key is ever sent.
        base_params = _compact(
            sections=_join_sections(sections, "sections"),
            exclude=_join_sections(exclude, "exclude"),
            include_cif_content="true" if include_cif_content else None,
        )

        if output == "zip":
            total = len(name_list) + len(id_list)
            if total > _BUNDLE_MAX_MATERIALS:
                raise ValueError(
                    f"{total} materials requested; a single bundle request is "
                    f"capped at {_BUNDLE_MAX_MATERIALS}. Download the archive in "
                    "batches of 200 or fewer."
                )
            params = {**base_params, "output": "zip"}
            if name_list:
                params["names"], params["match"] = name_list, match
            if id_list:
                params["ids"] = id_list
            response = self._request_bytes(
                "/materials/bundle/",
                _bundle_post_body(params) if use_post else params,
                use_post=use_post,
                timeout=timeout,
            )
            return self._save_bundle_zip(response, save_path)

        # Single id and nothing else — the dedicated per-material route.
        if single_id and not name_list:
            return self._get(f"/materials/{id_list[0]}/bundle/", base_params or None)

        requested = [("ids", v) for v in id_list] + [("names", v) for v in name_list]
        results: list[dict] = []
        missing: list = []
        schema: str | None = None
        sections_returned: list | None = None

        for start in range(0, len(requested), _BUNDLE_MAX_MATERIALS):
            batch = requested[start:start + _BUNDLE_MAX_MATERIALS]
            batch_ids = [v for kind, v in batch if kind == "ids"]
            batch_names = [v for kind, v in batch if kind == "names"]
            params = dict(base_params)
            if batch_ids:
                params["ids"] = batch_ids
            if batch_names:
                params["names"], params["match"] = batch_names, match

            try:
                if use_post:
                    payload = self._post("/materials/bundle/",
                                         _bundle_post_body(params))
                else:
                    payload = self._get("/materials/bundle/", params)
            except requests.HTTPError as exc:
                # 404 on the bulk route means nothing in this batch matched —
                # the same signal as `missing`, so fold it in rather than
                # failing a request where other batches did match.
                if exc.response is None or exc.response.status_code != 404:
                    raise
                payload = {"missing": batch_names + [str(v) for v in batch_ids]}

            results.extend(payload.get("results") or [])
            missing.extend(payload.get("missing") or [])
            schema = schema or payload.get("_schema")
            if sections_returned is None:
                sections_returned = payload.get("sections")

        if single_name:
            if not results:
                raise ValueError(f"No material matched '{names}'.")
            if len(results) > 1:
                matched = [r.get("material", {}).get("name") for r in results]
                raise ValueError(
                    f"'{names}' matched {len(results)} materials: {matched}. "
                    "Use match='exact', or pass a list to fetch them all."
                )
            return results[0]

        server = self._base_url().rsplit("/api/v2", 1)[0]
        print(f"{len(results)} material bundle(s) loaded from {server}")
        if missing:
            print(f"  no match for: {missing}")
        return {
            "_schema": schema,
            "count": len(results),
            "missing": missing,
            "sections": sections_returned,
            "results": results,
        }

    def _save_bundle_zip(self, response: requests.Response,
                         save_path: str | Path | None) -> Path:
        """Write an ``output=zip`` bundle response to disk and return its path."""
        filename = _filename_from_disposition(
            response.headers.get("Content-Disposition")
        ) or "material_bundles.zip"
        path = Path(save_path) if save_path is not None else Path.cwd() / filename
        if path.is_dir():
            path = path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        print(f"{len(response.content):,} bytes written to {path}")
        return path

    def upsert_material_bundles(
        self,
        bundles: dict | list[dict],
        cif_files: str | Path | list | dict | None = None,
        create_materials: bool = True,
        strip_ids: bool = False,
        inline_cifs: bool = False,
        derive_cif_metadata: bool | str = True,
        tag_names: dict[int, str] | None = None,
        method: str | None = None,
        timeout: int = 300,
    ) -> dict:
        """
        Write complete material bundles back to the database.

        ``PUT|POST /api/v2/materials/bundle/upsert/`` — the write counterpart of
        :meth:`get_material_bundles`. It takes the *same document the read
        endpoint returns*, so a bundle can be read, edited and posted back
        unchanged: every row matches on its ``id`` and only the edited value
        moves. Computed fields (``_schema``, ``sections``, ``counts``,
        ``cif_url``, ``file_url``, ``mof``, …) are ignored by the server and
        can be left in place.

        Args:
            bundles: One bundle dict, or a list of them. Each is the read-bundle
                     shape: ``{"material": {...}, "cifs": [...],
                     "isotherms": [...], ...}``.
            cif_files: CIF file(s) to send alongside the payload. Either a path
                     (or list of paths) when upserting a single bundle, or a
                     ``{material name: path | [paths]}`` mapping. Each file is
                     attached to the ``cifs`` row whose ``filename`` it matches,
                     or appended as a new row.
            create_materials: Create a material the database does not have
                     (default ``True``). ``False`` makes an unknown name an error.
            strip_ids: Drop ``material.id`` and every per-row ``id`` so rows fall
                     back to their natural keys. Use when sending a bundle to a
                     *different* database than it was read from, where those ids
                     mean nothing. Keep it ``False`` for a round trip within one
                     database: a material can have several CIF rows sharing a
                     file name, and those are distinguishable only by ``id``.
            inline_cifs: Send CIF structures as ``cifs[].content`` in the JSON
                     body instead of as multipart file parts.
            derive_cif_metadata: Fill each ``cifs`` row's structural metadata —
                     formulae, cell lengths, angles, volume, symmetry and space
                     group — from the CIF text itself, so the row describes the
                     file being sent rather than whatever it carried before.
                     ``True`` (default) derives from every attached file and
                     from any row that already carries ``content``, overwriting
                     the row's own values; ``'fill'`` only fills keys that are
                     missing or ``None``; ``False`` sends the metadata as given.
                     Fields the file does not carry are left alone, and
                     ``material`` is never touched.
            tag_names: ``{tag id: tag name}`` map used to translate integer
                     ``water_kpis[].tags``. Tag ids are local to one database;
                     with ``strip_ids=True`` any untranslated integer tag raises
                     rather than failing upstream with ``Unknown tag id``.
            method:  ``'put'`` or ``'post'``. Defaults to ``'post'`` when files
                     are attached, ``'put'`` otherwise.
            timeout: Request timeout in seconds (default 300).

        Returns:
            The server's upsert report::

                {"_schema": "prisma_v2.material.bundle.upsert.v1",
                 "materials": 1,
                 "created": {},
                 "updated": {"cifs": 1, "isotherms": 2, ...},
                 "results": [{"material": {"id": 84368, "name": "Zeolite_13X",
                                           "created": false},
                              "created": {}, "updated": {...}}]}

            A 207 response (partial success) returns the same body with an
            ``errors: [{index, material, error}]`` list and raises a
            ``UserWarning``. Each bundle is applied in its own transaction, so a
            failed bundle changed nothing. Retry only the failed indices —
            re-sending the whole payload re-applies the bundles that succeeded.

        Raises:
            ValueError: on an unknown section name, a populated read-only
                section (``adsorption_singlepoint``, ``heat_capacity``,
                ``isotherm_h2``, ``mofchecker`` — each has its own upsert
                method), a bundle with no ``material``, a CIF row carrying both
                ``content`` and ``file``, an unmatched ``cif_files`` key, or an
                untranslated integer tag under ``strip_ids``.
            FileNotFoundError: a path in ``cif_files`` that does not exist.
            requests.HTTPError: passed through from the API — 403 for a bad API
                key, 400 for a body the server rejects.

        Notes:
            Nothing is ever deleted. Re-posting a payload with a row removed
            leaves that row in place.

        Examples:
            >>> bundle = api.v2.get_material_bundles('Zeolite_13X')
            >>> bundle['isotherms'][0]['T_ref_K'] = 298.15
            >>> api.v2.upsert_material_bundles(bundle)['updated']
            {'isotherms': 1}

            >>> # Same payload into a different database, with its CIF file
            >>> api.v2.upsert_material_bundles(
            ...     bundle, cif_files='Zeolite_13X.cif', strip_ids=True,
            ...     tag_names={2: 'MOFevaluator', 1: 'PrISMa V1'})

            >>> # Keep hand-edited row metadata, filling only what is missing
            >>> api.v2.upsert_material_bundles(
            ...     bundle, cif_files='Zeolite_13X.cif', derive_cif_metadata='fill')

            >>> # Several materials at once
            >>> api.v2.upsert_material_bundles(
            ...     [b1, b2], cif_files={'Zeolite_13X': 'Zeolite_13X.cif'})
        """
        if method is not None and method.lower() not in ("put", "post"):
            raise ValueError("method must be 'put' or 'post'")
        if derive_cif_metadata not in (True, False, "fill"):
            raise ValueError("derive_cif_metadata must be True, False or 'fill'")

        single = isinstance(bundles, dict)
        if single:
            raw_bundles = [bundles]
        elif isinstance(bundles, list):
            raw_bundles = bundles
        else:
            raise TypeError("bundles must be a bundle dict or a list of bundle dicts")
        if not raw_bundles:
            raise ValueError("No bundles given.")

        prepared = [
            _prepare_bundle(b, index, strip_ids=strip_ids, tag_names=tag_names)
            for index, b in enumerate(raw_bundles)
        ]
        files, derived = self._attach_bundle_cifs(
            prepared, cif_files, inline_cifs, derive_cif_metadata,
        )
        if derive_cif_metadata:
            # Rows that arrived with their structure inline (a bundle read with
            # include_cif_content=true) describe a CIF too.
            for bundle in prepared:
                for row in bundle.get("cifs") or []:
                    if (isinstance(row, dict) and id(row) not in derived
                            and isinstance(row.get("content"), str)):
                        _apply_cif_metadata(row, row["content"], derive_cif_metadata)

        body: Any = prepared[0] if single else prepared
        params = {"create_materials": "true" if create_materials else "false"}
        verb = method.lower() if method else ("post" if files else "put")

        if files:
            # Multipart: the JSON document travels in a 'bundle' form field and
            # each CIF as its own named part, referenced by `cifs[].file`.
            parts: dict[str, tuple] = {
                "bundle": (None, json.dumps(body), "application/json"),
                **files,
            }
            response = self._send(verb, "/materials/bundle/upsert/",
                                  params=params, files=parts, timeout=timeout)
        else:
            response = self._send(verb, "/materials/bundle/upsert/",
                                  params=params, json_body=body, timeout=timeout)

        payload = response.json()
        if response.status_code == 207:
            errors = payload.get("errors") or []
            warnings.warn(
                f"Partial success (207): {len(errors)} of {len(prepared)} bundle(s) "
                f"failed at index/indices {[e.get('index') for e in errors]} — "
                f"{[e.get('error') for e in errors]}. Each bundle is its own "
                "transaction, so the failed ones changed nothing. Retry only those "
                "indices; re-sending the whole payload re-applies the rest.",
                UserWarning,
                stacklevel=2,
            )
        return payload

    def _attach_bundle_cifs(self, bundles: list[dict],
                            cif_files: str | Path | list | dict | None,
                            inline_cifs: bool,
                            derive_cif_metadata: bool | str = False,
                            ) -> tuple[dict[str, tuple], set[int]]:
        """
        Attach local CIF files to prepared bundles.

        Mutates each bundle's ``cifs`` section in place — inline as ``content``,
        or as a ``file`` part name, with metadata derived from the file when
        asked. Returns the multipart parts to send (empty when ``inline_cifs``
        is set or no files were given) and the ids of the rows already derived.
        """
        if cif_files is None:
            return {}, set()

        by_index: dict[int, list[Path]] = {}
        if isinstance(cif_files, dict):
            names = {
                (b.get("material") or {}).get("name"): i
                for i, b in enumerate(bundles)
            }
            for name, paths in cif_files.items():
                if name not in names:
                    raise ValueError(
                        f"cif_files key '{name}' matches no bundle; "
                        f"bundle material names: {[n for n in names if n]}"
                    )
                by_index.setdefault(names[name], []).extend(_as_paths(paths))
        else:
            if len(bundles) != 1:
                raise ValueError(
                    "Pass cif_files as a {material name: path} mapping when "
                    "upserting more than one bundle."
                )
            by_index[0] = _as_paths(cif_files)

        parts: dict[str, tuple] = {}
        derived: set[int] = set()
        for index, paths in by_index.items():
            bundle = bundles[index]
            rows = bundle.setdefault("cifs", [])
            if not isinstance(rows, list):
                raise ValueError(f"bundles[{index}]['cifs'] must be a list")

            for position, path in enumerate(paths):
                if not path.is_file():
                    raise FileNotFoundError(f"CIF file not found: {path}")

                row = _match_cif_row(rows, path)
                if row is None:
                    # No metadata row for this file — add one. The first CIF a
                    # material gets is its primary structure.
                    row = {"primary": not any(r.get("primary") for r in rows)}
                    rows.append(row)

                data = path.read_bytes()
                if inline_cifs:
                    row["content"] = data.decode("utf-8")
                    row.pop("file", None)
                    row.setdefault("filename", f"cifs/{path.name}")
                else:
                    # `content` and `file` are mutually exclusive on a row.
                    part_name = f"cif_{index}_{position}"
                    row["file"] = part_name
                    row.pop("content", None)
                    parts[part_name] = (path.name, data, "chemical/x-cif")

                if derive_cif_metadata:
                    _apply_cif_metadata(row, data.decode("utf-8", errors="replace"),
                                        derive_cif_metadata)
                    derived.add(id(row))

        return parts, derived

    def preflight_material_check(self, name: str) -> bool:
        """
        Check whether a material with the given name exists in the database.

        Calls ``list_materials(name=name, limit=1)`` and returns ``True`` if
        at least one result is returned.

        Args:
            name: Material name to search for (substring match).

        Returns:
            ``True`` if at least one matching material is found, ``False`` otherwise.
        """
        results = self.list_materials(name=name, limit=1)
        if isinstance(results, list):
            return len(results) > 0
        return not results.empty

    # ── Internal record helpers ───────────────────────────────────────────────

    def _as_records(self, result: Any) -> list[dict]:
        """Normalise a DataFrame or list[dict] to list[dict]."""
        if isinstance(result, pd.DataFrame):
            return result.to_dict(orient="records")
        if isinstance(result, list):
            return result
        return []

    def _payload_to_records(self, payload: pd.DataFrame | list[dict] | dict) -> list[dict]:
        """
        Normalise write payloads to list[dict] while preserving all fields.

        NaN/±inf/``pd.NA``/``NaT`` become ``None`` and numpy scalars become
        plain Python values, so the result is valid JSON.
        """
        if isinstance(payload, pd.DataFrame):
            return _json_safe(payload.to_dict(orient="records"))
        if isinstance(payload, dict):
            return [_json_safe(payload)]
        if isinstance(payload, list):
            return _json_safe(payload)
        raise TypeError("payload must be a DataFrame, dict, or list[dict]")

    def _autoprism_meta_provenance(self, repo_dir: str | Path | None = None) -> dict[str, str | None]:
        """
        Build meta_provenance from the caller's git repository.

        Git runs in *repo_dir*, or the current working directory if omitted —
        i.e. the program doing the upload, not prisma_api itself. The
        semantic version comes from that repository's ``pyproject.toml``.
        """
        cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()

        def _git(args: list[str]) -> str | None:
            return _git_output(args, cwd)

        repo_root = _git(["rev-parse", "--show-toplevel"])
        root = Path(repo_root) if repo_root else cwd.resolve()
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        source_repo = (
            root.name
            if branch in (None, "main", "HEAD")
            else f"{root.name} (branch: {branch})"
        )

        pyproject_version: str | None = None
        pyproject_path = root / "pyproject.toml"
        if pyproject_path.exists():
            text = pyproject_path.read_text(encoding="utf-8")
            try:
                import tomllib  # Python 3.11+

                data = tomllib.loads(text)
                project = data.get("project", {}) if isinstance(data, dict) else {}
                value = project.get("version") if isinstance(project, dict) else None
                pyproject_version = str(value) if value else None
            except Exception:
                # Fallback for environments where tomllib is unavailable.
                m = re.search(r"(?ms)^\[project\].*?^version\s*=\s*\"([^\"]+)\"", text)
                pyproject_version = m.group(1).strip() if m else None

        return {
            "source_repo": source_repo,
            "source_repo_semantic_version": pyproject_version,
            "source_repo_tag": _git(["describe", "--tags", "--abbrev=0"]),
            "source_commit_hash": _git(["rev-parse", "HEAD"]),
        }

    def _autoprism_source_repo_url(self, repo_dir: str | Path | None = None) -> str | None:
        """Return the caller's ``origin`` remote URL with any credentials removed."""
        cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
        url = _git_output(["remote", "get-url", "origin"], cwd)
        return _strip_url_credentials(url) if url else None

    def _resolve_meta_provenance(self, meta_provenance: dict | None = None,
                                 repo_dir: str | Path | None = None) -> dict:
        """Return *meta_provenance* as given, or derive it from git in *repo_dir*."""
        if meta_provenance is not None:
            if not isinstance(meta_provenance, dict):
                raise TypeError("meta_provenance must be a dict or None")
            return _json_safe(dict(meta_provenance))
        return {
            **self._autoprism_meta_provenance(repo_dir),
            "source_repo_url": self._autoprism_source_repo_url(repo_dir),
        }

    def _upsert_autoprism_table(self, method_name: str,
                                payload: pd.DataFrame | list[dict] | dict,
                                meta_provenance: dict | None,
                                repo_dir: str | Path | None,
                                timeout: int | None) -> dict:
        """Shared body of the AutoPrism table upserts: unwrap, stamp provenance, PUT."""
        path, wrapper_key = _AUTOPRISM_TABLES[method_name]
        if isinstance(payload, dict) and isinstance(payload.get(wrapper_key), list):
            payload = payload[wrapper_key]
        records = self._payload_to_records(payload)
        meta = self._resolve_meta_provenance(meta_provenance, repo_dir)
        enriched = [
            {**record, "meta_provenance": meta} if isinstance(record, dict) else record
            for record in records
        ]
        return self._put(path, enriched, timeout=timeout)

    def _properties_for(self, object_id: int, limit: int = 2000) -> list[dict]:
        """Return all Property records linked to *object_id* via GenericForeignKey.

        The GFK fields (``object_id``, ``content_type``, ``content_type_id``)
        are stripped from every returned record — they served their purpose for
        the fetch and carry no semantic value in the assembled bundle.
        Records are sorted alphabetically by ``name``.
        """
        _GFK_DROP = frozenset({"id", "object_id", "content_type", "content_type_id"})
        records = self._as_records(
            self.get_properties(object_id=object_id, limit=limit)
        )
        cleaned = [
            {k: v for k, v in r.items() if k not in _GFK_DROP}
            for r in records
        ]
        return sorted(cleaned, key=lambda r: str(r.get("name", "")).lower())

    # ── Cases bundle ──────────────────────────────────────────────────────────

    def get_cases_bundle(
        self,
        name: str | None = None,
        source: str | None = None,
        sink: str | None = None,
        region: str | None = None,
        limit_cases: int = 100,
        limit_props: int = 2000,
    ) -> list[dict]:
        """
        Aggregate all related data for one or more CaseStudy records into a
        structured bundle, following the full relationship graph:

            CaseStudy
            ├── source        → Source         + properties (GFK)
            ├── sink          → Sink            + properties (GFK)
            ├── region        → Region          + properties (GFK, ambient params)
            ├── utilities     → Utility[]       + properties (GFK) each
            ├── subsystems    → Subsystem[]     + properties (GFK) each  (if present on case detail)
            └── scenarios     → Scenario[]
                    └── process_conditions → ProcessConditions  + properties (GFK)
                                └── configurations → ProcessConfiguration[] + properties (GFK) each

        Args:
            name:        Substring filter on CaseStudy name (passed to get_cases).
            source:      Substring filter on source name   (passed to get_cases).
            sink:        Substring filter on sink name     (passed to get_cases).
            region:      Exact ISO code filter on region   (passed to get_cases).
            limit_cases: Maximum number of cases to fetch (default 100).
            limit_props: Maximum properties per related object (default 2000).

        Returns:
            list[dict] — one entry per matched case, each structured as::

                {
                  "case": { ...case fields... },
                  "source": {
                      "record":     { ...source fields... },
                      "properties": [ ...property records... ]
                  },
                  "sink": {
                      "record":     { ...sink fields... },
                      "properties": [ ...property records... ]
                  },
                  "region": {
                      "record":     { ...region fields... },
                      "properties": [ ...property records... ]
                  },
                  "utilities": [
                      { "record": {...}, "properties": [...] },
                      ...
                  ],
                  "subsystems": [
                      { "record": {...}, "properties": [...] },
                      ...
                  ],
                  "scenarios": [
                      {
                          "record": { ...scenario fields... },
                          "process_conditions": {
                              "record":          { ...process condition fields... },
                              "properties":      [ ...property records... ],
                              "configurations":  [
                                  { "record": {...}, "properties": [...] },
                                  ...
                              ]
                          } | None
                      },
                      ...
                  ]
                }
        """

        # ── helpers ────────────────────────────────────────────────────────

        def _sort_props(props: list[dict]) -> list[dict]:
            """Sort a property list alphabetically by name (case-insensitive)."""
            return sorted(props, key=lambda r: str(r.get("name", "")).lower())

        def _first_record(result: Any) -> dict | None:
            records = self._as_records(result)
            return records[0] if records else None

        def _object_node(record: dict | None) -> dict:
            """Wrap a single record + its properties into a bundle node."""
            if record is None:
                return {"record": None, "properties": []}
            obj_id = record.get("id")
            props  = _sort_props(self._properties_for(obj_id, limit=limit_props)) if obj_id else []
            return {"record": record, "properties": props}

        # ── fetch matching cases ───────────────────────────────────────────

        cases = self._as_records(
            self.get_cases(source=source, sink=sink,
                           region=region, limit=limit_cases)
        )
        # Client-side name substring filter (get_cases has no name param)
        if name:
            name_lower = name.lower()
            cases = [c for c in cases if name_lower in str(c.get("name", "")).lower()]

        bundles: list[dict] = []

        for case in cases:
            case_id = case["id"]

            # ── source ────────────────────────────────────────────────────
            source_name = case.get("source")
            source_rec  = _first_record(
                self.get_sources(name=source_name, limit=10)
            ) if source_name else None
            # prefer exact match
            if source_rec and source_rec.get("name") != source_name:
                candidates = [
                    r for r in self._as_records(self.get_sources(name=source_name, limit=50))
                    if r.get("name") == source_name
                ]
                if candidates:
                    source_rec = candidates[0]

            # ── sink ──────────────────────────────────────────────────────
            sink_name = case.get("sink")
            sink_rec  = _first_record(
                self.get_sinks(name=sink_name, limit=10)
            ) if sink_name else None
            if sink_rec and sink_rec.get("name") != sink_name:
                candidates = [
                    r for r in self._as_records(self.get_sinks(name=sink_name, limit=50))
                    if r.get("name") == sink_name
                ]
                if candidates:
                    sink_rec = candidates[0]

            # ── region ────────────────────────────────────────────────────
            region_code = case.get("region")
            region_rec  = _first_record(
                self.get_regions(code=region_code, limit=1)
            ) if region_code else None

            # ── utilities ─────────────────────────────────────────────────
            utils_raw = case.get("utilities") or []
            if isinstance(utils_raw, str):
                utils_raw = [utils_raw] if utils_raw else []
            utility_nodes: list[dict] = []
            for util_name in utils_raw:
                util_rec = _first_record(self.get_utilities(name=util_name, limit=10))
                if util_rec and util_rec.get("name") != util_name:
                    candidates = [
                        r for r in self._as_records(self.get_utilities(name=util_name, limit=50))
                        if r.get("name") == util_name
                    ]
                    if candidates:
                        util_rec = candidates[0]
                utility_nodes.append(_object_node(util_rec))

            # ── subsystems (M2M — present on case detail if serialiser exposes them)
            subsystem_nodes: list[dict] = []
            case_detail    = self.get_case(case_id)
            subsystems_raw = case_detail.get("subsystems") or []
            if isinstance(subsystems_raw, str):
                subsystems_raw = [subsystems_raw] if subsystems_raw else []
            for sub_item in subsystems_raw:
                # sub_item may be a name string or a dict with 'name'/'id'
                if isinstance(sub_item, dict):
                    sub_rec = sub_item
                else:
                    sub_name = str(sub_item)
                    sub_rec  = _first_record(self.get_subsystems(name=sub_name, limit=10))
                    if sub_rec and sub_rec.get("name") != sub_name:
                        candidates = [
                            r for r in self._as_records(self.get_subsystems(name=sub_name, limit=50))
                            if r.get("name") == sub_name
                        ]
                        if candidates:
                            sub_rec = candidates[0]
                subsystem_nodes.append(_object_node(sub_rec))

            # ── scenarios ─────────────────────────────────────────────────
            scenario_nodes: list[dict] = []
            scenarios = self._as_records(
                self.get_scenarios(case_id=case_id, limit=200)
            )
            for scen in scenarios:
                scen_id     = scen["id"]
                scen_detail = self.get_scenario(scen_id)

                # Process conditions: look for process_conditions or
                # process_conditions_id in the scenario detail response
                pc_node: dict | None = None
                pc_name = scen_detail.get("process_conditions")
                pc_id   = scen_detail.get("process_conditions_id")

                if pc_id:
                    try:
                        pc_rec = self.get_process_condition(int(pc_id))
                    except Exception:
                        pc_rec = None
                elif pc_name:
                    pc_rec = _first_record(
                        self.get_process_conditions(name=pc_name, limit=10)
                    )
                    if pc_rec and pc_rec.get("name") != pc_name:
                        candidates = [
                            r for r in self._as_records(
                                self.get_process_conditions(name=pc_name, limit=50)
                            )
                            if r.get("name") == pc_name
                        ]
                        pc_rec = candidates[0] if candidates else pc_rec
                else:
                    pc_rec = None

                if pc_rec:
                    pc_obj_id = pc_rec.get("id")
                    pc_props  = _sort_props(self._properties_for(pc_obj_id, limit=limit_props)) if pc_obj_id else []

                    # ProcessConfigurations that reference this ProcessConditions
                    # (purge / desiccant / process_data FKs on ProcessConfiguration)
                    cfg_nodes: list[dict] = []
                    cfgs = self._as_records(
                        self.get_process_configurations(name=pc_rec.get("name"), limit=100)
                    )
                    for cfg in cfgs:
                        cfg_obj_id = cfg.get("id")
                        cfg_props  = _sort_props(self._properties_for(cfg_obj_id, limit=limit_props)) if cfg_obj_id else []
                        cfg_nodes.append({"record": cfg, "properties": cfg_props})

                    pc_node = {
                        "record":         pc_rec,
                        "properties":     pc_props,
                        "configurations": cfg_nodes,
                    }

                scenario_nodes.append({
                    "record":             scen_detail,
                    "process_conditions": pc_node,
                })

            # ── assemble bundle ───────────────────────────────────────────
            bundle = {
                "case":       case_detail,
                "source":     _object_node(source_rec),
                "sink":       _object_node(sink_rec),
                "region":     _object_node(region_rec),
                "utilities":  utility_nodes,
                "subsystems": subsystem_nodes,
                "scenarios":  scenario_nodes,
            }

            # ── summary print (mirrors get_material_property_bundle style) ──
            n_props = (
                len(bundle["source"]["properties"])
                + len(bundle["sink"]["properties"])
                + len(bundle["region"]["properties"])
                + sum(u["properties"].__len__() for u in utility_nodes)
                + sum(s["properties"].__len__() for s in subsystem_nodes)
                + sum(
                    len(sn["process_conditions"]["properties"]) if sn["process_conditions"] else 0
                    for sn in scenario_nodes
                )
                + sum(
                    len(c["properties"])
                    for sn in scenario_nodes
                    if sn["process_conditions"]
                    for c in sn["process_conditions"]["configurations"]
                )
            )
            print(
                f"Case bundle '{case_detail.get('name', case_id)}': "
                f"{len(scenarios)} scenario(s), "
                f"{len(utility_nodes)} utility/ies, "
                f"{len(subsystem_nodes)} subsystem(s), "
                f"{n_props} total property records"
            )

            bundles.append(bundle)

        return bundles

    def get_molecules(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/molecules/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/molecules/", params))

    def get_molecule(self, molecule_id: int) -> dict:
        """GET /api/v2/molecules/{molecule_id}/"""
        return self._get(f"/molecules/{molecule_id}/")

    def get_elements(self, symbol: str | None = None, name: str | None = None,
                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/elements/

        Args:
            symbol: Exact symbol filter (case-insensitive), e.g. 'Fe'.
            name:   Substring filter on element name.
        """
        params = _compact(symbol=symbol, name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/elements/", params))

    def get_element(self, element_id: int) -> dict:
        """GET /api/v2/elements/{element_id}/"""
        return self._get(f"/elements/{element_id}/")

    def get_regions(self, code: str | None = None, name: str | None = None,
                    limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/regions/

        Args:
            code: Exact ISO code filter (case-insensitive), e.g. 'GB'.
            name: Substring filter on region name.
        """
        params = _compact(code=code, name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/regions/", params))

    def get_region(self, region_id: int) -> dict:
        """GET /api/v2/regions/{region_id}/"""
        return self._get(f"/regions/{region_id}/")

    def get_sources(self, name: str | None = None,
                    limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/sources/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/sources/", params))

    def get_source(self, source_id: int) -> dict:
        """GET /api/v2/sources/{source_id}/"""
        return self._get(f"/sources/{source_id}/")

    def get_scopes(self, name: str | None = None,
                   limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/scopes/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._coerce_scope_types(self._to_df(self._get("/scopes/", params)))

    def get_scope(self, scope_id: int) -> dict:
        """GET /api/v2/scopes/{scope_id}/"""
        return self._coerce_scope_types(self._get(f"/scopes/{scope_id}/"))

    def get_sinks(self, name: str | None = None,
                  limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/sinks/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/sinks/", params))

    def get_sink(self, sink_id: int) -> dict:
        """GET /api/v2/sinks/{sink_id}/"""
        return self._get(f"/sinks/{sink_id}/")

    def get_transport_scenarios(self, name: str | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/transport-scenarios/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/transport-scenarios/", params))

    def get_transport_scenario(self, ts_id: int) -> dict:
        """GET /api/v2/transport-scenarios/{ts_id}/"""
        return self._get(f"/transport-scenarios/{ts_id}/")

    def get_utilities(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/utilities/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/utilities/", params))

    def get_utility(self, utility_id: int) -> dict:
        """GET /api/v2/utilities/{utility_id}/"""
        return self._get(f"/utilities/{utility_id}/")

    def get_references(self, name: str | None = None, doi: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/references/

        Args:
            name: Substring filter on reference name.
            doi:  Exact DOI filter (case-insensitive).
        """
        params = _compact(name=name, doi=doi, limit=limit, offset=offset)
        return self._to_df(self._get("/references/", params))

    def get_reference(self, ref_id: int) -> dict:
        """GET /api/v2/references/{ref_id}/"""
        return self._get(f"/references/{ref_id}/")

    def get_transports(self, name: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/transports/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/transports/", params))

    def get_transport(self, transport_id: int) -> dict:
        """GET /api/v2/transports/{transport_id}/"""
        return self._get(f"/transports/{transport_id}/")

    def get_subsystems(self, name: str | None = None, type: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/subsystems/

        Args:
            name: Substring filter on subsystem name.
            type: Exact type filter (e.g. 'dac').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/subsystems/", params))

    def get_subsystem(self, subsystem_id: int) -> dict:
        """GET /api/v2/subsystems/{subsystem_id}/"""
        return self._get(f"/subsystems/{subsystem_id}/")


    def get_properties(self,
                       name: str | None = None,
                       domain: str | None = None,
                       category: str | None = None,
                       object_id: int | None = None,
                       limit: int = 500,
                       offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/properties/

        Args:
            name:      Substring filter on property name.
            domain:    Domain filter (e.g. 'TEA').
            category:  Category filter (e.g. 'params_amb').
            object_id: Exact object PK filter.
        """
        params = _compact(name=name, domain=domain, category=category,
                          object_id=object_id, limit=limit, offset=offset)
        return self._to_df(self._get("/properties/", params))

    def get_property(self, property_id: int) -> dict:
        """GET /api/v2/properties/{property_id}/"""
        return self._get(f"/properties/{property_id}/")

    def get_equipment(self, name: str | None = None, group: str | None = None,
                          limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/equipment/

        Args:
            name:  Substring filter on equipment name.
            group: Exact group filter (e.g. 'Blower').
        """
        params = _compact(name=name, group=group, limit=limit, offset=offset)
        return self._to_df(self._get("/equipment/", params))

    def get_equipment_item(self, equipment_id: int) -> dict:
        """GET /api/v2/equipment/{equipment_id}/"""
        return self._get(f"/equipment/{equipment_id}/")

    def get_equipment_costs(self, equipment_id: int | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/equipment-costs/

        Args:
            equipment_id: Exact equipment PK filter.
        """
        params = _compact(equipment_id=equipment_id, limit=limit, offset=offset)
        return self._to_df(self._get("/equipment-costs/", params))

    def get_equipment_cost(self, cost_id: int) -> dict:
        """GET /api/v2/equipment-costs/{cost_id}/"""
        return self._get(f"/equipment-costs/{cost_id}/")

    def get_equipment_designs(self, equipment_id: int | None = None,
                                  key: str | None = None,
                                  limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/equipment-designs/

        Args:
            equipment_id: Exact equipment PK filter.
            key:          Exact design parameter key filter (e.g. 'D1').
        """
        params = _compact(equipment_id=equipment_id, key=key,
                          limit=limit, offset=offset)
        return self._to_df(self._get("/equipment-designs/", params))

    def get_equipment_design(self, design_id: int) -> dict:
        """GET /api/v2/equipment-designs/{design_id}/"""
        return self._get(f"/equipment-designs/{design_id}/")

    def get_process_conditions(self, name: str | None = None,
                               type: str | None = None,
                               limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/process-conditions/

        Args:
            name: Substring filter on process condition name.
            type: Exact type filter (e.g. 'tvsa').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/process-conditions/", params))

    def get_process_condition(self, condition_id: int) -> dict:
        """GET /api/v2/process-conditions/{condition_id}/"""
        return self._get(f"/process-conditions/{condition_id}/")

    def get_process_configurations(self, name: str | None = None,
                                   type: str | None = None,
                                   limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/process-configurations/

        Args:
            name: Substring filter on process configuration name.
            type: Exact type filter (e.g. 'dac').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/process-configurations/", params))

    def get_process_configuration(self, config_id: int) -> dict:
        """GET /api/v2/process-configurations/{config_id}/"""
        return self._get(f"/process-configurations/{config_id}/")

    def get_contactor_configurations(self, name: str | None = None,
                                     type: str | None = None,
                                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/contactor-configurations/

        Args:
            name: Substring filter on contactor configuration name.
            type: Exact type filter (e.g. 'kiln').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/contactor-configurations/", params))

    def get_contactor_configuration(self, config_id: int) -> dict:
        """GET /api/v2/contactor-configurations/{config_id}/"""
        return self._get(f"/contactor-configurations/{config_id}/")

    def get_cost_indices(self, year: int | None = None,
                         limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/cost-indices/

        Args:
            year: Exact year filter.
        """
        params = _compact(year=year, limit=limit, offset=offset)
        return self._to_df(self._get("/cost-indices/", params))

    def get_cost_index(self, index_id: int) -> dict:
        """GET /api/v2/cost-indices/{index_id}/"""
        return self._get(f"/cost-indices/{index_id}/")

    def get_constants(self, param: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/constants/

        Args:
            param: Exact parameter symbol filter (e.g. 'R').
        """
        params = _compact(param=param, limit=limit, offset=offset)
        return self._to_df(self._get("/constants/", params))

    def get_constant(self, constant_id: int) -> dict:
        """GET /api/v2/constants/{constant_id}/"""
        return self._get(f"/constants/{constant_id}/")

    def get_mea_baselines(self, name: str | None = None,
                          limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/mea/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/mea/", params))

    def get_mea_baseline(self, mea_id: int) -> dict:
        """GET /api/v2/mea/{mea_id}/"""
        return self._get(f"/mea/{mea_id}/")

    def get_mea_kpis(self, name: str | None = None, category: str | None = None,
                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/mea-kpis/

        Args:
            name:     Substring filter on KPI name.
            category: Exact category filter (e.g. 'CAC').
        """
        params = _compact(name=name, category=category, limit=limit, offset=offset)
        return self._to_df(self._get("/mea-kpis/", params))

    def get_mea_kpi(self, kpi_id: int) -> dict:
        """GET /api/v2/mea-kpis/{kpi_id}/"""
        return self._get(f"/mea-kpis/{kpi_id}/")

    # ── Science data ──────────────────────────────────────────────────────────

    def get_isotherm(self,
                     mof: str | None = None,
                     molecule: str | None = None,
                     temperature_min: float | None = None,
                     temperature_max: float | None = None,
                     sim_or_exp: str | None = None,
                     good_structure: bool | None = None,
                     limit: int = 500,
                     offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/isotherms/

        Args:
            mof:             MOF name substring filter.
            molecule:        Molecule name substring filter.
            temperature_min: Lower bound on T_ref_K [K].
            temperature_max: Upper bound on T_ref_K [K].
            sim_or_exp:      'sim' or 'exp'.
            good_structure:  Filter to good/bad structures.
            limit:           Max records (default 500).
            offset:          Pagination offset.

        Returns:
            DataFrame with one row per isotherm record.
        """
        params = _compact(
            mof=mof, molecule=molecule,
            temperature_min=temperature_min, temperature_max=temperature_max,
            sim_or_exp=sim_or_exp,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/isotherms/", params))

    def get_water_kpis(self,
                       mof: str | None = None,
                       molecule: str | None = None,
                       source: str | None = None,
                       sim_or_exp: str | None = None,
                       good_structure: bool | None = None,
                       limit: int = 500,
                       offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/water-kpis/

        Args:
            mof:            MOF name substring filter.
            molecule:       Molecule name substring filter.
            source:         Source name substring filter.
            sim_or_exp:     'sim' or 'exp'.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            mof=mof, molecule=molecule, source=source,
            sim_or_exp=sim_or_exp,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        records = self._to_df(self._get("/water-kpis/", params))
        # Strip integer FK fields 'MOF' and 'Molecule' (DB PKs) — the
        # human-readable equivalents are kept as 'mof' and 'molecule'.
        _drop = {"MOF", "Molecule"}
        if isinstance(records, list):
            return [{k: v for k, v in r.items() if k not in _drop} for r in records]
        if isinstance(records, pd.DataFrame):
            return records.drop(columns=[c for c in _drop if c in records.columns])
        return records

    def get_carbon_zeopp(self,
                         mof: str | None = None,
                         good_structure: bool | None = None,
                         limit: int = 500,
                         offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/carbon-zeopp/

        Simulated Zeo++ geometric characterisation data.

        Args:
            mof:            MOF name substring filter.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            mof=mof,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/carbon-zeopp/", params))

    def get_carbon_zeopp_item(self, item_id: int) -> dict:
        """GET /api/v2/carbon-zeopp/{item_id}/"""
        return self._get(f"/carbon-zeopp/{item_id}/")

    def get_carbon_zeopp_experimental(self,
                                      mof: str | None = None,
                                      limit: int = 500,
                                      offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/carbon-zeopp-experimental/

        Experimental Zeo++ geometric characterisation data.

        Args:
            mof: MOF name substring filter.
        """
        params = _compact(mof=mof, limit=limit, offset=offset)
        return self._to_df(self._get("/carbon-zeopp-experimental/", params))

    def get_carbon_zeopp_experimental_item(self, item_id: int) -> dict:
        """GET /api/v2/carbon-zeopp-experimental/{item_id}/"""
        return self._get(f"/carbon-zeopp-experimental/{item_id}/")

    # ── AutoPrism tables ─────────────────────────────────────────────────────

    def get_computation_runs(
        self,
        workflow_id: str | None = None,
        step: str | None = None,
        status: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/computation-runs/

        Args:
            workflow_id: Workflow identifier filter.
            step: Step filter.
            status: Status filter.
        """
        params = _compact(
            workflow_id=workflow_id,
            step=step,
            status=status,
            limit=limit,
            offset=offset,
        )
        return self._to_df(self._get("/computation-runs/", params))

    def get_computation_run(self, run_id: int) -> dict:
        """GET /api/v2/computation-runs/{run_id}/"""
        return self._get(f"/computation-runs/{run_id}/")

    def upsert_computation_runs(self, payload: pd.DataFrame | list[dict] | dict,
                                timeout: int | None = None) -> dict:
        """
        PUT /api/v2/computation-runs/

        Accepts one object or many objects and forwards all provided fields.
        """
        return self._put("/computation-runs/", self._payload_to_records(payload),
                         timeout=timeout)

    def get_adsorption_singlepoint(
        self,
        structure: str | None = None,
        md5: str | None = None,
        mixture_id: str | None = None,
        component: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/adsorption-singlepoint/

        Args:
            structure: Structure name filter.
            md5: Exact md5 hash filter.
            mixture_id: Mixture identifier filter.
            component: Component filter.
        """
        params = _compact(
            structure=structure,
            md5=md5,
            mixture_id=mixture_id,
            component=component,
            limit=limit,
            offset=offset,
        )
        return self._to_df(self._get("/adsorption-singlepoint/", params))

    def get_adsorption_singlepoint_item(self, row_id: int) -> dict:
        """GET /api/v2/adsorption-singlepoint/{row_id}/"""
        return self._get(f"/adsorption-singlepoint/{row_id}/")

    def upsert_adsorption_singlepoint(
        self,
        payload: pd.DataFrame | list[dict] | dict,
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        PUT /api/v2/adsorption-singlepoint/

        Accepts one object or many objects. Every row's ``meta_provenance`` is
        replaced with the resolved provenance.

        Args:
            payload: DataFrame, one record, a list of records, or
                ``{"adsorption_singlepoints": [...]}``.
            meta_provenance: Provenance stamped on every row, used as-is. If
                omitted it is derived from git in *repo_dir* (default: the
                current working directory), with credentials removed from the
                remote URL.
            repo_dir: Repository to read provenance from when
                *meta_provenance* is not given.
            timeout: Request timeout in seconds (default: ``upload_timeout``).
        """
        return self._upsert_autoprism_table("upsert_adsorption_singlepoint", payload,
                                            meta_provenance, repo_dir, timeout)

    def get_heat_capacity(
        self,
        structure: str | None = None,
        temperature_K: float | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/heat-capacity/

        Args:
            structure: Structure name filter.
            temperature_K: Temperature filter [K].
        """
        params = _compact(
            structure=structure,
            temperature_K=temperature_K,
            limit=limit,
            offset=offset,
        )
        return self._to_df(self._get("/heat-capacity/", params))

    def get_heat_capacity_item(self, row_id: int) -> dict:
        """GET /api/v2/heat-capacity/{row_id}/"""
        return self._get(f"/heat-capacity/{row_id}/")

    def upsert_heat_capacity(
        self,
        payload: pd.DataFrame | list[dict] | dict,
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        PUT /api/v2/heat-capacity/

        Accepts one object or many objects. Every row's ``meta_provenance`` is
        replaced with the resolved provenance.

        Args:
            payload: DataFrame, one record, a list of records, or
                ``{"heat_capacities": [...]}``.
            meta_provenance: Provenance stamped on every row, used as-is. If
                omitted it is derived from git in *repo_dir* (default: the
                current working directory), with credentials removed from the
                remote URL.
            repo_dir: Repository to read provenance from when
                *meta_provenance* is not given.
            timeout: Request timeout in seconds (default: ``upload_timeout``).
        """
        return self._upsert_autoprism_table("upsert_heat_capacity", payload,
                                            meta_provenance, repo_dir, timeout)

    def get_isotherm_h2(
        self,
        structure: str | None = None,
        isotherm_id: str | None = None,
        component: str | None = None,
        temperature_K: float | None = None,
        pressure_bar: float | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/isotherm-h2/

        Args:
            structure: Structure name filter.
            isotherm_id: Isotherm identifier filter.
            component: Component filter.
            temperature_K: Temperature filter [K].
            pressure_bar: Pressure filter [bar].
        """
        params = _compact(
            structure=structure,
            isotherm_id=isotherm_id,
            component=component,
            temperature_K=temperature_K,
            pressure_bar=pressure_bar,
            limit=limit,
            offset=offset,
        )
        return self._to_df(self._get("/isotherm-h2/", params))

    def get_isotherm_h2_item(self, row_id: int) -> dict:
        """GET /api/v2/isotherm-h2/{row_id}/"""
        return self._get(f"/isotherm-h2/{row_id}/")

    def upsert_isotherm_h2(
        self,
        payload: pd.DataFrame | list[dict] | dict,
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        PUT /api/v2/isotherm-h2/

        Accepts one object or many objects. Every row's ``meta_provenance`` is
        replaced with the resolved provenance.

        Args:
            payload: DataFrame, one record, a list of records, or
                ``{"isotherm_H2s": [...]}``.
            meta_provenance: Provenance stamped on every row, used as-is. If
                omitted it is derived from git in *repo_dir* (default: the
                current working directory), with credentials removed from the
                remote URL.
            repo_dir: Repository to read provenance from when
                *meta_provenance* is not given.
            timeout: Request timeout in seconds (default: ``upload_timeout``).
        """
        return self._upsert_autoprism_table("upsert_isotherm_h2", payload,
                                            meta_provenance, repo_dir, timeout)

    def get_mofchecker(
        self,
        structure: str | None = None,
        md5: str | None = None,
        is_mof: bool | None = None,
        MOFQ: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/mofchecker/

        Args:
            structure: Structure name filter.
            md5: Exact md5 hash filter.
            is_mof: Boolean mofchecker flag.
            MOFQ: MOFQ classifier filter.
        """
        params = _compact(
            structure=structure,
            md5=md5,
            is_mof=None if is_mof is None else str(is_mof).lower(),
            MOFQ=MOFQ,
            limit=limit,
            offset=offset,
        )
        return self._to_df(self._get("/mofchecker/", params))

    def get_mofchecker_item(self, row_id: int) -> dict:
        """GET /api/v2/mofchecker/{row_id}/"""
        return self._get(f"/mofchecker/{row_id}/")

    def upsert_mofchecker(
        self,
        payload: pd.DataFrame | list[dict] | dict,
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        PUT /api/v2/mofchecker/

        Accepts one object or many objects. Every row's ``meta_provenance`` is
        replaced with the resolved provenance.

        Args:
            payload: DataFrame, one record, a list of records, or
                ``{"mofchecker": [...]}``.
            meta_provenance: Provenance stamped on every row, used as-is. If
                omitted it is derived from git in *repo_dir* (default: the
                current working directory), with credentials removed from the
                remote URL.
            repo_dir: Repository to read provenance from when
                *meta_provenance* is not given.
            timeout: Request timeout in seconds (default: ``upload_timeout``).
        """
        return self._upsert_autoprism_table("upsert_mofchecker", payload,
                                            meta_provenance, repo_dir, timeout)

    def get_zeopp_metrics(
        self,
        mof: str | None = None,
        md5: str | None = None,
        probe: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        GET /api/v2/zeopp-metrics/

        Args:
            mof: MOF name filter.
            md5: Exact md5 hash filter.
            probe: Probe name filter.
        """
        params = _compact(mof=mof, md5=md5, probe=probe, limit=limit, offset=offset)
        return self._to_df(self._get("/zeopp-metrics/", params))

    def get_zeopp_metrics_item(self, row_id: int) -> dict:
        """GET /api/v2/zeopp-metrics/{row_id}/"""
        return self._get(f"/zeopp-metrics/{row_id}/")

    def upsert_zeopp_metrics(
        self,
        payload: pd.DataFrame | list[dict] | dict,
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
    ) -> dict:
        """
        PUT /api/v2/zeopp-metrics/

        Accepts one object or many objects. Every row's ``meta_provenance`` is
        replaced with the resolved provenance.

        Args:
            payload: DataFrame, one record, a list of records, or
                ``{"zeopp_metrics": [...]}``.
            meta_provenance: Provenance stamped on every row, used as-is. If
                omitted it is derived from git in *repo_dir* (default: the
                current working directory), with credentials removed from the
                remote URL.
            repo_dir: Repository to read provenance from when
                *meta_provenance* is not given.
            timeout: Request timeout in seconds (default: ``upload_timeout``).
        """
        return self._upsert_autoprism_table("upsert_zeopp_metrics", payload,
                                            meta_provenance, repo_dir, timeout)

    def upsert_autoprism_collection(
        self,
        payload: dict[str, Any],
        meta_provenance: dict | None = None,
        repo_dir: str | Path | None = None,
        timeout: int | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """
        Upsert multiple AutoPrism sections from a single combined payload.

        Expected payload shape mirrors the AutoPrism collection mock payload, with
        optional top-level keys:
            computation_runs, adsorption_singlepoints, heat_capacities,
            isotherm_H2s, mofchecker, zeopp_metrics, meta_provenance

        Provenance (stamped on every row of the five AutoPrism tables), in
        order of precedence:
            1. the *meta_provenance* argument;
            2. the payload's top-level ``meta_provenance``;
            3. derived from git in *repo_dir* (default: current directory).

        Error handling:
            By default a failing section does not raise: it is reported with
            ``status: "error"`` and ``overall_status`` becomes
            ``"partial_failure"``. Check ``overall_status``, or pass
            ``raise_on_error=True`` to raise ``RuntimeError`` after all
            sections have been attempted.

        Returns:
            dict with keys:
                sections: per-section status details
                totals: aggregate created/updated counters
                overall_status: "ok" if no section failed, else "partial_failure"
        """
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict matching the AutoPrism collection shape")

        if meta_provenance is None:
            meta_provenance = payload.get("meta_provenance")
        # Resolve once so every section carries identical provenance.
        meta = self._resolve_meta_provenance(meta_provenance, repo_dir)

        section_handlers: list[tuple[str, str]] = [
            ("computation_runs", "upsert_computation_runs"),
            *((key, method) for method, (_, key) in _AUTOPRISM_TABLES.items()),
        ]

        sections: dict[str, dict[str, Any]] = {}
        total_created = 0
        total_updated = 0
        failed = 0

        for section_name, method_name in section_handlers:
            section_payload = payload.get(section_name)
            if section_payload is None:
                sections[section_name] = {
                    "status": "skipped",
                    "reason": "missing section in payload",
                }
                continue

            try:
                method = getattr(self, method_name)
                if method_name in _AUTOPRISM_TABLES:
                    result = method(section_payload, meta_provenance=meta, timeout=timeout)
                else:
                    result = method(section_payload, timeout=timeout)
                created = int(result.get("created", 0)) if isinstance(result, dict) else 0
                updated = int(result.get("updated", 0)) if isinstance(result, dict) else 0
                total_created += created
                total_updated += updated
                sections[section_name] = {
                    "status": "ok",
                    "created": created,
                    "updated": updated,
                    "result": result,
                }
            except Exception as exc:
                failed += 1
                sections[section_name] = {
                    "status": "error",
                    "error": str(exc),
                }

        summary = {
            "sections": sections,
            "totals": {
                "created": total_created,
                "updated": total_updated,
                "failed_sections": failed,
            },
            "overall_status": "ok" if failed == 0 else "partial_failure",
        }
        if raise_on_error and failed:
            errors = "; ".join(
                f"{name}: {info['error']}"
                for name, info in sections.items()
                if info["status"] == "error"
            )
            raise RuntimeError(f"AutoPrism upsert failed for {failed} section(s): {errors}")
        return summary

    def get_autoprism_collection(
        self,
        workflow_id: str | None = None,
        step: str | None = None,
        status: str | None = None,
        structure: str | None = None,
        mof: str | None = None,
        md5: str | None = None,
        mixture_id: str | None = None,
        component: str | None = None,
        isotherm_id: str | None = None,
        temperature_K: float | None = None,
        pressure_bar: float | None = None,
        probe: str | None = None,
        is_mof: bool | None = None,
        MOFQ: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, list[dict] | dict[str, str | None]]:
        """
        Gather AutoPrism table records in one call flow.

        Returns a dict with keys:
            computation_runs,
            adsorption_singlepoints, heat_capacities, isotherm_H2s,
            mofchecker, zeopp_metrics
            meta_provenance

        Notes:
                        - ``workflow_id``, ``step`` and ``status`` filter computation runs.
            - ``structure`` is used for adsorption_singlepoint, heat_capacity,
              isotherm_H2 and mofchecker.
            - ``mof`` is used for zeopp_metrics.
            - If ``structure`` is omitted and ``mof`` is provided, ``mof`` is
              also used as the structure filter for convenience.

        Empty payload handling:
            - If any sub-call returns ``None`` or an unexpected scalar payload,
              this method normalises it to an empty table representation
              (``pd.DataFrame()`` in dataframe mode, ``[]`` in json mode).
        """
        structure_filter = structure or mof

        def _empty_table() -> pd.DataFrame | list[dict]:
            return [] if self._return_format == "json" else pd.DataFrame()

        def _normalise_table_payload(value: Any) -> pd.DataFrame | list[dict]:
            if value is None:
                return _empty_table()
            if isinstance(value, (pd.DataFrame, list)):
                return value
            if isinstance(value, dict):
                return self._to_df(value)
            return _empty_table()

        def _record_count(value: Any) -> int:
            try:
                return len(value)
            except TypeError:
                return 0

        def _as_record_list(value: Any) -> list[dict]:
            records = self._as_records(value)
            return [r for r in records if isinstance(r, dict)]

        meta = self._resolve_meta_provenance()

        def _safe_fetch(section: str, fetcher, **kwargs) -> pd.DataFrame | list[dict]:
            try:
                return _normalise_table_payload(fetcher(**kwargs))
            except requests.HTTPError as exc:
                warnings.warn(
                    f"AutoPrism section '{section}' failed ({exc}); returning empty table.",
                    UserWarning,
                    stacklevel=2,
                )
                return _empty_table()
            except requests.RequestException as exc:
                warnings.warn(
                    f"AutoPrism section '{section}' request error ({exc}); returning empty table.",
                    UserWarning,
                    stacklevel=2,
                )
                return _empty_table()

        collection = {
            "computation_runs": _safe_fetch(
                "computation_runs",
                self.get_computation_runs,
                workflow_id=workflow_id,
                step=step,
                status=status,
                limit=limit,
                offset=offset,
            ),
            "adsorption_singlepoints": _safe_fetch(
                "adsorption_singlepoint",
                self.get_adsorption_singlepoint,
                structure=structure_filter,
                md5=md5,
                mixture_id=mixture_id,
                component=component,
                limit=limit,
                offset=offset,
            ),
            "heat_capacities": _safe_fetch(
                "heat_capacity",
                self.get_heat_capacity,
                structure=structure_filter,
                temperature_K=temperature_K,
                limit=limit,
                offset=offset,
            ),
            "isotherm_H2s": _safe_fetch(
                "isotherm_H2",
                self.get_isotherm_h2,
                structure=structure_filter,
                isotherm_id=isotherm_id,
                component=component,
                temperature_K=temperature_K,
                pressure_bar=pressure_bar,
                limit=limit,
                offset=offset,
            ),
            "mofchecker": _safe_fetch(
                "mofchecker",
                self.get_mofchecker,
                structure=structure_filter,
                md5=md5,
                is_mof=is_mof,
                MOFQ=MOFQ,
                limit=limit,
                offset=offset,
            ),
            "zeopp_metrics": _safe_fetch(
                "zeopp_metrics",
                self.get_zeopp_metrics,
                mof=mof,
                md5=md5,
                probe=probe,
                limit=limit,
                offset=offset,
            ),
        }

        collection = {
            key: _as_record_list(value)
            for key, value in collection.items()
        }
        collection["meta_provenance"] = meta

        label = structure_filter or mof or "all"
        print(f"AutoPrism collection for '{label}':")
        for key in (
            "computation_runs",
            "adsorption_singlepoints",
            "heat_capacities",
            "isotherm_H2s",
            "mofchecker",
            "zeopp_metrics",
        ):
            print(f"  {key:22s}: {_record_count(collection.get(key, []))} records")

        return collection

    # ── TEA / LCA data ────────────────────────────────────────────────────────

    def get_output_kpis(self,
                        scenario_id: int | None = None,
                        mof: str | None = None,
                        good_structure: bool | None = None,
                        limit: int = 500,
                        offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/output-kpis/

        Args:
            scenario_id:    Exact scenario PK filter.
            mof:            MOF name substring filter.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            scenario_id=scenario_id, mof=mof,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/output-kpis/", params))

    def get_output_kpi(self, kpi_id: int) -> dict:
        """GET /api/v2/output-kpis/{kpi_id}/"""
        return self._get(f"/output-kpis/{kpi_id}/")

    def upsert_output_kpis(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/output-kpis/

        Bulk upsert. Lookup key: (scenario, MOF) integer PKs.

        Args:
            df: DataFrame with columns matching the OutputKpi write schema.

        Returns:
            dict with keys 'created', 'updated', and optionally 'errors'.
        """
        return self._put("/output-kpis/", df.to_dict(orient="records"))

    def get_region_costs(self,
                         region: str | None = None,
                         name: str | None = None,
                         year: int | None = None,
                         limit: int = 500,
                         offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/region-costs/

        Args:
            region: Exact region ISO code filter.
            name:   Substring filter on cost name.
            year:   Exact year filter.
        """
        params = _compact(region=region, name=name, year=year, limit=limit, offset=offset)
        return self._to_df(self._get("/region-costs/", params))

    def get_region_cost(self, rc_id: int) -> dict:
        """GET /api/v2/region-costs/{rc_id}/"""
        return self._get(f"/region-costs/{rc_id}/")

    def upsert_region_costs(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/region-costs/  Lookup key: Name (unique).

        Args:
            df: DataFrame with columns matching the RegionCost write schema.
        """
        return self._put("/region-costs/", df.to_dict(orient="records"))

    def get_ambient_parameters(self, name: str | None = None,
                               limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/ambient-parameters/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/ambient-parameters/", params))

    def get_ambient_parameter(self, ap_id: int) -> dict:
        """GET /api/v2/ambient-parameters/{ap_id}/"""
        return self._get(f"/ambient-parameters/{ap_id}/")

    def upsert_ambient_parameters(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/ambient-parameters/  Lookup key: Name (unique).

        Args:
            df: DataFrame with columns matching the AmbientParameter write schema.
        """
        return self._put("/ambient-parameters/", df.to_dict(orient="records"))

    # ── Cases & Scenarios ─────────────────────────────────────────────────────

    def get_cases(self,
                  source: str | None = None,
                  sink: str | None = None,
                  region: str | None = None,
                  study: str | None = None,
                  limit: int = 500,
                  offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/cases/

        Args:
            source: Source name substring filter.
            sink:   Sink name substring filter.
            region: Exact region ISO code filter.
            study:  Exact study label filter.
        """
        params = _compact(source=source, sink=sink, region=region,
                          study=study, limit=limit, offset=offset)
        return self._to_df(self._get("/cases/", params))

    def get_case(self, case_id: int) -> dict:
        """GET /api/v2/cases/{case_id}/"""
        return self._get(f"/cases/{case_id}/")

    def list_case_studies(self,
                          name: str | None = None,
                          limit: int = 500,
                          offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/case-studies/

        Args:
            name:   Optional substring filter on case-study name.
            limit:  Maximum number of records to return.
            offset: Pagination offset.
        """
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/case-studies/", params))

    def get_scenarios(self,
                      case_id: int | None = None,
                      name: str | None = None,
                      type: str | None = None,
                      limit: int = 500,
                      offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/scenarios/

        Args:
            case_id: Exact case PK filter.
            name:    Substring filter on name or print_name.
            type:    Exact scenario type filter (e.g. 'TEA').
        """
        params = _compact(case_id=case_id, name=name, type=type,
                          limit=limit, offset=offset)
        return self._to_df(self._get("/scenarios/", params))

    def get_scenario(self, scenario_id: int) -> dict:
        """GET /api/v2/scenarios/{scenario_id}/"""
        return self._get(f"/scenarios/{scenario_id}/")

    def get_screening_analysis_bundle(self, analysis_id: int) -> dict:
        """GET /api/v2/screening-analyses/{analysis_id}/bundle/"""
        return self._get(f"/screening-analyses/{analysis_id}/bundle/")

    # ── Case-pack builders (ImportedCasePack spec) ────────────────────────────

    @staticmethod
    def _component_spec(component_type: str, name: str | None) -> dict | None:
        """
        Build a minimal ``CaseComponentSpec`` dict from a name string.

        Fields that require a local YAML document (``document``,
        ``region_use``, ``region_synthesis``, ``region_storage``,
        ``sink_type``) are set to ``None`` — they are not stored on the
        remote Django models and can only be populated from the originating
        YAML pack.
        """
        if name is None:
            return None
        return {
            "component_type": component_type,
            "name": name,
            "document": None,
            "region_use": None,
            "region_synthesis": None,
            "region_storage": None,
            "sink_type": None,
        }

    def build_case_spec(self, case_id: int) -> dict:
        """
        Fetch ``GET /api/v2/cases/{case_id}/`` and return a ``CaseSpec``-shaped
        nested dict conforming to the ``ImportedCasePack`` spec.

        Fields that live only in the originating YAML pack (``root_case_path``,
        per-component ``document`` sub-trees, ``import_issues``) are
        returned as ``None`` / ``[]``.

        Args:
            case_id: PK of the ``CaseStudy`` record.

        Returns:
            ``dict`` matching the ``CaseSpec`` schema::

                {
                  "case_name": str,
                  "source_name": str,
                  "sink_name": str,
                  "region": str,
                  "root_case_path": None,
                  "source":    { CaseComponentSpec },
                  "sink":      { CaseComponentSpec },
                  "transport": { CaseComponentSpec } | None,
                  "utilities": [ CaseComponentSpec, ... ],
                  "tea_general": None,
                  "import_issues": []
                }
        """
        case = self.get_case(case_id)
        transport_name = case.get("transport_scenario")
        utilities_raw  = case.get("utilities") or []
        # utilities may come back as a string or list depending on serializer
        if isinstance(utilities_raw, str):
            utilities_raw = [utilities_raw] if utilities_raw else []

        return {
            "case_name":      case.get("name"),
            "source_name":    case.get("source"),
            "sink_name":      case.get("sink"),
            "region":         case.get("region"),
            "root_case_path": None,
            "source":         self._component_spec("source",    case.get("source")),
            "sink":           self._component_spec("sink",      case.get("sink")),
            "transport":      self._component_spec("transport", transport_name),
            "utilities":      [
                self._component_spec("utility", u)
                for u in utilities_raw
                if u
            ],
            "tea_general":    None,
            "import_issues":  [],
        }

    def build_scenario_spec(self, scenario_id: int) -> dict:
        """
        Fetch ``GET /api/v2/scenarios/{scenario_id}/`` and return a
        ``ScenarioSpec``-shaped nested dict.

        ``process``, ``adsorption_scenario``, ``process_preview`` and the
        compiled science sub-objects are not stored on the remote Django
        models; they are returned as ``None``.

        Args:
            scenario_id: PK of the ``Scenario`` record.

        Returns:
            ``dict`` matching the ``ScenarioSpec`` schema::

                {
                  "scenario_name": str,
                  "case_name": str,
                  "source_name": None,   # not on Scenario model
                  "sink_name": None,
                  "region": None,
                  "process": None,
                  "adsorption_scenario": None,
                  "process_preview": None,
                  "utilities": [],
                  "tea_general": None,
                  "import_issues": []
                }
        """
        scenario = self.get_scenario(scenario_id)
        return {
            "scenario_name":       scenario.get("name"),
            "case_name":           scenario.get("case_study_name"),
            "source_name":         None,
            "sink_name":           None,
            "region":              None,
            "process":             None,
            "adsorption_scenario": None,
            "process_preview":     None,
            "utilities":           [],
            "tea_general":         None,
            "import_issues":       [],
        }

    def build_case_pack(self, case_id: int,
                        scenario_id: int | None = None) -> dict:
        """
        Assemble an ``ImportedCasePack``-shaped nested dict for a single case,
        using two remote calls:

        * ``GET /api/v2/cases/{case_id}/``
        * ``GET /api/v2/scenarios/?case_id={case_id}``  *(or a specific scenario)*

        The result conforms to the ``ImportedCasePack`` JSON contract::

            {
              "pack_root": None,
              "case_spec": { CaseSpec },
              "scenario_spec": { ScenarioSpec } | None,
              "available_documents": [],
              "import_issues": []
            }

        ``pack_root``, ``available_documents``, and per-document ``sections``/
        ``scalar_entries`` sub-trees are not stored on the remote Django models;
        they are returned as ``None`` / ``[]``.  The caller can merge in locally
        scanned document data if needed.

        Args:
            case_id:     PK of the ``CaseStudy`` record.
            scenario_id: Optional specific ``Scenario`` PK.  When omitted the
                         first scenario found for the case is used (if any).
                         Pass ``-1`` to suppress scenario resolution entirely
                         and always return ``scenario_spec: null``.

        Returns:
            Nested ``dict`` matching the ``ImportedCasePack`` spec.
        """
        case_spec = self.build_case_spec(case_id)

        scenario_spec: dict | None = None
        if scenario_id != -1:
            if scenario_id is not None:
                scenario_spec = self.build_scenario_spec(scenario_id)
            else:
                # Resolve the first available scenario for this case
                raw = self._get("/scenarios/", {"case_id": case_id, "limit": 1, "offset": 0})
                results = raw.get("results", [])
                if results:
                    sid = results[0]["id"]
                    scenario_spec = self.build_scenario_spec(sid)

        return {
            "pack_root":           None,
            "case_spec":           case_spec,
            "scenario_spec":       scenario_spec,
            "available_documents": [],
            "import_issues":       [],
        }

    def list_case_packs(self,
                        source: str | None = None,
                        sink: str | None = None,
                        region: str | None = None,
                        study: str | None = None,
                        include_scenarios: bool = False,
                        limit: int = 100,
                        offset: int = 0) -> list[dict]:
        """
        Return a list of ``ImportedCasePack``-shaped dicts for every matching
        case, using ``GET /api/v2/cases/``.

        By default ``scenario_spec`` is ``null`` for every record to keep the
        response lightweight.  Set ``include_scenarios=True`` to resolve the
        first scenario for each case (one extra GET per case).

        Args:
            source:            Source name substring filter.
            sink:              Sink name substring filter.
            region:            Exact region ISO code filter.
            study:             Exact study label filter.
            include_scenarios: If ``True``, attach ``scenario_spec`` for each
                               case (N+1 requests — use with small result sets).
            limit:             Max cases to return (default 100).
            offset:            Pagination offset.

        Returns:
            ``list[dict]`` — each element is an ``ImportedCasePack`` dict.
        """
        params = _compact(source=source, sink=sink, region=region,
                          study=study, limit=limit, offset=offset)
        raw_cases = self._get("/cases/", params).get("results", [])

        packs: list[dict] = []
        for case in raw_cases:
            case_id = case["id"]
            transport_name = case.get("transport_scenario")
            utilities_raw  = case.get("utilities") or []
            if isinstance(utilities_raw, str):
                utilities_raw = [utilities_raw] if utilities_raw else []

            case_spec: dict = {
                "case_name":      case.get("name"),
                "source_name":    case.get("source"),
                "sink_name":      case.get("sink"),
                "region":         case.get("region"),
                "root_case_path": None,
                "source":         self._component_spec("source",    case.get("source")),
                "sink":           self._component_spec("sink",      case.get("sink")),
                "transport":      self._component_spec("transport", transport_name),
                "utilities":      [
                    self._component_spec("utility", u)
                    for u in utilities_raw if u
                ],
                "tea_general":    None,
                "import_issues":  [],
            }

            scenario_spec: dict | None = None
            if include_scenarios:
                raw = self._get("/scenarios/", {"case_id": case_id, "limit": 1})
                results = raw.get("results", [])
                if results:
                    sid = results[0]["id"]
                    sc  = results[0]
                    scenario_spec = {
                        "scenario_name":       sc.get("name"),
                        "case_name":           sc.get("case_study_name"),
                        "source_name":         None,
                        "sink_name":           None,
                        "region":              None,
                        "process":             None,
                        "adsorption_scenario": None,
                        "process_preview":     None,
                        "utilities":           [],
                        "tea_general":         None,
                        "import_issues":       [],
                    }

            packs.append({
                "pack_root":           None,
                "case_spec":           case_spec,
                "scenario_spec":       scenario_spec,
                "available_documents": [],
                "import_issues":       [],
            })

        return packs

    def get_screening_summaries(self, scenario_id: int | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/screening-summaries/

        Args:
            scenario_id: Exact scenario PK filter.
        """
        params = _compact(scenario_id=scenario_id, limit=limit, offset=offset)
        return self._to_df(self._get("/screening-summaries/", params))

    def get_screening_summary(self, summary_id: int) -> dict:
        """GET /api/v2/screening-summaries/{summary_id}/"""
        return self._get(f"/screening-summaries/{summary_id}/")


# ── Module-level helper ───────────────────────────────────────────────────────

def _compact(**kwargs) -> dict:
    """Return kwargs dict with None values removed."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _json_safe(value: Any) -> Any:
    """
    Recursively convert *value* into something ``json.dumps(allow_nan=False)``
    accepts: NaN/±inf/``pd.NA``/``NaT`` -> None, numpy scalars and arrays ->
    Python values, timestamps -> ISO strings.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    tolist = getattr(value, "tolist", None)  # numpy scalars and arrays
    if callable(tolist):
        return _json_safe(tolist())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _git_output(args: list[str], cwd: Path) -> str | None:
    """Run ``git <args>`` in *cwd*; return stripped stdout, or None on failure."""
    try:
        cp = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if cp.returncode != 0:
        return None
    return cp.stdout.strip() or None


def _strip_url_credentials(url: str) -> str:
    """Drop ``user:token@`` from an http(s) remote URL (CI checkouts embed tokens)."""
    parts = urlsplit(url)
    if parts.scheme in ("http", "https") and "@" in parts.netloc:
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit(parts._replace(netloc=host))
    return url


def _as_material_names(value: str | list[str] | None) -> list[str]:
    """Normalise a name argument to a list of non-empty names."""
    if value is None:
        return []
    items = [value] if isinstance(value, str) else list(value)
    names = [str(v).strip() for v in items if str(v).strip()]
    return names


def _as_material_ids(value: int | list[int] | None) -> list[int]:
    """Normalise an id argument to a list of ints."""
    if value is None:
        return []
    items = [value] if isinstance(value, (int, str)) else list(value)
    ids: list[int] = []
    for item in items:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            raise ValueError(f"Material ids must be integers; got {item!r}.") from None
    return ids


def _join_sections(value: str | list[str] | None, param: str) -> str | None:
    """Validate section names and join them into a comma-separated query value."""
    if value is None:
        return None
    items = value.split(",") if isinstance(value, str) else list(value)
    names = [str(v).strip() for v in items if str(v).strip()]
    unknown = [n for n in names if n not in _BUNDLE_SECTIONS]
    if unknown:
        raise ValueError(
            f"Unknown section name(s) in '{param}': {unknown}. "
            f"Valid sections: {list(_BUNDLE_SECTIONS)}"
        )
    return ",".join(names) or None


def _prepare_bundle(bundle: Any, index: int, strip_ids: bool = False,
                    tag_names: dict[int, str] | None = None) -> dict:
    """
    Validate one bundle for upsert and return a copy safe to send.

    Rejects unknown section names and populated read-only sections locally,
    rather than letting the server reject the whole bundle, and optionally
    strips the ids and translates the tag ids that are local to one database.
    """
    if not isinstance(bundle, dict):
        raise TypeError(f"bundles[{index}] must be a dict, got {type(bundle).__name__}")

    known = {"material", *_BUNDLE_WRITABLE_SECTIONS, *_BUNDLE_READONLY_SECTIONS,
             *_BUNDLE_IGNORED_KEYS}
    unknown = [k for k in bundle if k not in known]
    if unknown:
        raise ValueError(
            f"Unknown key(s) in bundles[{index}]: {unknown}. "
            f"Writable sections: {list(_BUNDLE_WRITABLE_SECTIONS)}"
        )

    for section, endpoint in _BUNDLE_READONLY_SECTIONS.items():
        if bundle.get(section):
            raise ValueError(
                f"bundles[{index}]['{section}'] is read-only on the bundle "
                f"endpoint — write it with api.v2.{endpoint}(). An empty "
                "section is fine and passes through as a no-op."
            )

    prepared = copy.deepcopy(bundle)
    material = prepared.get("material")
    if not isinstance(material, dict) or not (material.get("id") or material.get("name")):
        raise ValueError(
            f"bundles[{index}] needs a 'material' with an 'id' or a 'name'."
        )

    if strip_ids:
        # Row ids are local to the database the bundle was read from; without
        # them each row falls back to its natural key, which is what makes the
        # same payload safe to apply anywhere.
        material.pop("id", None)
        if not material.get("name"):
            raise ValueError(
                f"bundles[{index}]['material'] needs a 'name' once ids are stripped."
            )
        for section in _BUNDLE_WRITABLE_SECTIONS:
            value = prepared.get(section)
            if isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        row.pop("id", None)
            elif isinstance(value, dict):
                value.pop("id", None)

    for row in prepared.get("water_kpis") or []:
        if isinstance(row, dict) and isinstance(row.get("tags"), list):
            row["tags"] = _translate_tags(row["tags"], tag_names, index, strip_ids)

    return prepared


def _translate_tags(tags: list, tag_names: dict[int, str] | None, index: int,
                    strip_ids: bool) -> list:
    """Map integer tag ids to names where possible; ids are database-local."""
    translated = []
    untranslated = []
    for tag in tags:
        if isinstance(tag, int) and not isinstance(tag, bool):
            name = (tag_names or {}).get(tag)
            if name is None:
                untranslated.append(tag)
                translated.append(tag)
            else:
                translated.append(name)
        else:
            translated.append(tag)
    if untranslated and strip_ids:
        raise ValueError(
            f"bundles[{index}]['water_kpis'] carries tag ids {untranslated}, which "
            "are local to the database the bundle was read from and will fail with "
            "'Unknown tag id'. Replace them with tag names, or pass "
            "tag_names={id: name}."
        )
    return translated


def _as_paths(value: str | Path | list) -> list[Path]:
    """Normalise a path argument to a list of Paths."""
    if isinstance(value, (str, Path)):
        return [Path(value)]
    return [Path(v) for v in value]


def _match_cif_row(rows: list, path: Path) -> dict | None:
    """Find the cifs row that names this file, if the bundle already carries one."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        filename = row.get("filename") or row.get("file_url")
        if isinstance(filename, str) and Path(filename).name == path.name:
            if row.get("content") and row.get("file"):
                raise ValueError(
                    f"CIF row for '{path.name}' carries both 'content' and 'file'; "
                    "they are mutually exclusive."
                )
            return row
    return None


# CIF tags that map onto stored ``cifs`` row columns, with the type to coerce to.
_CIF_METADATA_TAGS: dict[str, tuple[str, str]] = {
    "_chemical_formula_sum": ("chemical_formula_sum", "str"),
    "_chemical_formula_structural": ("chemical_formula_structural", "str"),
    "_chemical_name_common": ("chemical_name_common", "str"),
    "_cell_formula_units_Z": ("cell_formula_units_Z", "int"),
    "_cell_volume": ("cell_volume", "float"),
    "_cell_length_a": ("cell_length_a", "float"),
    "_cell_length_b": ("cell_length_b", "float"),
    "_cell_length_c": ("cell_length_c", "float"),
    "_cell_angle_alpha": ("cell_angle_alpha", "float"),
    "_cell_angle_beta": ("cell_angle_beta", "float"),
    "_cell_angle_gamma": ("cell_angle_gamma", "float"),
    "_symmetry_cell_setting": ("symmetry_cell_setting", "str"),
    "_symmetry_space_group_name": ("symmetry_space_group_name", "str"),
    "_symmetry_space_group_name_H-M": ("symmetry_space_group_name_H_M", "str"),
    "_symmetry_space_group_name_Hall": ("symmetry_space_group_name_Hall", "str"),
    "_symmetry_Int_Tables_number": ("symmetry_Int_Tables_number", "int"),
    "_space_group_name_H-M_alt": ("space_group_name_H_M_alt", "str"),
    "_space_group_name_Hall": ("space_group_name_Hall", "str"),
    "_space_group_IT_number": ("space_group_IT_number", "int"),
}
# A file carrying only the legacy ``_symmetry_*`` names still fills the modern
# space group name columns — matching how stored rows are populated. The IT
# number is deliberately not aliased: stored rows leave it unset.
_CIF_SPACE_GROUP_ALIASES = {
    "symmetry_space_group_name_H_M": "space_group_name_H_M_alt",
    "symmetry_space_group_name_Hall": "space_group_name_Hall",
}


def _parse_cif_metadata(text: str) -> dict[str, Any]:
    """
    Derive stored ``cifs`` row metadata from CIF text.

    Reads the tags in ``_CIF_METADATA_TAGS`` and counts the atom-site loop to
    build the chemical formulae. Elements are listed alphabetically with an
    explicit count, which is how the stored rows read
    (``Al86 Na86 O384 Si106``). Tags the file does not carry are simply absent
    from the result.
    """
    fields: dict[str, str] = {}
    symbols: Counter = Counter()
    lines = text.splitlines()
    index, total = 0, len(lines)

    while index < total:
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith(";"):
            # Multi-line text block — skip to its closing semicolon.
            while index < total and not lines[index].strip().startswith(";"):
                index += 1
            index += 1
            continue
        if line == "loop_":
            columns: list[str] = []
            while index < total and lines[index].strip().startswith("_"):
                columns.append(lines[index].strip().split()[0])
                index += 1
            rows: list[str] = []
            while index < total:
                row = lines[index].strip()
                if not row or row == "loop_" or row.startswith(("_", "#", "data_")):
                    break
                rows.append(row)
                index += 1
            # The type symbol column is authoritative; site labels such as
            # 'O2Al' name the site, not the element, so they are a fallback.
            key = next((c for c in ("_atom_site_type_symbol", "_atom_site_label")
                        if c in columns), None)
            if key is not None:
                column = columns.index(key)
                for row in rows:
                    cells = row.split()
                    if len(cells) > column:
                        symbol = _element_symbol(cells[column])
                        if symbol:
                            symbols[symbol] += 1
            continue
        if line.startswith("_"):
            tag, _, value = line.partition(" ")
            if value.strip():
                fields[tag] = value

    metadata: dict[str, Any] = {}
    for tag, (column, kind) in _CIF_METADATA_TAGS.items():
        value = _cif_value(fields.get(tag))
        if value is None:
            continue
        if kind in ("float", "int"):
            number = re.sub(r"\(\d+\)$", "", value)   # drop an uncertainty, e.g. 25.077(3)
            try:
                value = float(number) if kind == "float" else int(float(number))
            except ValueError:
                continue
        metadata[column] = value

    for source, alias in _CIF_SPACE_GROUP_ALIASES.items():
        if source in metadata and alias not in metadata:
            metadata[alias] = metadata[source]

    if symbols:
        descriptive = " ".join(f"{el}{count}" for el, count in sorted(symbols.items()))
        metadata["chemical_formula_descriptive"] = descriptive
        metadata["chemical_formula"] = descriptive.replace(" ", "")
        metadata.setdefault("chemical_formula_sum", descriptive.replace(" ", ""))

    return metadata


def _apply_cif_metadata(row: dict, text: str, mode: bool | str) -> dict:
    """Write derived CIF metadata onto a ``cifs`` row; ``'fill'`` keeps set values."""
    metadata = _parse_cif_metadata(text)
    for column, value in metadata.items():
        if mode == "fill" and row.get(column) is not None:
            continue
        row[column] = value
    return row


def _element_symbol(token: str) -> str | None:
    """Element symbol from an atom-site type symbol or label ('O2-' → 'O')."""
    match = re.match(r"[A-Za-z]{1,2}", token)
    if not match:
        return None
    symbol = match.group(0)
    if len(symbol) == 2 and not symbol[1].islower():
        symbol = symbol[0]
    return symbol[0].upper() + symbol[1:].lower()


def _cif_value(raw: str | None) -> str | None:
    """Unquote a CIF value, treating '?' and '.' as absent."""
    if raw is None:
        return None
    value = raw.strip()
    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
        value = value[1:-1].strip()
    return value or None if value not in ("?", ".") else None


def _bundle_post_body(params: dict) -> dict:
    """
    Convert bundle query params into a JSON body.

    Query strings carry ``include_cif_content`` as ``'true'``/``'false'``; a
    JSON body should carry a real boolean.
    """
    body = dict(params)
    if "include_cif_content" in body:
        body["include_cif_content"] = str(body["include_cif_content"]).lower() == "true"
    return body


def _filename_from_disposition(disposition: str | None) -> str | None:
    """Pull the filename out of a Content-Disposition header, if present."""
    if not disposition:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
    return match.group(1).strip() if match else None
