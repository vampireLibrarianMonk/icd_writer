"""Search evaluation ground truth.

Defines query→expected_results pairs for benchmarking retrieval quality.
Ground truth is maintained manually from ICD content — this is the "test suite"
for search quality, analogous to how visual fidelity tests validate rendering.

Add new queries as you encounter real use cases. The eval harness scores
all configured model/chunk/retrieval combinations against this ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RelevanceJudgment:
    """A single query with expected relevant results."""

    query_id: str
    query: str
    # Expected relevant chunks (by content substring or exact chunk_id)
    relevant_texts: list[str]  # Substrings that MUST appear in top-k results
    # Optional: page numbers where answers live
    relevant_pages: list[int] = field(default_factory=list)
    # Optional: document hash (for corpus-level eval)
    document_hash: str | None = None
    # Relevance tier: "must_find" (critical) vs "nice_to_find" (bonus)
    tier: str = "must_find"
    # Category for grouped reporting
    category: str = "general"


# -----------------------------------------------------------------
# Ground truth for NASA LVC ICD (20150010976.pdf)
# -----------------------------------------------------------------

LVC_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="lvc-001",
        query="What is the data rate for LVC telemetry?",
        relevant_texts=["data rate", "telemetry"],
        relevant_pages=[],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="lvc-002",
        query="What interfaces does the LVC system provide?",
        relevant_texts=["interface", "message", "packet"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="lvc-003",
        query="What are the TBD items in the LVC document?",
        relevant_texts=["TBD", "to be determined", "wind"],
        category="tbd",
    ),
    RelevanceJudgment(
        query_id="lvc-004",
        query="revision history of this document",
        relevant_texts=["revision", "change"],
        relevant_pages=[4],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="lvc-005",
        query="electrical power requirements",
        relevant_texts=["power", "electrical"],
        category="requirements",
    ),
]

# -----------------------------------------------------------------
# Ground truth for HSI Spectrometer ICD (HSI_SYS_015G.pdf)
# -----------------------------------------------------------------

HSI_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="hsi-001",
        query="thermal operating limits for the spectrometer",
        relevant_texts=["thermal", "temperature", "limit"],
        relevant_pages=[7],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="hsi-002",
        query="heater circuit specifications",
        relevant_texts=["heater", "thermostat"],
        relevant_pages=[7],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="hsi-003",
        query="detector characteristics",
        relevant_texts=["detector", "germanium"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="hsi-004",
        query="mass and dimensions of the spectrometer",
        relevant_texts=["mass", "dimension", "spectrometer"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="hsi-005",
        query="applicable reference documents",
        relevant_texts=["reference", "document", "applicable"],
        relevant_pages=[2],
        category="metadata",
    ),
]

# -----------------------------------------------------------------
# Ground truth for TSAFE ICD (20130010957.pdf)
# -----------------------------------------------------------------

TSAFE_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="tsafe-001",
        query="conflict detection algorithm",
        relevant_texts=["conflict", "detection", "algorithm"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="tsafe-002",
        query="trajectory prediction accuracy requirements",
        relevant_texts=["trajectory", "prediction", "accuracy"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="tsafe-003",
        query="input data format from radar",
        relevant_texts=["radar", "input", "format"],
        category="interface",
    ),
]

# -----------------------------------------------------------------
# Ground truth for ICESat-2 ATL03 ATBD (ICESat2_ATL03.pdf)
# -----------------------------------------------------------------

ICESAT2_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="ice-001",
        query="What instrument is on the ICESat-2 spacecraft?",
        relevant_texts=["ATLAS", "Advance Topographic Laser Altimeter"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="ice-002",
        query="Who prepared the ATL03 algorithm document?",
        relevant_texts=["Neumann", "NASA GSFC"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="ice-003",
        query="What processing levels does ICESat-2 produce?",
        relevant_texts=["Level 0", "Level 4", "data products"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="ice-004",
        query="How are changes to this document submitted?",
        relevant_texts=["shall be submitted", "SCoRe", "Management Information System"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="ice-005",
        query="What are the TBD items in the ICESat-2 document?",
        relevant_texts=["TBD", "processing", "release date"],
        category="tbd",
    ),
    RelevanceJudgment(
        query_id="ice-006",
        query="What is the purpose of the ATL03 data product?",
        relevant_texts=["geolocated", "photon", "elevation"],
        category="architecture",
    ),
]

# -----------------------------------------------------------------
# Ground truth for IDSS IDD Rev F (IDSS_IDD_RevF.pdf)
# -----------------------------------------------------------------

IDSS_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="idss-001",
        query="What is the docking interface definition?",
        relevant_texts=["IDSS", "docking", "interface"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="idss-002",
        query="Who has configuration management responsibility for IDSS?",
        relevant_texts=["NASA", "Configuration Management"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="idss-003",
        query="What are the pressure seal requirements?",
        relevant_texts=["seal", "concentric", "pressure"],
        relevant_pages=[36],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="idss-004",
        query="How does soft capture work in the docking system?",
        relevant_texts=["soft capture", "petal", "alignment"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="idss-005",
        query="What does 'shall' mean in this document?",
        relevant_texts=["shall", "binding", "requirement", "implemented"],
        relevant_pages=[13],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="idss-006",
        query="What are the TBD items in the IDSS IDD?",
        relevant_texts=["TBD", "To Be Determined", "placeholder"],
        relevant_pages=[63],
        category="tbd",
    ),
    RelevanceJudgment(
        query_id="idss-007",
        query="What is the hard capture system?",
        relevant_texts=["hard capture", "hook", "structural"],
        category="architecture",
    ),
]

# -----------------------------------------------------------------
# Ground truth for NDS IDD Rev C (NDS_IDD_RevC.pdf)
# -----------------------------------------------------------------

NDS_GROUND_TRUTH: list[RelevanceJudgment] = [
    RelevanceJudgment(
        query_id="nds-001",
        query="What is the thermal contact conductance across the docking interface?",
        relevant_texts=["thermal", "conductance", "docking interface"],
        relevant_pages=[21],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="nds-002",
        query="What is the command packet size for host vehicle to NDS?",
        relevant_texts=["packet", "1024", "Bytes"],
        relevant_pages=[76],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="nds-003",
        query="What are the host vehicle requirements for NDS integration?",
        relevant_texts=["host", "requirements", "integrate", "hazards"],
        relevant_pages=[91],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="nds-004",
        query="What future capabilities will the NDS support?",
        relevant_texts=["water transfer", "fuel transfer", "future", "block upgrade"],
        relevant_pages=[51],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="nds-005",
        query="What changes were made in revision C of the NDS IDD?",
        relevant_texts=["removing TBDs", "matured design"],
        relevant_pages=[3],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="nds-006",
        query="What connector is used for the umbilical power and data?",
        relevant_texts=["SSQ22680", "connector", "umbilical"],
        relevant_pages=[51],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="nds-007",
        query="What is the health and status packet rate?",
        relevant_texts=["50 Hz", "health", "periodic"],
        relevant_pages=[76],
        category="interface",
    ),
]

# -----------------------------------------------------------------
# Aggregate all ground truth
# -----------------------------------------------------------------

ALL_GROUND_TRUTH: dict[str, list[RelevanceJudgment]] = {
    "20150010976": LVC_GROUND_TRUTH,
    "HSI_SYS_015G": HSI_GROUND_TRUTH,
    "20130010957": TSAFE_GROUND_TRUTH,
    "ICESat2_ATL03": ICESAT2_GROUND_TRUTH,
    "IDSS_IDD_RevF": IDSS_GROUND_TRUTH,
    "NDS_IDD_RevC": NDS_GROUND_TRUTH,
}


# -----------------------------------------------------------------
# Expanded queries (Series 2-5) for statistical confidence
# -----------------------------------------------------------------

EXPANDED_QUERIES: list[RelevanceJudgment] = [
    # LVC ICD — lvc-006 through lvc-015
    RelevanceJudgment(query_id="lvc-006", query="What is the message code for MsgFlightState?", relevant_texts=["MsgFlightState", "5310"], category="interface"),
    RelevanceJudgment(query_id="lvc-007", query="What message code is assigned to MsgFlightPlan?", relevant_texts=["MsgFlightPlan", "5201"], category="interface"),
    RelevanceJudgment(query_id="lvc-008", query="What operating system platforms are supported by the LVC architecture?", relevant_texts=["Windows", "x86"], category="requirements"),
    RelevanceJudgment(query_id="lvc-009", query="What is the heartbeat message code in the LVC system?", relevant_texts=["heartbeat", "7030"], category="interface"),
    RelevanceJudgment(query_id="lvc-010", query="What primitive data types are defined in the LVC message specification?", relevant_texts=["float", "int", "char"], category="architecture"),
    RelevanceJudgment(query_id="lvc-011", query="What is the message code for MsgTrajectoryIntent?", relevant_texts=["MsgTrajectoryIntent", "5421"], category="interface"),
    RelevanceJudgment(query_id="lvc-012", query="How does the LVC system handle aircraft deletion?", relevant_texts=["MsgDeleteAc", "5202"], category="interface"),
    RelevanceJudgment(query_id="lvc-013", query="What bus protocol is used for LVC messages?", relevant_texts=["1553", "bus"], category="architecture"),
    RelevanceJudgment(query_id="lvc-014", query="What are the SAA threat result outputs in LVC?", relevant_texts=["SAA", "threat"], category="architecture"),
    RelevanceJudgment(query_id="lvc-015", query="How does the LVC system perform conflict detection?", relevant_texts=["conflict", "detection"], category="architecture"),
    # HSI Spectrometer — hsi-006 through hsi-013
    RelevanceJudgment(query_id="hsi-006", query="What is the maximum power for the coldplate heater?", relevant_texts=["coldplate", "heater", "15"], category="requirements"),
    RelevanceJudgment(query_id="hsi-007", query="What is the radiator heater power specification?", relevant_texts=["radiator", "heater", "30"], category="requirements"),
    RelevanceJudgment(query_id="hsi-008", query="What is the role of the IDPU in the spectrometer system?", relevant_texts=["IDPU", "single-point", "electrical"], category="architecture"),
    RelevanceJudgment(query_id="hsi-009", query="From which direction is the spectrometer installed on the spacecraft?", relevant_texts=["installed", "-Z"], category="requirements"),
    RelevanceJudgment(query_id="hsi-010", query="What is the thermal contact resistance at the cryostat mounting interface?", relevant_texts=["contact resistance", "W/K"], category="requirements"),
    RelevanceJudgment(query_id="hsi-011", query="What type of detectors does the spectrometer use?", relevant_texts=["germanium", "detector"], category="architecture"),
    RelevanceJudgment(query_id="hsi-012", query="What is the minimum turn-on temperature for the spectrometer?", relevant_texts=["turn-on", "-30"], category="requirements"),
    RelevanceJudgment(query_id="hsi-013", query="What thermal insulation is used on the spectrometer surfaces?", relevant_texts=["MLI", "surface"], category="requirements"),
    # TSAFE — tsafe-004 through tsafe-010
    RelevanceJudgment(query_id="tsafe-004", query="What triggers a conflict check in the TSAFE system?", relevant_texts=["trigger", "conflict"], category="architecture"),
    RelevanceJudgment(query_id="tsafe-005", query="What types of resolution maneuvers does TSAFE generate?", relevant_texts=["resolution", "maneuver"], category="architecture"),
    RelevanceJudgment(query_id="tsafe-006", query="What input record types does TSAFE accept?", relevant_texts=["input", "record", "type"], category="interface"),
    RelevanceJudgment(query_id="tsafe-007", query="How does TSAFE use flight state data for prediction?", relevant_texts=["MsgFlightState", "trajectory", "prediction"], category="architecture"),
    RelevanceJudgment(query_id="tsafe-008", query="What output messages does the TSAFE system produce?", relevant_texts=["output", "message"], category="interface"),
    RelevanceJudgment(query_id="tsafe-009", query="How does TSAFE receive radar surveillance data?", relevant_texts=["radar", "data"], category="interface"),
    RelevanceJudgment(query_id="tsafe-010", query="What is the tactical separation function of TSAFE?", relevant_texts=["Tactical Separation", "Flight Environment"], category="architecture"),
    # ICESat-2 ATL03 — ice-007 through ice-018
    RelevanceJudgment(query_id="ice-007", query="How does ATL03 identify signal photons from background noise?", relevant_texts=["signal photon", "background", "noise"], category="architecture"),
    RelevanceJudgment(query_id="ice-008", query="What is the Dead Time Compensation algorithm in ATLAS?", relevant_texts=["Dead Time", "Compensation"], category="architecture"),
    RelevanceJudgment(query_id="ice-009", query="How does ICESat-2 perform geolocation of photon events?", relevant_texts=["geolocation", "photon"], category="architecture"),
    RelevanceJudgment(query_id="ice-010", query="What atmospheric delay corrections are applied to ATL03 data?", relevant_texts=["atmosphere", "delay", "correction"], category="architecture"),
    RelevanceJudgment(query_id="ice-011", query="How does the histogram binning algorithm work for photon detection?", relevant_texts=["histogram", "bin"], category="architecture"),
    RelevanceJudgment(query_id="ice-012", query="What tidal models are used in ATL03 processing?", relevant_texts=["tidal", "model"], category="architecture"),
    RelevanceJudgment(query_id="ice-013", query="What is the telemetry window concept in ATLAS photon counting?", relevant_texts=["telemetry", "window"], category="architecture"),
    RelevanceJudgment(query_id="ice-014", query="How is pointing determination performed for ICESat-2?", relevant_texts=["pointing", "determination"], category="architecture"),
    RelevanceJudgment(query_id="ice-015", query="What background noise statistics are computed in ATL03?", relevant_texts=["background", "statistics"], category="architecture"),
    RelevanceJudgment(query_id="ice-016", query="What is the difference between Level 0 and Level 4 data products?", relevant_texts=["Level 0", "Level 4"], category="architecture"),
    RelevanceJudgment(query_id="ice-017", query="What photon counting technique does the ATLAS instrument use?", relevant_texts=["photon counting", "ATLAS"], category="architecture"),
    RelevanceJudgment(query_id="ice-018", query="What are the TBD document numbers in the ATL03 ATBD?", relevant_texts=["TBD", "XXX"], category="tbd"),
    # IDSS IDD Rev F — idss-008 through idss-019
    RelevanceJudgment(query_id="idss-008", query="What are the guide petal specifications for soft capture?", relevant_texts=["guide petal", "soft capture"], category="architecture"),
    RelevanceJudgment(query_id="idss-009", query="What lateral misalignment is tolerated during docking?", relevant_texts=["lateral", "misalignment"], category="requirements"),
    RelevanceJudgment(query_id="idss-010", query="What is the seal-on-seal mating configuration?", relevant_texts=["seal-on-seal", "mating"], category="architecture"),
    RelevanceJudgment(query_id="idss-011", query="What are the mechanical latch striker requirements?", relevant_texts=["latch", "striker"], category="requirements"),
    RelevanceJudgment(query_id="idss-012", query="What is the tunnel housing specification?", relevant_texts=["tunnel", "housing"], category="architecture"),
    RelevanceJudgment(query_id="idss-013", query="What cis-lunar missions does IDSS support?", relevant_texts=["cis-lunar", "Gateway"], category="architecture"),
    RelevanceJudgment(query_id="idss-014", query="What post-contact thrust constraints apply during capture?", relevant_texts=["post-contact", "thrust"], category="requirements"),
    RelevanceJudgment(query_id="idss-015", query="How many concentric pressure seals does the docking interface use?", relevant_texts=["two", "concentric", "seal"], category="requirements"),
    RelevanceJudgment(query_id="idss-016", query="What are the Hard Capture System hook requirements?", relevant_texts=["Hard Capture", "hook"], category="requirements"),
    RelevanceJudgment(query_id="idss-017", query="What dimensional tolerances apply to the IDSS docking ring?", relevant_texts=["dimensional", "tolerance"], category="requirements"),
    RelevanceJudgment(query_id="idss-018", query="Does IDSS support Orion and Human Landing System applications?", relevant_texts=["Orion", "HLS"], category="architecture"),
    RelevanceJudgment(query_id="idss-019", query="What role does the Soft Capture System play in initial alignment?", relevant_texts=["Soft Capture System", "SCS"], category="architecture"),
    # NDS IDD Rev C — nds-008 through nds-019
    RelevanceJudgment(query_id="nds-008", query="What is the thermal conductance range across the NDS interface?", relevant_texts=["conductance", "85", "284"], category="requirements"),
    RelevanceJudgment(query_id="nds-009", query="What document defines the NDS thermal environment?", relevant_texts=["JSC-65970", "thermal"], category="requirements"),
    RelevanceJudgment(query_id="nds-010", query="What are the electrical bonding requirements for NDS?", relevant_texts=["bonding", "electrical"], category="requirements"),
    RelevanceJudgment(query_id="nds-011", query="What is the GSE software interface for NDS?", relevant_texts=["GSE", "software", "interface"], category="interface"),
    RelevanceJudgment(query_id="nds-012", query="What heater power does the NDS system require?", relevant_texts=["heater", "power"], category="requirements"),
    RelevanceJudgment(query_id="nds-013", query="How does the NDS communicate with the host vehicle over 1553 bus?", relevant_texts=["1553", "bus"], category="interface"),
    RelevanceJudgment(query_id="nds-014", query="What hazard control requirements does the host vehicle have for NDS?", relevant_texts=["hazard", "control", "host vehicle"], category="requirements"),
    RelevanceJudgment(query_id="nds-015", query="What is the maximum size of the health and status packet?", relevant_texts=["1024", "bytes", "packet"], category="interface"),
    RelevanceJudgment(query_id="nds-016", query="What is the umbilical connector part number for NDS?", relevant_texts=["SSQ22680", "umbilical"], category="interface"),
    RelevanceJudgment(query_id="nds-017", query="What command packet parameters does the host vehicle send to NDS?", relevant_texts=["command", "packet", "parameter"], category="interface"),
    RelevanceJudgment(query_id="nds-018", query="What fluid transfer capabilities are planned for future NDS upgrades?", relevant_texts=["water", "fuel", "transfer"], category="architecture"),
    RelevanceJudgment(query_id="nds-019", query="What is the health and status transmission frequency for NDS?", relevant_texts=["50", "Hz", "health"], category="interface"),
    # Additional queries for 100+ threshold
    RelevanceJudgment(query_id="lvc-016", query="What is the MsgSaaThreatResults message code?", relevant_texts=["MsgSaaThreatResults", "5830"], category="interface"),
    RelevanceJudgment(query_id="idss-020", query="What revision updates were made in IDSS IDD Rev F?", relevant_texts=["Revision F", "cis-lunar", "resource umbilical"], category="metadata"),
    RelevanceJudgment(query_id="nds-020", query="Who prepared the NDS IDD document?", relevant_texts=["James Lewis", "Project Manager"], category="metadata"),
    RelevanceJudgment(query_id="ice-019", query="What is the SIPS processing system in ICESat-2?", relevant_texts=["SIPS", "Science Investigator", "Processing System"], category="architecture"),
    RelevanceJudgment(query_id="hsi-014", query="What is the cryocooler non-op temperature limit?", relevant_texts=["cryocooler", "non-op", "limit"], category="requirements"),
    RelevanceJudgment(query_id="tsafe-011", query="What is the conflict removal message in TSAFE?", relevant_texts=["Conflict Removal", "rem"], category="interface"),
    # -----------------------------------------------------------------
    # Batch 2: 71 queries (post adversarial review — 4 removed, 7 fixed)
    # -----------------------------------------------------------------
    # LVC — 11 queries (removed batch2_lvc_005 hallucinated, batch2_lvc_013 redundant)
    RelevanceJudgment(query_id="batch2_lvc_001", query="What fields are in the MsgHandshake message structure?", relevant_texts=["MsgHandshake", "Handshake", "5960"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_002", query="How are latitude and longitude represented in MsgFlightState?", relevant_texts=["latitude", "longitude", "MsgFlightState"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_003", query="What is the MsgSetOwnship message used for in LVC?", relevant_texts=["MsgSetOwnship", "5901", "ownship"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_004", query="How does the LVC system distinguish ADS-B from TIS-B flight states?", relevant_texts=["MsgFlightStateADSB", "7010", "MsgFlightStateTISB"], category="architecture"),
    RelevanceJudgment(query_id="batch2_lvc_006", query="What is the coordinate representation for aircraft positions in LVC messages?", relevant_texts=["latitude", "longitude", "decimal"], category="architecture"),
    RelevanceJudgment(query_id="batch2_lvc_007", query="What are the SAA resolution maneuver outputs from the LVC system?", relevant_texts=["MsgSaaResManeuvers", "5831"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_008", query="How does MsgSaaResReroute convey reroute information?", relevant_texts=["MsgSaaResReroute", "5832", "reroute"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_009", query="What navigation mode fields does MsgNavMode contain?", relevant_texts=["MsgNavMode", "5835"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_010", query="What is the structure of the MsgStrwayBands alerting message?", relevant_texts=["MsgStrwayBands", "5841", "bands"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_011", query="How does MsgAcasxuRaTa report resolution advisories?", relevant_texts=["MsgAcasxuRaTa", "5842"], category="interface"),
    RelevanceJudgment(query_id="batch2_lvc_012", query="What altitude fields are in the LVC flight state messages?", relevant_texts=["altitude", "pressureAltitude", "MsgFlightState"], category="interface"),
    # HSI — 12 queries (fixed batch2_hsi_007 generic terms)
    RelevanceJudgment(query_id="batch2_hsi_001", query="How is the cryostat mechanically mounted to the spacecraft?", relevant_texts=["cryostat", "mounting", "flange"], category="architecture"),
    RelevanceJudgment(query_id="batch2_hsi_002", query="What material is used for thermal coupling between spectrometer and spacecraft?", relevant_texts=["aluminum", "coupling", "conduction"], category="architecture"),
    RelevanceJudgment(query_id="batch2_hsi_003", query="How does radiative thermal dissipation work on the spectrometer?", relevant_texts=["radiative", "dissipation", "radiator"], category="architecture"),
    RelevanceJudgment(query_id="batch2_hsi_004", query="Which surface of the spectrometer serves as the bottom radiator?", relevant_texts=["bottom", "radiator", "surface"], category="architecture"),
    RelevanceJudgment(query_id="batch2_hsi_005", query="How is the heater bus power routed through the IDPU?", relevant_texts=["heater bus", "IDPU"], category="interface"),
    RelevanceJudgment(query_id="batch2_hsi_006", query="What thermostatically controlled heater modes are available?", relevant_texts=["thermostatically", "controlled", "heater"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_007", query="What are the programmable power levels for the coldplate heater?", relevant_texts=["programmable", "15W", "coldplate"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_008", query="What is the detector annealing procedure for the spectrometer?", relevant_texts=["detector", "annealing"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_009", query="What is the cool-down control sequence for the HSI cryostat?", relevant_texts=["cool-down", "control", "temperature"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_010", query="Why must the aft antennas be moved during spectrometer integration?", relevant_texts=["aft", "antenna", "moved"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_011", query="From which axis is the spectrometer integrated onto the spacecraft bus?", relevant_texts=["-Z", "direction", "installed"], category="requirements"),
    RelevanceJudgment(query_id="batch2_hsi_012", query="How does the heater prevent the spectrometer from going below cryocooler non-op limit?", relevant_texts=["heater", "cryocooler", "non-op"], category="requirements"),
    # TSAFE — 11 queries (removed batch2_tsafe_001 redundant, fixed tsafe_002/007/012)
    RelevanceJudgment(query_id="batch2_tsafe_002", query="How does the Method field indicate the data source of a TSAFE input?", relevant_texts=["Method", "Triggers", "record"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_003", query="What output codes represent conflict notifications in TSAFE?", relevant_texts=["output", "conflict", "code"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_004", query="How does the Conflict Check boolean work for each TSAFE input type?", relevant_texts=["Conflict Check", "boolean"], category="architecture"),
    RelevanceJudgment(query_id="batch2_tsafe_005", query="What flight plan intent fields does TSAFE consume as input?", relevant_texts=["flight plan", "intent"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_006", query="How does TSAFE encode route-based resolution outputs?", relevant_texts=["resolution", "reroute"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_007", query="How far into the future does TSAFE probe for conflicts?", relevant_texts=["minutes", "future", "conflict"], category="requirements"),
    RelevanceJudgment(query_id="batch2_tsafe_008", query="How are aircraft pairs identified in a TSAFE conflict output record?", relevant_texts=["aircraft", "pair", "conflict"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_009", query="What altitude and speed fields are in the TSAFE flight state input?", relevant_texts=["altitude", "speed", "flight state"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_010", query="How does TSAFE differentiate between lateral and vertical conflicts?", relevant_texts=["lateral", "vertical", "separation"], category="architecture"),
    RelevanceJudgment(query_id="batch2_tsafe_011", query="What waypoint sequence format does TSAFE accept for flight plan inputs?", relevant_texts=["waypoint", "sequence", "flight plan"], category="interface"),
    RelevanceJudgment(query_id="batch2_tsafe_012", query="What track conformance monitoring does TSAFE perform?", relevant_texts=["conformance", "track", "monitor"], category="architecture"),
    # ICESat-2 — 12 queries (removed batch2_ice_012 unverified)
    RelevanceJudgment(query_id="batch2_ice_001", query="What defines the range window for ATLAS photon detection?", relevant_texts=["range window", "start", "stop"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_002", query="How are strong and weak beams configured on ICESat-2?", relevant_texts=["strong", "weak", "beam"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_003", query="What is the reference ground track and how is it used in ATL03?", relevant_texts=["reference ground track", "RGT"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_004", query="What is the laser pulse repetition rate of the ATLAS instrument?", relevant_texts=["pulse", "repetition", "kHz"], category="requirements"),
    RelevanceJudgment(query_id="batch2_ice_005", query="How does the single photon sensitive detector achieve ranging?", relevant_texts=["single photon", "detector", "sensitive"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_006", query="How is solar background noise characterized in ATL03 processing?", relevant_texts=["solar", "background", "noise"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_007", query="What calibration targets are used for ATLAS instrument verification?", relevant_texts=["calibration", "target"], category="requirements"),
    RelevanceJudgment(query_id="batch2_ice_008", query="How is the Digital Elevation Model used in ATL03 photon classification?", relevant_texts=["Digital Elevation Model", "DEM"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_009", query="What geoid model is applied in ATL03 elevation computation?", relevant_texts=["geoid", "elevation"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_010", query="What is the along-track resolution of ATL03 geolocated photons?", relevant_texts=["along-track", "resolution"], category="requirements"),
    RelevanceJudgment(query_id="batch2_ice_011", query="What is the cross-track beam spacing on ICESat-2?", relevant_texts=["cross-track", "spacing"], category="architecture"),
    RelevanceJudgment(query_id="batch2_ice_013", query="What orbit parameters define the ICESat-2 repeat cycle?", relevant_texts=["orbit", "repeat", "cycle"], category="requirements"),
    # IDSS — 13 queries (fixed cross-doc contamination with IDSS-specific terms)
    RelevanceJudgment(query_id="batch2_idss_001", query="What are the IDSS separation spring force requirements for undocking?", relevant_texts=["separation spring", "IDSS", "force"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_002", query="How is the mating plane defined geometrically in the IDSS standard?", relevant_texts=["mating plane", "seal plane", "IDSS"], category="architecture"),
    RelevanceJudgment(query_id="batch2_idss_003", query="What hook stiffness values are specified for IDSS hard capture latches?", relevant_texts=["hook stiffness", "latch"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_004", query="What is the maximum allowable leak rate across the IDSS docking seal?", relevant_texts=["leak rate", "seal", "IDSS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_005", query="What is the IDSS capture envelope geometry for initial contact?", relevant_texts=["capture envelope", "lateral", "IDSS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_006", query="What IDSS relative velocity limits apply during final approach?", relevant_texts=["relative velocity", "limit", "approach"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_007", query="What angular misalignment tolerances are permitted at IDSS contact?", relevant_texts=["angular", "misalignment", "IDSS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_008", query="How is roll alignment ensured between active and passive IDSS vehicles?", relevant_texts=["roll", "alignment", "active"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_009", query="What resource umbilical services does the IDSS docking port provide?", relevant_texts=["resource", "umbilical", "IDSS"], category="interface"),
    RelevanceJudgment(query_id="batch2_idss_010", query="How does IDSS seal verification testing confirm docking integrity?", relevant_texts=["seal", "verification", "IDSS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_011", query="What approach corridor dimensions constrain the IDSS final docking trajectory?", relevant_texts=["approach corridor", "IDSS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_idss_012", query="How does the IDSS accommodate different docking port sizes across programs?", relevant_texts=["docking port", "standardization"], category="architecture"),
    RelevanceJudgment(query_id="batch2_idss_013", query="What load path transfers structural force through the IDSS hard capture mechanism?", relevant_texts=["load path", "structural", "hard capture"], category="architecture"),
    # NDS — 12 queries (fixed batch2_nds_009 cross-doc contamination)
    RelevanceJudgment(query_id="batch2_nds_001", query="What is the latch actuation time requirement for the NDS mechanism?", relevant_texts=["latch", "actuation", "time"], category="requirements"),
    RelevanceJudgment(query_id="batch2_nds_002", query="What is the mechanism stroke length for the NDS capture system?", relevant_texts=["mechanism", "stroke", "NDS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_nds_003", query="How do the NDS alignment guides establish initial contact geometry?", relevant_texts=["alignment guide", "contact", "NDS"], category="architecture"),
    RelevanceJudgment(query_id="batch2_nds_004", query="What sensors detect NDS mate confirmation?", relevant_texts=["sensor", "contact", "capture"], category="interface"),
    RelevanceJudgment(query_id="batch2_nds_005", query="What structural loads must the NDS interface withstand?", relevant_texts=["structural load", "NDS", "interface"], category="requirements"),
    RelevanceJudgment(query_id="batch2_nds_006", query="What bolt preload specifications secure the NDS structural connection?", relevant_texts=["bolt", "preload", "NDS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_nds_007", query="How many connector pins are in the NDS umbilical interface?", relevant_texts=["connector", "pin", "umbilical"], category="interface"),
    RelevanceJudgment(query_id="batch2_nds_008", query="What signal definitions are carried across the NDS docking interface?", relevant_texts=["signal", "definition", "NDS"], category="interface"),
    RelevanceJudgment(query_id="batch2_nds_009", query="What is the NDS power bus voltage specification?", relevant_texts=["28V", "NDS", "power"], category="interface"),
    RelevanceJudgment(query_id="batch2_nds_010", query="What current limits are imposed on NDS power circuits?", relevant_texts=["current", "limit", "NDS"], category="requirements"),
    RelevanceJudgment(query_id="batch2_nds_011", query="How is the grounding scheme implemented across the NDS interface?", relevant_texts=["grounding", "scheme", "NDS"], category="interface"),
    RelevanceJudgment(query_id="batch2_nds_012", query="What cable routing constraints apply to the NDS docking mechanism?", relevant_texts=["cable", "routing", "NDS"], category="interface"),
]


# -----------------------------------------------------------------
# Batch 3: 80 queries for statistical confidence (250 total target)
# -----------------------------------------------------------------

BATCH3_QUERIES: list[RelevanceJudgment] = [
    # LVC ICD — 14 queries
    RelevanceJudgment(
        query_id="batch3_lvc_001",
        query="What is the message code for MsgSaaFlightState?",
        relevant_texts=["MsgSaaFlightState", "5833"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_002",
        query="What message code is assigned to MsgSaaRelease?",
        relevant_texts=["MsgSaaRelease", "5834"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_003",
        query="What is the MsgTrialTrajectoryIntent message code in the LVC system?",
        relevant_texts=["MsgTrialTrajectoryIntent", "5454"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_004",
        query="What message code identifies MsgSaaTrialThreatResults?",
        relevant_texts=["MsgSaaTrialThreatResults", "5839"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_005",
        query="What is the MsgSaaRecapManeuver message and its code?",
        relevant_texts=["MsgSaaRecapManeuver", "5840"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_006",
        query="What message code is used for MsgTrialAccepted?",
        relevant_texts=["MsgTrialAccepted", "5452"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_007",
        query="What is the MsgSaaBands message code in the LVC alerting system?",
        relevant_texts=["MsgSaaBands", "5843"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_008",
        query="What is the m_callSign field in LVC message structures?",
        relevant_texts=["m_callSign", "MsgFlightState"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_009",
        query="How is aircraft ID represented in LVC struct fields?",
        relevant_texts=["m_acId", "aircraft"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_010",
        query="What ground speed field is in the LVC flight state struct?",
        relevant_texts=["m_groundSpeed", "MsgFlightState"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_011",
        query="How is vertical speed encoded in LVC message structures?",
        relevant_texts=["m_verticalSpeed", "flight state"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_012",
        query="What heading field is defined in the LVC state message struct?",
        relevant_texts=["m_heading", "MsgFlightState"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_013",
        query="How are data sizes defined in the LVC message specification?",
        relevant_texts=["bytes", "data size"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_lvc_014",
        query="What latitude and longitude struct fields are in SAA flight state?",
        relevant_texts=["m_latitude", "m_longitude", "MsgSaaFlightState"],
        category="interface",
    ),
    # HSI Spectrometer — 13 queries
    RelevanceJudgment(
        query_id="batch3_hsi_001",
        query="What is the revision history of the HSI ICD from Rev A through G?",
        relevant_texts=["Rev A", "Rev G", "revision"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_002",
        query="Who is the author of the HSI spectrometer ICD?",
        relevant_texts=["Dave Pankow", "author"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_003",
        query="What company is the spacecraft contractor for the HSI mission?",
        relevant_texts=["Spectrum Astro", "spacecraft contractor"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_004",
        query="Which institution is responsible for the HSI instrument team?",
        relevant_texts=["UC Berkeley", "instrument team"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_005",
        query="What is the spectrometer mass allocation in the HSI ICD?",
        relevant_texts=["mass allocation", "spectrometer"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_006",
        query="What vibration environment requirements apply to the HSI spectrometer?",
        relevant_texts=["vibration environment", "spectrometer"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_007",
        query="What contamination control requirements are specified for HSI?",
        relevant_texts=["contamination control", "spectrometer"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_008",
        query="What is the optical alignment budget for the HSI spectrometer?",
        relevant_texts=["optical alignment", "budget"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_009",
        query="How many revisions has the HSI ICD undergone?",
        relevant_texts=["Rev A", "Rev B", "Rev G"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_010",
        query="What dates are associated with HSI ICD revision releases?",
        relevant_texts=["revision", "date", "history"],
        category="metadata",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_011",
        query="What random vibration levels must the spectrometer survive?",
        relevant_texts=["random vibration", "spectrometer"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_012",
        query="What particulate contamination limits apply to HSI optical surfaces?",
        relevant_texts=["particulate", "contamination", "optical"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_hsi_013",
        query="What alignment accuracy is required between spectrometer and spacecraft?",
        relevant_texts=["alignment", "accuracy", "spectrometer"],
        category="requirements",
    ),
    # TSAFE — 13 queries
    RelevanceJudgment(
        query_id="batch3_tsafe_001",
        query="What is the conflict probe lookahead time in TSAFE?",
        relevant_texts=["conflict probe", "lookahead"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_002",
        query="How does dead reckoning projection work in TSAFE?",
        relevant_texts=["dead reckoning", "projection"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_003",
        query="How does TSAFE perform state vector extrapolation?",
        relevant_texts=["state vector", "extrapolation"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_004",
        query="What minimum separation distance triggers a TSAFE conflict?",
        relevant_texts=["minimum separation", "distance"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_005",
        query="How are conflict start and end times computed in TSAFE?",
        relevant_texts=["conflict start", "end time"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_006",
        query="What conflict geometry types does TSAFE classify?",
        relevant_texts=["crossing", "converging", "parallel"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_007",
        query="What alert threshold parameters are defined in TSAFE?",
        relevant_texts=["alert threshold", "conflict"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_008",
        query="How does TSAFE distinguish crossing conflicts from converging conflicts?",
        relevant_texts=["crossing", "converging", "geometry"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_009",
        query="What dead reckoning assumptions does TSAFE use for aircraft projection?",
        relevant_texts=["dead reckoning", "aircraft", "projection"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_010",
        query="How does TSAFE extrapolate current state vectors into the future?",
        relevant_texts=["state vector", "extrapolation", "future"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_011",
        query="What parallel conflict geometry criteria are used in TSAFE?",
        relevant_texts=["parallel", "conflict geometry"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_012",
        query="How does the conflict probe determine time-to-loss-of-separation?",
        relevant_texts=["conflict probe", "loss of separation"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_tsafe_013",
        query="What state information does TSAFE use to compute minimum separation?",
        relevant_texts=["minimum separation", "state vector"],
        category="architecture",
    ),
    # ICESat-2 ATL03 — 13 queries
    RelevanceJudgment(
        query_id="batch3_ice_001",
        query="How is Precise Orbit Determination performed for ICESat-2?",
        relevant_texts=["Precise Orbit Determination", "orbit determination"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_002",
        query="What is the Precision Pointing Determination system on ICESat-2?",
        relevant_texts=["Precision Pointing Determination", "pointing determination"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_003",
        query="How are spacecraft attitude quaternions used in ATL03?",
        relevant_texts=["attitude quaternion", "spacecraft"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_004",
        query="What star tracker data feeds into ICESat-2 pointing?",
        relevant_texts=["star tracker", "pointing"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_005",
        query="How does the GPS receiver contribute to ICESat-2 orbit determination?",
        relevant_texts=["GPS receiver", "orbit"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_006",
        query="What is the laser reference system on ICESat-2?",
        relevant_texts=["laser reference system", "ATLAS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_007",
        query="How is the beam reference frame defined for ATLAS?",
        relevant_texts=["beam reference frame", "ATLAS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_008",
        query="How are ellipsoidal heights computed in ATL03?",
        relevant_texts=["ellipsoidal height", "ATL03"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_009",
        query="What transmit time tags are recorded by the ATLAS instrument?",
        relevant_texts=["transmit time", "time tag"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_010",
        query="How are receive time tags used in ATL03 photon geolocation?",
        relevant_texts=["receive time", "time tag", "geolocation"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_011",
        query="What optical path delay corrections are applied in ATL03?",
        relevant_texts=["optical path delay", "correction"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_012",
        query="What is the detector response function for ATLAS photon counting?",
        relevant_texts=["detector response function", "ATLAS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_ice_013",
        query="How do attitude quaternions relate to the laser reference system?",
        relevant_texts=["quaternion", "laser reference system"],
        category="architecture",
    ),
    # IDSS IDD Rev F — 13 queries
    RelevanceJudgment(
        query_id="batch3_idss_001",
        query="What is the IDSS active docking system architecture?",
        relevant_texts=["active docking", "IDSS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_002",
        query="What defines the IDSS passive docking system?",
        relevant_texts=["passive docking", "IDSS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_003",
        query="What is the capture ring diameter specified in the IDSS standard?",
        relevant_texts=["capture ring", "diameter", "IDSS"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_004",
        query="How many guide petals are in the IDSS soft capture system?",
        relevant_texts=["guide petal", "three", "IDSS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_005",
        query="What is the IDSS attenuation system for docking energy management?",
        relevant_texts=["attenuation system", "IDSS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_006",
        query="What kinetic energy absorption requirements apply to IDSS docking?",
        relevant_texts=["kinetic energy", "absorption", "IDSS"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_007",
        query="What are the IDSS vestibule pressurization requirements after hard capture?",
        relevant_texts=["vestibule pressurization", "IDSS"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_008",
        query="What are the IDSS hatch opening dimensions for crew transfer?",
        relevant_texts=["hatch opening", "IDSS", "crew"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_009",
        query="What crew transfer corridor dimensions does the IDSS standard specify?",
        relevant_texts=["crew transfer corridor", "IDSS"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_010",
        query="What utility connections are provided through the IDSS interface?",
        relevant_texts=["utility connections", "IDSS"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_011",
        query="How does the IDSS attenuation system absorb approach kinetic energy?",
        relevant_texts=["attenuation", "kinetic energy", "IDSS"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_012",
        query="What pressurization verification is required before IDSS hatch opening?",
        relevant_texts=["pressurization", "hatch", "IDSS"],
        category="requirements",
    ),
    RelevanceJudgment(
        query_id="batch3_idss_013",
        query="How does the IDSS capture ring guide initial vehicle alignment?",
        relevant_texts=["capture ring", "alignment", "IDSS"],
        category="architecture",
    ),
    # NDS IDD Rev C — 14 queries
    RelevanceJudgment(
        query_id="batch3_nds_001",
        query="What is the iLIDS heritage for the NDS design?",
        relevant_texts=["iLIDS", "heritage", "docking system"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_002",
        query="What is the NDS soft capture ring mechanism?",
        relevant_texts=["soft capture ring", "NASA Docking"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_003",
        query="How does the NDS hard dock ring achieve structural connection?",
        relevant_texts=["hard dock ring", "NASA Docking System"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_004",
        query="What pyrotechnic separation capability does the NDS provide?",
        relevant_texts=["pyrotechnic separation", "NASA Docking"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_005",
        query="How does NDS umbilical mate and demate work?",
        relevant_texts=["umbilical mate", "demate", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_006",
        query="What fluid quick disconnect connectors does the NDS use?",
        relevant_texts=["fluid quick disconnect", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_007",
        query="What data bus architecture connects the NDS to the host vehicle?",
        relevant_texts=["data bus architecture", "NASA Docking System"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_008",
        query="What command and telemetry format does the NDS system use?",
        relevant_texts=["command/telemetry", "format", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_009",
        query="What motor controller drives the NDS capture mechanism?",
        relevant_texts=["motor controller", "NASA Docking System"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_010",
        query="What position feedback sensor is used in the NDS mechanism?",
        relevant_texts=["position feedback", "sensor", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_011",
        query="What proximity switch detects NDS mechanism states?",
        relevant_texts=["proximity switch", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_012",
        query="How does the NDS pyrotechnic system enable emergency separation?",
        relevant_texts=["pyrotechnic", "emergency", "NASA Docking"],
        category="architecture",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_013",
        query="What fluid transfer lines pass through the NDS quick disconnect interface?",
        relevant_texts=["fluid transfer", "quick disconnect", "NASA Docking"],
        category="interface",
    ),
    RelevanceJudgment(
        query_id="batch3_nds_014",
        query="How does the NDS motor controller interface with the position feedback sensor?",
        relevant_texts=["motor controller", "position feedback", "NASA Docking"],
        category="architecture",
    ),
]


def get_ground_truth_for_document(doc_key: str) -> list[RelevanceJudgment]:
    """Get ground truth queries for a document."""
    return ALL_GROUND_TRUTH.get(doc_key, [])


def get_all_ground_truth() -> list[RelevanceJudgment]:
    """Get all ground truth queries across all documents."""
    all_queries: list[RelevanceJudgment] = []
    for queries in ALL_GROUND_TRUTH.values():
        all_queries.extend(queries)
    all_queries.extend(EXPANDED_QUERIES)
    all_queries.extend(BATCH3_QUERIES)
    return all_queries
