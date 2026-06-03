### List of REST-API URLs on prisma_cloud (v2, 2026-05-20)

> "provide list of API urls matching all of the above, no other code just urls. where optional arguments exist, give at least one working example of argument usage"

# Health
GET /api/v2/health/

# Materials (MOFs)
GET /api/v2/materials/
GET /api/v2/materials/?name=HKUST
GET /api/v2/materials/?limit=10&offset=0
GET /api/v2/materials/1/

# Materials PSDI (extended)
GET /api/v2/materials-psdi/
GET /api/v2/materials-psdi/?name=LAGNAK
GET /api/v2/materials-psdi/1/

# Molecules
GET /api/v2/molecules/
GET /api/v2/molecules/?name=CO2
GET /api/v2/molecules/1/

# Elements
GET /api/v2/elements/
GET /api/v2/elements/?symbol=Cu
GET /api/v2/elements/?name=carbon
GET /api/v2/elements/6/

# Regions
GET /api/v2/regions/
GET /api/v2/regions/?code=UK
GET /api/v2/regions/?name=northern
GET /api/v2/regions/1/

# Sources
GET /api/v2/sources/
GET /api/v2/sources/?name=DAC
GET /api/v2/sources/1/

# Sinks
GET /api/v2/sinks/
GET /api/v2/sinks/?name=northern
GET /api/v2/sinks/1/

# Transport Scenarios
GET /api/v2/transport-scenarios/
GET /api/v2/transport-scenarios/?name=pipeline
GET /api/v2/transport-scenarios/1/

# Transport Modes
GET /api/v2/transports/
GET /api/v2/transports/?name=ship
GET /api/v2/transports/1/

# Utilities
GET /api/v2/utilities/
GET /api/v2/utilities/?name=heat
GET /api/v2/utilities/1/

# References
GET /api/v2/references/
GET /api/v2/references/?name=EBTF
GET /api/v2/references/?doi=10.1016/j.ijggc.2011.01.004
GET /api/v2/references/1/

# Subsystems
GET /api/v2/subsystems/
GET /api/v2/subsystems/?name=capture
GET /api/v2/subsystems/?type=dac
GET /api/v2/subsystems/1/

# Equipment
GET /api/v2/equipment/
GET /api/v2/equipment/?name=blower
GET /api/v2/equipment/1/

# Properties
GET /api/v2/properties/
GET /api/v2/properties/?name=pressure
GET /api/v2/properties/?domain=TEA
GET /api/v2/properties/?category=params_amb
GET /api/v2/properties/?object_id=3
GET /api/v2/properties/1/

# TEA Equipment
GET /api/v2/tea-equipment/
GET /api/v2/tea-equipment/?name=Blower
GET /api/v2/tea-equipment/?group=Blower
GET /api/v2/tea-equipment/1/

# TEA Equipment Costs
GET /api/v2/tea-equipment-costs/
GET /api/v2/tea-equipment-costs/?equipment_id=1
GET /api/v2/tea-equipment-costs/1/

# TEA Equipment Design Parameters
GET /api/v2/tea-equipment-designs/
GET /api/v2/tea-equipment-designs/?equipment_id=1
GET /api/v2/tea-equipment-designs/?key=D1
GET /api/v2/tea-equipment-designs/1/

# Process Conditions
GET /api/v2/process-conditions/
GET /api/v2/process-conditions/?name=TVSA01
GET /api/v2/process-conditions/?type=tvsa
GET /api/v2/process-conditions/1/

# Process Configurations
GET /api/v2/process-configurations/
GET /api/v2/process-configurations/?name=dac
GET /api/v2/process-configurations/?type=dac
GET /api/v2/process-configurations/1/

# Contactor Configurations
GET /api/v2/contactor-configurations/
GET /api/v2/contactor-configurations/?name=kiln
GET /api/v2/contactor-configurations/?type=kiln
GET /api/v2/contactor-configurations/1/

# Cost Indices
GET /api/v2/cost-indices/
GET /api/v2/cost-indices/?year=2019
GET /api/v2/cost-indices/1/

# Physical Constants
GET /api/v2/constants/
GET /api/v2/constants/?param=R
GET /api/v2/constants/1/

# MEA Baseline
GET /api/v2/mea/
GET /api/v2/mea/?name=NGCC
GET /api/v2/mea/1/

# MEA KPIs
GET /api/v2/mea-kpis/
GET /api/v2/mea-kpis/?category=CAC
GET /api/v2/mea-kpis/?name=CAPEX
GET /api/v2/mea-kpis/1/

# Isotherms (Carbon_Isotherm)
GET /api/v2/isotherms/
GET /api/v2/isotherms/?mof=HKUST
GET /api/v2/isotherms/?molecule=CO2
GET /api/v2/isotherms/?sim_or_exp=sim
GET /api/v2/isotherms/?good_structure=true
GET /api/v2/isotherms/?temperature_min=273&temperature_max=373

# Water KPIs
GET /api/v2/water-kpis/
GET /api/v2/water-kpis/?mof=HKUST
GET /api/v2/water-kpis/?source=DAC
GET /api/v2/water-kpis/?sim_or_exp=exp
GET /api/v2/water-kpis/?good_structure=true

# Carbon ZeoPP (simulated geometry)
GET /api/v2/carbon-zeopp/
GET /api/v2/carbon-zeopp/?mof=HKUST
GET /api/v2/carbon-zeopp/?good_structure=true
GET /api/v2/carbon-zeopp/1/

# Carbon ZeoPP Experimental
GET /api/v2/carbon-zeopp-experimental/
GET /api/v2/carbon-zeopp-experimental/?mof=HKUST
GET /api/v2/carbon-zeopp-experimental/1/

# Cases (CaseStudy)
GET /api/v2/cases/
GET /api/v2/cases/?source=DAC
GET /api/v2/cases/?sink=northern
GET /api/v2/cases/?region=UK
GET /api/v2/cases/?study=Simulated
GET /api/v2/cases/1/

# Scenarios
GET /api/v2/scenarios/
GET /api/v2/scenarios/?case_id=1
GET /api/v2/scenarios/?name=TVSA
GET /api/v2/scenarios/?type=Simulated
GET /api/v2/scenarios/1/

# Screening Summaries
GET /api/v2/screening-summaries/
GET /api/v2/screening-summaries/?scenario_id=1
GET /api/v2/screening-summaries/1/

# Output KPIs (GET + PUT upsert)
GET  /api/v2/output-kpis/
GET  /api/v2/output-kpis/?scenario_id=1
GET  /api/v2/output-kpis/?mof=HKUST
GET  /api/v2/output-kpis/?good_structure=true
GET  /api/v2/output-kpis/1/
PUT  /api/v2/output-kpis/

# Ambient Parameters / EconomicData (GET + PUT upsert)
GET  /api/v2/ambient-parameters/
GET  /api/v2/ambient-parameters/?name=electricity
GET  /api/v2/ambient-parameters/1/
PUT  /api/v2/ambient-parameters/