"""
CI unit tests for the PrISMa v2 REST API surface.

Run with:
    python manage.py test prisma_cloud.tests_api_v2 --verbosity=2

Each test class is self-contained: it creates the minimum database fixtures
it needs in setUp() and tears them down automatically via Django's test runner
transaction rollback.

Authentication:  all requests include HTTP_X_API_KEY=<key>.
"""

import json
import uuid

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import (
    ApiKey,
    MOF, MOF_Element, Element, Molecule,
    Carbon_Isotherm, Water_KPIs,
    Region, RegionCost, Ambient_Parameters,
    Source, Sink, TransportScenario, Utility, Reference,
    CaseStudy, Scenario, OutputKpi,
)


# ── Shared base class ─────────────────────────────────────────────────────────

class V2ApiTestCase(TestCase):
    """
    Base class that wires up:
      - a superuser with an API key
      - a test Client pre-configured with the API-Key header
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="x", is_staff=True, is_superuser=True
        )
        self.api_key = ApiKey.objects.create(user=self.user)
        self.client = Client()
        self.key_header = {"HTTP_X_API_KEY": str(self.api_key.key)}

    # ── convenience helpers ──────────────────────────────────────────────────

    def get(self, path, **params):
        """Authenticated GET with optional query-string params dict."""
        return self.client.get(path, params, **self.key_header)

    def put_json(self, path, data):
        """Authenticated PUT with a JSON body (list or dict)."""
        return self.client.put(
            path,
            data=json.dumps(data),
            content_type="application/json",
            **self.key_header,
        )

    def assertListEnvelope(self, response, min_count=0):
        """Assert the response is a valid list envelope with at least min_count results."""
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertIn("count",   body)
        self.assertIn("results", body)
        self.assertGreaterEqual(body["count"], min_count)
        self.assertIsInstance(body["results"], list)
        return body

    def assertDetail(self, response, expected_keys):
        """Assert 200 and that all expected_keys are present in the response."""
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        for key in expected_keys:
            self.assertIn(key, body, msg=f"Key '{key}' missing from response: {body}")
        return body

    def assertNotFound(self, response):
        self.assertEqual(response.status_code, 404)
        body = json.loads(response.content)
        self.assertIn("detail", body)

    def assertBadRequest(self, response):
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("detail", body)

    def assertForbidden(self, response):
        self.assertEqual(response.status_code, 403)


# ── Authentication ────────────────────────────────────────────────────────────

class AuthenticationTests(V2ApiTestCase):

    def test_missing_api_key_returns_403(self):
        """Requests without X-API-Key header must be rejected."""
        resp = self.client.get("/api/v2/health/")
        self.assertForbidden(resp)

    def test_invalid_api_key_returns_403(self):
        resp = self.client.get(
            "/api/v2/health/",
            HTTP_X_API_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(resp.status_code, 403)

    def test_valid_api_key_accepted(self):
        resp = self.get("/api/v2/health/")
        self.assertEqual(resp.status_code, 200)


# ── Health ────────────────────────────────────────────────────────────────────

class HealthTests(V2ApiTestCase):

    def test_health_returns_ok(self):
        resp = self.get("/api/v2/health/")
        body = json.loads(resp.content)
        self.assertEqual(body["status"], "ok")
        self.assertIn("version", body)

    def test_health_method_not_allowed(self):
        resp = self.client.post("/api/v2/health/", **self.key_header)
        self.assertEqual(resp.status_code, 405)


# ── Materials ─────────────────────────────────────────────────────────────────

class MaterialListTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.mof1 = MOF.objects.create(name="TEST_MOF_ALPHA")
        self.mof2 = MOF.objects.create(name="TEST_MOF_BETA")

    def test_list_returns_envelope(self):
        body = self.assertListEnvelope(self.get("/api/v2/materials/"), min_count=2)

    def test_list_contains_expected_fields(self):
        body = self.assertListEnvelope(self.get("/api/v2/materials/"))
        first = next(r for r in body["results"] if r["name"] == "TEST_MOF_ALPHA")
        self.assertIn("id",      first)
        self.assertIn("name",    first)
        self.assertIn("cif_url", first)

    def test_filter_by_name_substring(self):
        body = self.assertListEnvelope(self.get("/api/v2/materials/", name="ALPHA"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("TEST_MOF_ALPHA", names)
        self.assertNotIn("TEST_MOF_BETA", names)

    def test_pagination_limit(self):
        resp = self.get("/api/v2/materials/", limit=1, offset=0)
        body = json.loads(resp.content)
        self.assertLessEqual(len(body["results"]), 1)

    def test_pagination_offset_advances(self):
        resp_p1 = self.get("/api/v2/materials/", limit=1, offset=0)
        resp_p2 = self.get("/api/v2/materials/", limit=1, offset=1)
        ids_p1  = [r["id"] for r in json.loads(resp_p1.content)["results"]]
        ids_p2  = [r["id"] for r in json.loads(resp_p2.content)["results"]]
        self.assertNotEqual(ids_p1, ids_p2)


class MaterialDetailTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.elem = Element.objects.create(
            symbol="C", name="Carbon", atomic_number=6, atomic_weight=12.011
        )
        self.mof = MOF.objects.create(name="TEST_MOF_DETAIL")
        MOF_Element.objects.create(
            MOF=self.mof, element=self.elem, mass_fraction=0.45
        )

    def test_detail_returns_correct_fields(self):
        body = self.assertDetail(
            self.get(f"/api/v2/materials/{self.mof.pk}/"),
            ["id", "name", "cif_url", "elements"],
        )
        self.assertEqual(body["id"],   self.mof.pk)
        self.assertEqual(body["name"], "TEST_MOF_DETAIL")

    def test_detail_includes_element_composition(self):
        resp = self.get(f"/api/v2/materials/{self.mof.pk}/")
        body = json.loads(resp.content)
        self.assertEqual(len(body["elements"]), 1)
        self.assertEqual(body["elements"][0]["symbol"], "C")

    def test_detail_unknown_id_returns_404(self):
        self.assertNotFound(self.get("/api/v2/materials/999999999/"))


# ── Molecules ─────────────────────────────────────────────────────────────────

class MoleculeTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.mol = Molecule.objects.create(name="CO2")

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/molecules/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/molecules/", name="CO"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("CO2", names)

    def test_detail(self):
        self.assertDetail(
            self.get(f"/api/v2/molecules/{self.mol.pk}/"),
            ["id", "name"],
        )

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/molecules/999999999/"))


# ── Elements ─────────────────────────────────────────────────────────────────

class ElementTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.elem = Element.objects.create(
            symbol="Fe", name="Iron", atomic_number=26, atomic_weight=55.845
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/elements/"), min_count=1)

    def test_filter_by_symbol(self):
        body = self.assertListEnvelope(self.get("/api/v2/elements/", symbol="Fe"))
        symbols = [r["symbol"] for r in body["results"]]
        self.assertIn("Fe", symbols)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/elements/", name="iro"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("Iron", names)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/elements/{self.elem.pk}/"),
            ["id", "symbol", "name", "atomic_number", "atomic_weight"],
        )
        self.assertEqual(body["symbol"], "Fe")

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/elements/999999999/"))


# ── Regions ───────────────────────────────────────────────────────────────────

class RegionTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.region = Region.objects.create(name="United Kingdom", code="GB-TEST")

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/regions/"), min_count=1)

    def test_filter_by_code(self):
        body = self.assertListEnvelope(self.get("/api/v2/regions/", code="GB-TEST"))
        codes = [r["code"] for r in body["results"]]
        self.assertIn("GB-TEST", codes)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/regions/", name="United"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("United Kingdom", names)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/regions/{self.region.pk}/"),
            ["id", "name", "code"],
        )
        self.assertEqual(body["code"], "GB-TEST")

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/regions/999999999/"))


# ── Sources ───────────────────────────────────────────────────────────────────

class SourceTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.source = Source.objects.create(
            name="Test Coal Power Plant", short_name="TCPP"
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/sources/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/sources/", name="Coal"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("Test Coal Power Plant", names)

    def test_detail(self):
        self.assertDetail(
            self.get(f"/api/v2/sources/{self.source.pk}/"),
            ["id", "name", "short_name"],
        )

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/sources/999999999/"))


# ── Sinks ─────────────────────────────────────────────────────────────────────

class SinkTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.sink = Sink.objects.create(name="Test North Sea Storage")

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/sinks/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/sinks/", name="North Sea"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("Test North Sea Storage", names)

    def test_detail(self):
        self.assertDetail(
            self.get(f"/api/v2/sinks/{self.sink.pk}/"),
            ["id", "name"],
        )

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/sinks/999999999/"))


# ── Transport Scenarios ───────────────────────────────────────────────────────

class TransportScenarioTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.ts = TransportScenario.objects.create(name="Test Pipeline 200km")

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/transport-scenarios/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/transport-scenarios/", name="Pipeline")
        )
        names = [r["name"] for r in body["results"]]
        self.assertIn("Test Pipeline 200km", names)

    def test_detail(self):
        self.assertDetail(
            self.get(f"/api/v2/transport-scenarios/{self.ts.pk}/"),
            ["id", "name"],
        )

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/transport-scenarios/999999999/"))


# ── Utilities ─────────────────────────────────────────────────────────────────

class UtilityTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.utility = Utility.objects.create(name="Test Steam")

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/utilities/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/utilities/", name="Steam"))
        names = [r["name"] for r in body["results"]]
        self.assertIn("Test Steam", names)

    def test_detail(self):
        self.assertDetail(
            self.get(f"/api/v2/utilities/{self.utility.pk}/"),
            ["id", "name"],
        )

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/utilities/999999999/"))


# ── References ────────────────────────────────────────────────────────────────

class ReferenceTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.ref = Reference.objects.create(
            Name="IPCC AR6 Test", Doi="10.9999/test-doi-001", Year=2021
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/references/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/references/", name="IPCC"))
        names = [r["Name"] for r in body["results"]]
        self.assertIn("IPCC AR6 Test", names)

    def test_filter_by_doi(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/references/", doi="10.9999/test-doi-001")
        )
        self.assertEqual(body["count"], 1)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/references/{self.ref.pk}/"),
            ["id", "Name", "Doi", "Year"],
        )
        self.assertEqual(body["Doi"], "10.9999/test-doi-001")

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/references/999999999/"))


# ── Isotherms ─────────────────────────────────────────────────────────────────

class IsothermTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.mof  = MOF.objects.create(name="ISO_TEST_MOF")
        self.mol  = Molecule.objects.create(name="CO2_ISO")
        self.iso  = Carbon_Isotherm.objects.create(
            MOF=self.mof, Molecule=self.mol,
            T_ref_K=298.0, sim_or_exp="sim", good_structure=True,
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/isotherms/"), min_count=1)

    def test_list_fields(self):
        body = self.assertListEnvelope(self.get("/api/v2/isotherms/"))
        rec = next(r for r in body["results"] if r["mof"] == "ISO_TEST_MOF")
        for f in ["id", "mof", "molecule", "T_ref_K", "sim_or_exp", "good_structure"]:
            self.assertIn(f, rec)

    def test_filter_by_mof(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/isotherms/", mof="ISO_TEST_MOF")
        )
        mofs = [r["mof"] for r in body["results"]]
        self.assertIn("ISO_TEST_MOF", mofs)

    def test_filter_by_molecule(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/isotherms/", molecule="CO2_ISO")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_filter_sim_or_exp(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/isotherms/", sim_or_exp="sim")
        )
        for r in body["results"]:
            self.assertEqual(r["sim_or_exp"], "sim")

    def test_filter_sim_or_exp_invalid_returns_400(self):
        resp = self.get("/api/v2/isotherms/", sim_or_exp="invalid")
        self.assertBadRequest(resp)

    def test_filter_temperature_range(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/isotherms/", temperature_min=290, temperature_max=310)
        )
        for r in body["results"]:
            self.assertGreaterEqual(r["T_ref_K"], 290)
            self.assertLessEqual(r["T_ref_K"],    310)

    def test_filter_temperature_invalid_returns_400(self):
        resp = self.get("/api/v2/isotherms/", temperature_min="not_a_number")
        self.assertBadRequest(resp)

    def test_filter_good_structure_true(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/isotherms/", good_structure="true")
        )
        for r in body["results"]:
            self.assertTrue(r["good_structure"])


# ── Water KPIs ────────────────────────────────────────────────────────────────

class WaterKpiTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.mof    = MOF.objects.create(name="WATER_TEST_MOF")
        self.mol    = Molecule.objects.create(name="H2O_TEST")
        self.source = Source.objects.create(name="WaterTestSource")
        self.kpi    = Water_KPIs.objects.create(
            MOF=self.mof, Molecule=self.mol, source=self.source,
            sim_or_exp="sim", good_structure=True,
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/water-kpis/"), min_count=1)

    def test_filter_by_mof(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/water-kpis/", mof="WATER_TEST_MOF")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_filter_by_source(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/water-kpis/", source="WaterTestSource")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_filter_sim_or_exp_invalid_returns_400(self):
        resp = self.get("/api/v2/water-kpis/", sim_or_exp="bad")
        self.assertBadRequest(resp)


# ── Output KPIs ───────────────────────────────────────────────────────────────

class OutputKpiReadTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        source   = Source.objects.create(name="KPI_Source")
        sink     = Sink.objects.create(name="KPI_Sink")
        region   = Region.objects.create(name="KPI_Region", code="KR-TEST")
        utility  = Utility.objects.create(name="KPI_Utility")
        ts       = TransportScenario.objects.create(name="KPI_TS")
        self.case = CaseStudy.objects.create(
            name="KPI_Case", source=source, sink=sink,
            region=region, utilities=utility, transport_scenario=ts,
        )
        self.scenario = Scenario.objects.create(
            case_study=self.case, name="kpi_scen", type="TEA"
        )
        self.mof  = MOF.objects.create(name="KPI_MOF")
        self.kpi  = OutputKpi.objects.create(
            scenario=self.scenario, MOF=self.mof,
            purity=0.96, recovery=0.88, good_structure=True,
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/output-kpis/"), min_count=1)

    def test_list_fields(self):
        body = self.assertListEnvelope(self.get("/api/v2/output-kpis/"))
        rec = next(r for r in body["results"] if r.get("mof_name") == "KPI_MOF")
        for f in ["id", "scenario_id", "mof_name", "purity", "recovery"]:
            self.assertIn(f, rec)

    def test_filter_by_scenario_id(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/output-kpis/", scenario_id=self.scenario.pk)
        )
        for r in body["results"]:
            self.assertEqual(r["scenario_id"], self.scenario.pk)

    def test_filter_bad_scenario_id_returns_400(self):
        resp = self.get("/api/v2/output-kpis/", scenario_id="not_a_number")
        self.assertBadRequest(resp)

    def test_filter_by_mof(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/output-kpis/", mof="KPI_MOF")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/output-kpis/{self.kpi.pk}/"),
            ["id", "scenario_id", "mof_name", "purity"],
        )
        self.assertAlmostEqual(body["purity"], 0.96, places=4)

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/output-kpis/999999999/"))


class OutputKpiUpsertTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        source  = Source.objects.create(name="UPS_Source")
        sink    = Sink.objects.create(name="UPS_Sink")
        region  = Region.objects.create(name="UPS_Region", code="UP-TEST")
        utility = Utility.objects.create(name="UPS_Utility")
        ts      = TransportScenario.objects.create(name="UPS_TS")
        case    = CaseStudy.objects.create(
            name="UPS_Case", source=source, sink=sink,
            region=region, utilities=utility, transport_scenario=ts,
        )
        self.scenario = Scenario.objects.create(
            case_study=case, name="ups_scen", type="TEA"
        )
        self.mof = MOF.objects.create(name="UPS_MOF")

    def test_put_creates_new_record(self):
        payload = [{"scenario": self.scenario.pk, "MOF": self.mof.pk, "purity": 0.91}]
        resp = self.put_json("/api/v2/output-kpis/", payload)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["updated"], 0)
        self.assertNotIn("errors", body)

    def test_put_updates_existing_record(self):
        # Create first
        OutputKpi.objects.create(scenario=self.scenario, MOF=self.mof, purity=0.80)
        # Now upsert with new value
        payload = [{"scenario": self.scenario.pk, "MOF": self.mof.pk, "purity": 0.95}]
        resp = self.put_json("/api/v2/output-kpis/", payload)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body["updated"], 1)
        self.assertEqual(body["created"], 0)

    def test_put_single_object_without_list_wrapper(self):
        """API must accept a bare object, not just a list."""
        payload = {"scenario": self.scenario.pk, "MOF": self.mof.pk, "purity": 0.88}
        resp = self.put_json("/api/v2/output-kpis/", payload)
        self.assertIn(resp.status_code, [200, 207])

    def test_put_invalid_record_returns_207_with_errors(self):
        """An invalid FK should not crash the endpoint; errors collected in response."""
        payload = [{"scenario": 999999999, "MOF": self.mof.pk, "purity": 0.91}]
        resp = self.put_json("/api/v2/output-kpis/", payload)
        self.assertEqual(resp.status_code, 207)
        body = json.loads(resp.content)
        self.assertIn("errors", body)
        self.assertGreater(len(body["errors"]), 0)


# ── Region Costs ─────────────────────────────────────────────────────────────

class RegionCostTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.region = Region.objects.create(name="RC_Region", code="RC-TEST")
        self.ref    = Reference.objects.create(Name="RC_Ref", Doi="10.9999/rc-ref")
        self.rc     = RegionCost.objects.create(
            Name="rc_electricity_test",
            Description="Test electricity cost",
            Region=self.region,
            Reference=self.ref,
            Units="EUR_per_MWh",
            Value=0.15,
            Year=2030,
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/region-costs/"), min_count=1)

    def test_filter_by_region_code(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/region-costs/", region="RC-TEST")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/region-costs/", name="electricity")
        )
        self.assertGreaterEqual(body["count"], 1)

    def test_filter_by_year(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/region-costs/", year=2030)
        )
        for r in body["results"]:
            self.assertEqual(r["Year"], 2030)

    def test_filter_bad_year_returns_400(self):
        resp = self.get("/api/v2/region-costs/", year="nan")
        self.assertBadRequest(resp)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/region-costs/{self.rc.pk}/"),
            ["id", "Name", "region", "Units", "Value", "Year"],
        )
        self.assertEqual(body["Value"], 0.15)

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/region-costs/999999999/"))

    def test_put_upsert_update(self):
        payload = [{
            "Name": "rc_electricity_test",
            "Description": "Test electricity cost",
            "Region": self.region.pk,
            "Reference": self.ref.pk,
            "Units": "EUR_per_MWh",
            "Value": 0.18,
            "Year": 2030,
        }]
        resp = self.put_json("/api/v2/region-costs/", payload)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body["updated"], 1)

    def test_put_upsert_create(self):
        payload = [{
            "Name": "rc_new_cost_unique_xyz",
            "Description": "Brand new cost row description unique",
            "Region": self.region.pk,
            "Units": "EUR_per_MWh",
            "Value": 0.22,
            "Year": 2031,
        }]
        resp = self.put_json("/api/v2/region-costs/", payload)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body["created"], 1)


# ── Ambient Parameters ────────────────────────────────────────────────────────

class AmbientParameterTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.ap = Ambient_Parameters.objects.create(
            Name="ambient_temp_test_K",
            Description="Ambient temperature used in TEA test",
            Units="K",
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/ambient-parameters/"), min_count=1)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/ambient-parameters/", name="ambient_temp")
        )
        names = [r["Name"] for r in body["results"]]
        self.assertIn("ambient_temp_test_K", names)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/ambient-parameters/{self.ap.pk}/"),
            ["id", "Name", "Units", "Description"],
        )
        self.assertEqual(body["Name"], "ambient_temp_test_K")

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/ambient-parameters/999999999/"))

    def test_put_upsert_update(self):
        payload = [{
            "Name": "ambient_temp_test_K",
            "Description": "Ambient temperature used in TEA test",
            "Units": "K",
        }]
        resp = self.put_json("/api/v2/ambient-parameters/", payload)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body["updated"], 1)


# ── Cases ─────────────────────────────────────────────────────────────────────

class CaseStudyTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        self.source  = Source.objects.create(name="CS_Source")
        self.sink    = Sink.objects.create(name="CS_Sink")
        self.region  = Region.objects.create(name="CS_Region", code="CS-TEST")
        self.utility = Utility.objects.create(name="CS_Utility")
        self.ts      = TransportScenario.objects.create(name="CS_TS")
        self.case    = CaseStudy.objects.create(
            name="CS_Test_Case",
            source=self.source, sink=self.sink,
            region=self.region, utilities=self.utility,
            transport_scenario=self.ts, study="Analytical",
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/cases/"), min_count=1)

    def test_list_fields(self):
        body = self.assertListEnvelope(self.get("/api/v2/cases/"))
        rec = next(r for r in body["results"] if r["id"] == self.case.pk)
        for f in ["id", "name", "source", "sink", "region", "transport_scenario", "utilities"]:
            self.assertIn(f, rec)

    def test_filter_by_source_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/cases/", source="CS_Source"))
        ids = [r["id"] for r in body["results"]]
        self.assertIn(self.case.pk, ids)

    def test_filter_by_sink_name(self):
        body = self.assertListEnvelope(self.get("/api/v2/cases/", sink="CS_Sink"))
        ids = [r["id"] for r in body["results"]]
        self.assertIn(self.case.pk, ids)

    def test_filter_by_region_code(self):
        body = self.assertListEnvelope(self.get("/api/v2/cases/", region="CS-TEST"))
        ids = [r["id"] for r in body["results"]]
        self.assertIn(self.case.pk, ids)

    def test_filter_by_study(self):
        body = self.assertListEnvelope(self.get("/api/v2/cases/", study="Analytical"))
        ids = [r["id"] for r in body["results"]]
        self.assertIn(self.case.pk, ids)

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/cases/{self.case.pk}/"),
            ["id", "name", "source", "sink", "region"],
        )
        self.assertEqual(body["source"], "CS_Source")
        self.assertEqual(body["region"], "CS-TEST")

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/cases/999999999/"))


# ── Scenarios ─────────────────────────────────────────────────────────────────

class ScenarioTests(V2ApiTestCase):

    def setUp(self):
        super().setUp()
        source  = Source.objects.create(name="SC_Source")
        sink    = Sink.objects.create(name="SC_Sink")
        region  = Region.objects.create(name="SC_Region", code="SC-TEST")
        utility = Utility.objects.create(name="SC_Utility")
        ts      = TransportScenario.objects.create(name="SC_TS")
        self.case = CaseStudy.objects.create(
            name="SC_Case", source=source, sink=sink,
            region=region, utilities=utility, transport_scenario=ts,
        )
        self.scenario = Scenario.objects.create(
            case_study=self.case,
            name="sc_baseline",
            print_name="SC Baseline",
            type="TEA",
        )

    def test_list(self):
        self.assertListEnvelope(self.get("/api/v2/scenarios/"), min_count=1)

    def test_list_fields(self):
        body = self.assertListEnvelope(self.get("/api/v2/scenarios/"))
        rec = next(r for r in body["results"] if r["id"] == self.scenario.pk)
        for f in ["id", "name", "print_name", "type", "case_study_id", "case_study_name"]:
            self.assertIn(f, rec)

    def test_filter_by_case_id(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/scenarios/", case_id=self.case.pk)
        )
        for r in body["results"]:
            self.assertEqual(r["case_study_id"], self.case.pk)

    def test_filter_bad_case_id_returns_400(self):
        resp = self.get("/api/v2/scenarios/", case_id="abc")
        self.assertBadRequest(resp)

    def test_filter_by_name(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/scenarios/", name="baseline")
        )
        names = [r["name"] for r in body["results"]]
        self.assertIn("sc_baseline", names)

    def test_filter_by_type(self):
        body = self.assertListEnvelope(
            self.get("/api/v2/scenarios/", type="TEA")
        )
        for r in body["results"]:
            self.assertEqual(r["type"].upper(), "TEA")

    def test_detail(self):
        body = self.assertDetail(
            self.get(f"/api/v2/scenarios/{self.scenario.pk}/"),
            ["id", "name", "print_name", "type", "case_study_id"],
        )
        self.assertEqual(body["name"], "sc_baseline")
        self.assertEqual(body["case_study_id"], self.case.pk)

    def test_detail_404(self):
        self.assertNotFound(self.get("/api/v2/scenarios/999999999/"))


# ── Error Mapping ─────────────────────────────────────────────────────────────

class ErrorMappingTests(V2ApiTestCase):
    """
    Verify the v2_exception_handler maps domain exceptions to the correct
    HTTP status codes (independent of specific model data).
    """

    def test_404_response_has_detail_key(self):
        resp = self.get("/api/v2/materials/999999999/")
        body = json.loads(resp.content)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", body)
        self.assertIn("999999999", body["detail"])

    def test_400_response_has_detail_key(self):
        resp = self.get("/api/v2/output-kpis/", scenario_id="bad")
        body = json.loads(resp.content)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", body)

    def test_404_message_includes_resource_id(self):
        resp = self.get("/api/v2/cases/999999999/")
        body = json.loads(resp.content)
        self.assertIn("999999999", body["detail"])
