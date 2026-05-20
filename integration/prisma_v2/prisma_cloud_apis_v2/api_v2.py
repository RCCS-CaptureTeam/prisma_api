"""
PrISMa v2-aligned REST API views.

URL surface mirrors the prisma-v2 FastAPI spec documented in
integration/prisma-v2/API_Scoping/current_api_surface.md so that the
external tool can point its RestBackend at this Django service.

Exception mapping matches the v2 convention:
  LookupError / 404  →  HTTP 404
  ValueError         →  HTTP 400
  NotImplementedError→  HTTP 501
  Anything else      →  HTTP 500

All list endpoints return {"count": N, "results": [...]} with optional
query-string filters.  Detail endpoints return the record object directly
or HTTP 404.  Upsert (PUT) endpoints return
{"created": N, "updated": N, "errors": [...]}.

Authentication: every endpoint requires a valid API key (same
APIKeyAuthentication used by the existing api.py surface).
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler as _drf_exception_handler

from .authentication import APIKeyAuthentication
from .models import (
    MOF, Molecule, Element,
    Carbon_Isotherm, Water_KPIs,
    Region, RegionCost, Ambient_Parameters,
    Source, Sink, TransportScenario, Utility, Reference,
    CaseStudy, Scenario,
    OutputKpi,
)
from .serializers_v2 import (
    HealthCheckSerializer,
    MaterialListSerializer, MaterialDetailSerializer,
    MoleculeSerializer, ElementSerializer,
    RegionSerializer, SourceSerializer, SinkSerializer,
    TransportScenarioSerializer, UtilitySerializer, ReferenceSerializer,
    IsothermSerializer, WaterKpiSerializer,
    OutputKpiSerializer, OutputKpiWriteSerializer,
    RegionCostSerializer, RegionCostWriteSerializer,
    AmbientParameterSerializer,
    CaseStudySerializer, ScenarioSerializer,
)

log = logging.getLogger(__name__)

# ── Exception handler (mirrors prisma-v2 FastAPI error mapping) ───────────────

def v2_exception_handler(exc, context):
    """
    Maps domain exceptions to HTTP status codes matching the v2 convention:
      LookupError / KeyError / FileNotFoundError  →  404
      ValueError                                  →  400
      NotImplementedError                         →  501

    Falls back to DRF's default handler for everything else
    (authentication, permission, validation errors keep their usual codes).
    """
    if isinstance(exc, (LookupError, KeyError, FileNotFoundError)):
        return Response(
            {'detail': str(exc)},
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, ValueError):
        return Response(
            {'detail': str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, NotImplementedError):
        return Response(
            {'detail': str(exc) or 'Not implemented.'},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
    return _drf_exception_handler(exc, context)

_AUTH  = [APIKeyAuthentication]
_PERMS = [IsAuthenticated]

API_VERSION = "2.0.0"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _paginate(request: Request, qs) -> dict[str, Any]:
    """Apply limit/offset from query-string and return count+results dict."""
    try:
        limit  = int(request.query_params.get('limit',  500))
        offset = int(request.query_params.get('offset', 0))
    except (ValueError, TypeError):
        limit, offset = 500, 0
    total   = qs.count()
    records = qs[offset: offset + limit]
    return {'count': total, 'offset': offset, 'limit': limit, 'records': records}


def _upsert(
    qs_model,
    items: list[dict],
    lookup_fields: list[str],
    write_serializer_cls,
) -> tuple[list, list, list]:
    """
    Generic upsert helper.  Tries to find an existing record using the
    provided lookup_fields; updates it if found, creates it otherwise.

    Returns (created_list, updated_list, error_list).
    """
    created, updated, errors = [], [], []
    for item in items:
        try:
            lookup = {f: item[f] for f in lookup_fields if f in item}
            if lookup:
                try:
                    instance = qs_model.objects.get(**lookup)
                    ser = write_serializer_cls(instance, data=item, partial=True)
                    if ser.is_valid():
                        ser.save()
                        updated.append(ser.data)
                    else:
                        errors.append({'item': item, 'errors': ser.errors})
                except qs_model.DoesNotExist:
                    ser = write_serializer_cls(data=item)
                    if ser.is_valid():
                        ser.save()
                        created.append(ser.data)
                    else:
                        errors.append({'item': item, 'errors': ser.errors})
            else:
                ser = write_serializer_cls(data=item)
                if ser.is_valid():
                    ser.save()
                    created.append(ser.data)
                else:
                    errors.append({'item': item, 'errors': ser.errors})
        except Exception as exc:
            log.exception("Upsert error for %s", qs_model.__name__)
            errors.append({'item': item, 'error': str(exc)})
    return created, updated, errors


def _upsert_response(created, updated, errors) -> Response:
    body: dict[str, Any] = {
        'created': len(created),
        'updated': len(updated),
    }
    if errors:
        body['errors'] = errors
    http_status = (
        status.HTTP_207_MULTI_STATUS if errors else status.HTTP_200_OK
    )
    return Response(body, status=http_status)


# ── Health ────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def health(request: Request) -> Response:
    """
    GET /api/v2/health/
    Returns service status and version.
    """
    return Response({'status': 'ok', 'version': API_VERSION})


# ── Catalog: materials (MOFs) ─────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_materials(request: Request) -> Response:
    """
    GET /api/v2/materials/
    Query params: name (substring), limit, offset
    """
    qs = MOF.objects.all().order_by('name')
    name = request.query_params.get('name')
    if name:
        qs = qs.filter(name__icontains=name)
    page = _paginate(request, qs)
    ser  = MaterialListSerializer(page['records'], many=True)
    return Response({
        'count':   page['count'],
        'offset':  page['offset'],
        'limit':   page['limit'],
        'results': ser.data,
    })


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_material(request: Request, material_id: int) -> Response:
    """
    GET /api/v2/materials/{material_id}/
    """
    try:
        obj = MOF.objects.prefetch_related(
            'mof_element_set__element'
        ).get(pk=material_id)
    except MOF.DoesNotExist:
        raise LookupError(f"Material '{material_id}' not found.")
    return Response(MaterialDetailSerializer(obj).data)


# ── Catalog: molecules ────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_molecules(request: Request) -> Response:
    """
    GET /api/v2/molecules/
    Query params: name, limit, offset
    """
    qs = Molecule.objects.all().order_by('name')
    name = request.query_params.get('name')
    if name:
        qs = qs.filter(name__icontains=name)
    page = _paginate(request, qs)
    ser  = MoleculeSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_molecule(request: Request, molecule_id: int) -> Response:
    """GET /api/v2/molecules/{molecule_id}/"""
    try:
        obj = Molecule.objects.get(pk=molecule_id)
    except Molecule.DoesNotExist:
        raise LookupError(f"Molecule '{molecule_id}' not found.")
    return Response(MoleculeSerializer(obj).data)


# ── Catalog: elements ─────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_elements(request: Request) -> Response:
    """
    GET /api/v2/elements/
    Query params: symbol, name, limit, offset
    """
    qs = Element.objects.all().order_by('atomic_number')
    if request.query_params.get('symbol'):
        qs = qs.filter(symbol__iexact=request.query_params['symbol'])
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = ElementSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_element(request: Request, element_id: int) -> Response:
    """GET /api/v2/elements/{element_id}/"""
    try:
        obj = Element.objects.get(pk=element_id)
    except Element.DoesNotExist:
        raise LookupError(f"Element '{element_id}' not found.")
    return Response(ElementSerializer(obj).data)


# ── Catalog: regions ──────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_regions(request: Request) -> Response:
    """
    GET /api/v2/regions/
    Query params: code, name, limit, offset
    """
    qs = Region.objects.all().order_by('name')
    if request.query_params.get('code'):
        qs = qs.filter(code__iexact=request.query_params['code'])
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = RegionSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_region(request: Request, region_id: int) -> Response:
    """GET /api/v2/regions/{region_id}/"""
    try:
        obj = Region.objects.get(pk=region_id)
    except Region.DoesNotExist:
        raise LookupError(f"Region '{region_id}' not found.")
    return Response(RegionSerializer(obj).data)


# ── Catalog: sources ──────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_sources(request: Request) -> Response:
    """
    GET /api/v2/sources/
    Query params: name, limit, offset
    """
    qs = Source.objects.all().order_by('name')
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = SourceSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_source(request: Request, source_id: int) -> Response:
    """GET /api/v2/sources/{source_id}/"""
    try:
        obj = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        raise LookupError(f"Source '{source_id}' not found.")
    return Response(SourceSerializer(obj).data)


# ── Catalog: sinks ────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_sinks(request: Request) -> Response:
    """
    GET /api/v2/sinks/
    Query params: name, limit, offset
    """
    qs = Sink.objects.all().order_by('name')
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = SinkSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_sink(request: Request, sink_id: int) -> Response:
    """GET /api/v2/sinks/{sink_id}/"""
    try:
        obj = Sink.objects.get(pk=sink_id)
    except Sink.DoesNotExist:
        raise LookupError(f"Sink '{sink_id}' not found.")
    return Response(SinkSerializer(obj).data)


# ── Catalog: transport-scenarios ─────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_transport_scenarios(request: Request) -> Response:
    """
    GET /api/v2/transport-scenarios/
    Query params: name, limit, offset
    """
    qs = TransportScenario.objects.all().order_by('name')
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = TransportScenarioSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_transport_scenario(request: Request, ts_id: int) -> Response:
    """GET /api/v2/transport-scenarios/{ts_id}/"""
    try:
        obj = TransportScenario.objects.get(pk=ts_id)
    except TransportScenario.DoesNotExist:
        raise LookupError(f"TransportScenario '{ts_id}' not found.")
    return Response(TransportScenarioSerializer(obj).data)


# ── Catalog: utilities ────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_utilities(request: Request) -> Response:
    """
    GET /api/v2/utilities/
    Query params: name, limit, offset
    """
    qs = Utility.objects.all().order_by('name')
    if request.query_params.get('name'):
        qs = qs.filter(name__icontains=request.query_params['name'])
    page = _paginate(request, qs)
    ser  = UtilitySerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_utility(request: Request, utility_id: int) -> Response:
    """GET /api/v2/utilities/{utility_id}/"""
    try:
        obj = Utility.objects.get(pk=utility_id)
    except Utility.DoesNotExist:
        raise LookupError(f"Utility '{utility_id}' not found.")
    return Response(UtilitySerializer(obj).data)


# ── Catalog: references ───────────���───────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_references(request: Request) -> Response:
    """
    GET /api/v2/references/
    Query params: name, doi, limit, offset
    """
    qs = Reference.objects.all().order_by('Name')
    if request.query_params.get('name'):
        qs = qs.filter(Name__icontains=request.query_params['name'])
    if request.query_params.get('doi'):
        qs = qs.filter(Doi__iexact=request.query_params['doi'])
    page = _paginate(request, qs)
    ser  = ReferenceSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_reference(request: Request, ref_id: int) -> Response:
    """GET /api/v2/references/{ref_id}/"""
    try:
        obj = Reference.objects.get(pk=ref_id)
    except Reference.DoesNotExist:
        raise LookupError(f"Reference '{ref_id}' not found.")
    return Response(ReferenceSerializer(obj).data)


# ── Science: isotherms ────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_isotherms(request: Request) -> Response:
    """
    GET /api/v2/isotherms/
    Query params:
      mof           – MOF name (exact or icontains if suffixed with *)
      molecule      – Molecule name
      temperature_min / temperature_max  – T_ref_K range [K]
      sim_or_exp    – 'sim' | 'exp'
      good_structure – true | false
      limit, offset
    """
    qs = Carbon_Isotherm.objects.select_related('MOF', 'Molecule').order_by('id')

    mof = request.query_params.get('mof')
    if mof:
        qs = qs.filter(MOF__name__icontains=mof)

    molecule = request.query_params.get('molecule')
    if molecule:
        qs = qs.filter(Molecule__name__icontains=molecule)

    t_min = request.query_params.get('temperature_min')
    t_max = request.query_params.get('temperature_max')
    if t_min:
        try:
            qs = qs.filter(T_ref_K__gte=float(t_min))
        except ValueError:
            raise ValueError(f"temperature_min must be a number, got '{t_min}'")
    if t_max:
        try:
            qs = qs.filter(T_ref_K__lte=float(t_max))
        except ValueError:
            raise ValueError(f"temperature_max must be a number, got '{t_max}'")

    sim_or_exp = request.query_params.get('sim_or_exp')
    if sim_or_exp:
        if sim_or_exp not in ('sim', 'exp'):
            raise ValueError("sim_or_exp must be 'sim' or 'exp'")
        qs = qs.filter(sim_or_exp=sim_or_exp)

    good = request.query_params.get('good_structure')
    if good is not None:
        qs = qs.filter(good_structure=(good.lower() in ('true', '1', 'yes')))

    page = _paginate(request, qs)
    ser  = IsothermSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


# ── Science: water-kpis ───────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_water_kpis(request: Request) -> Response:
    """
    GET /api/v2/water-kpis/
    Query params: mof, molecule, source, sim_or_exp, good_structure, limit, offset
    """
    qs = Water_KPIs.objects.select_related('MOF', 'Molecule', 'source').order_by('id')

    mof = request.query_params.get('mof')
    if mof:
        qs = qs.filter(MOF__name__icontains=mof)

    molecule = request.query_params.get('molecule')
    if molecule:
        qs = qs.filter(Molecule__name__icontains=molecule)

    source = request.query_params.get('source')
    if source:
        qs = qs.filter(source__name__icontains=source)

    sim_or_exp = request.query_params.get('sim_or_exp')
    if sim_or_exp:
        if sim_or_exp not in ('sim', 'exp'):
            raise ValueError("sim_or_exp must be 'sim' or 'exp'")
        qs = qs.filter(sim_or_exp=sim_or_exp)

    good = request.query_params.get('good_structure')
    if good is not None:
        qs = qs.filter(good_structure=(good.lower() in ('true', '1', 'yes')))

    page = _paginate(request, qs)
    ser  = WaterKpiSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


# ── TEA/LCA: output-kpis ─────────────────────────────────────────────────────

@api_view(['GET', 'PUT'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def output_kpis(request: Request) -> Response:
    """
    GET  /api/v2/output-kpis/
         Query params: scenario_id, mof, good_structure, limit, offset

    PUT  /api/v2/output-kpis/
         Body: list of OutputKpi records (with scenario / MOF as integer PKs).
         Lookup key: (scenario, MOF) — upserts per-record.
    """
    if request.method == 'GET':
        qs = OutputKpi.objects.select_related('scenario', 'MOF').order_by('id')

        scenario_id = request.query_params.get('scenario_id')
        if scenario_id:
            try:
                qs = qs.filter(scenario_id=int(scenario_id))
            except ValueError:
                raise ValueError(f"scenario_id must be an integer, got '{scenario_id}'")

        mof = request.query_params.get('mof')
        if mof:
            qs = qs.filter(MOF__name__icontains=mof)

        good = request.query_params.get('good_structure')
        if good is not None:
            qs = qs.filter(good_structure=(good.lower() in ('true', '1', 'yes')))

        page = _paginate(request, qs)
        ser  = OutputKpiSerializer(page['records'], many=True)
        return Response({'count': page['count'], 'results': ser.data})

    # PUT – upsert
    data = request.data
    if not isinstance(data, list):
        data = [data]
    created, updated, errors = _upsert(
        OutputKpi, data, ['scenario', 'MOF'], OutputKpiWriteSerializer
    )
    return _upsert_response(created, updated, errors)


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_output_kpi(request: Request, kpi_id: int) -> Response:
    """GET /api/v2/output-kpis/{kpi_id}/"""
    try:
        obj = OutputKpi.objects.select_related('scenario', 'MOF').get(pk=kpi_id)
    except OutputKpi.DoesNotExist:
        raise LookupError(f"OutputKpi '{kpi_id}' not found.")
    return Response(OutputKpiSerializer(obj).data)


# ── TEA/LCA: region-costs ─────────────────────────────────────────────────────

@api_view(['GET', 'PUT'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def region_costs(request: Request) -> Response:
    """
    GET  /api/v2/region-costs/
         Query params: region (code), name, year, limit, offset

    PUT  /api/v2/region-costs/
         Body: list of RegionCost records.
         Lookup key: Name (unique) — upserts per-record.
    """
    if request.method == 'GET':
        qs = RegionCost.objects.select_related('Region', 'Reference').order_by('Name')

        region = request.query_params.get('region')
        if region:
            qs = qs.filter(Region__code__iexact=region)

        name = request.query_params.get('name')
        if name:
            qs = qs.filter(Name__icontains=name)

        year = request.query_params.get('year')
        if year:
            try:
                qs = qs.filter(Year=int(year))
            except ValueError:
                raise ValueError(f"year must be an integer, got '{year}'")

        page = _paginate(request, qs)
        ser  = RegionCostSerializer(page['records'], many=True)
        return Response({'count': page['count'], 'results': ser.data})

    # PUT
    data = request.data
    if not isinstance(data, list):
        data = [data]
    created, updated, errors = _upsert(
        RegionCost, data, ['Name'], RegionCostWriteSerializer
    )
    return _upsert_response(created, updated, errors)


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_region_cost(request: Request, rc_id: int) -> Response:
    """GET /api/v2/region-costs/{rc_id}/"""
    try:
        obj = RegionCost.objects.select_related('Region', 'Reference').get(pk=rc_id)
    except RegionCost.DoesNotExist:
        raise LookupError(f"RegionCost '{rc_id}' not found.")
    return Response(RegionCostSerializer(obj).data)


# ── TEA/LCA: ambient-parameters ──────────────────────────────────────────────

@api_view(['GET', 'PUT'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def ambient_parameters(request: Request) -> Response:
    """
    GET  /api/v2/ambient-parameters/
         Query params: name, limit, offset

    PUT  /api/v2/ambient-parameters/
         Body: list of Ambient_Parameters records.
         Lookup key: Name (unique) — upserts per-record.
    """
    if request.method == 'GET':
        qs = Ambient_Parameters.objects.all().order_by('Name')
        name = request.query_params.get('name')
        if name:
            qs = qs.filter(Name__icontains=name)
        page = _paginate(request, qs)
        ser  = AmbientParameterSerializer(page['records'], many=True)
        return Response({'count': page['count'], 'results': ser.data})

    # PUT
    data = request.data
    if not isinstance(data, list):
        data = [data]
    created, updated, errors = _upsert(
        Ambient_Parameters, data, ['Name'], AmbientParameterSerializer
    )
    return _upsert_response(created, updated, errors)


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_ambient_parameter(request: Request, ap_id: int) -> Response:
    """GET /api/v2/ambient-parameters/{ap_id}/"""
    try:
        obj = Ambient_Parameters.objects.get(pk=ap_id)
    except Ambient_Parameters.DoesNotExist:
        raise LookupError(f"AmbientParameter '{ap_id}' not found.")
    return Response(AmbientParameterSerializer(obj).data)


# ── Cases ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_cases(request: Request) -> Response:
    """
    GET /api/v2/cases/
    Query params: source, sink, region, study, limit, offset
    """
    qs = CaseStudy.objects.select_related(
        'source', 'sink', 'transport_scenario', 'region', 'utilities'
    ).order_by('id')

    source = request.query_params.get('source')
    if source:
        qs = qs.filter(source__name__icontains=source)

    sink = request.query_params.get('sink')
    if sink:
        qs = qs.filter(sink__name__icontains=sink)

    region = request.query_params.get('region')
    if region:
        qs = qs.filter(region__code__iexact=region)

    study = request.query_params.get('study')
    if study:
        qs = qs.filter(study__iexact=study)

    page = _paginate(request, qs)
    ser  = CaseStudySerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_case(request: Request, case_id: int) -> Response:
    """GET /api/v2/cases/{case_id}/"""
    try:
        obj = CaseStudy.objects.select_related(
            'source', 'sink', 'transport_scenario', 'region', 'utilities'
        ).get(pk=case_id)
    except CaseStudy.DoesNotExist:
        raise LookupError(f"Case '{case_id}' not found.")
    return Response(CaseStudySerializer(obj).data)


# ── Scenarios ─────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def list_scenarios(request: Request) -> Response:
    """
    GET /api/v2/scenarios/
    Query params: case_id, name, type, limit, offset
    """
    qs = Scenario.objects.select_related('case_study').order_by('id')

    case_id = request.query_params.get('case_id')
    if case_id:
        try:
            qs = qs.filter(case_study_id=int(case_id))
        except ValueError:
            raise ValueError(f"case_id must be an integer, got '{case_id}'")

    name = request.query_params.get('name')
    if name:
        qs = qs.filter(Q(name__icontains=name) | Q(print_name__icontains=name))

    scenario_type = request.query_params.get('type')
    if scenario_type:
        qs = qs.filter(type__iexact=scenario_type)

    page = _paginate(request, qs)
    ser  = ScenarioSerializer(page['records'], many=True)
    return Response({'count': page['count'], 'results': ser.data})


@api_view(['GET'])
@authentication_classes(_AUTH)
@permission_classes(_PERMS)
def get_scenario(request: Request, scenario_id: int) -> Response:
    """GET /api/v2/scenarios/{scenario_id}/"""
    try:
        obj = Scenario.objects.select_related('case_study').get(pk=scenario_id)
    except Scenario.DoesNotExist:
        raise LookupError(f"Scenario '{scenario_id}' not found.")
    return Response(ScenarioSerializer(obj).data)
