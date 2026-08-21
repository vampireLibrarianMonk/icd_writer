"""Generate versioned document series (v1 → v2 → v3+) for lineage testing.

Creates multiple versions of the same source document, each with realistic
incremental changes, dates, and revision markers. These simulate the real
lifecycle of engineering documents feeding into an ICD.

Usage:
    python test_corpus/scripts/generate_versioned_series.py

Output goes to test_corpus/hsi_sys_015g/series/, test_corpus/idss_idd/series/, etc.
Each series has 3-5 versions of the same base document.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# Reuse generation helpers from the main script
import sys
sys.path.insert(0, str(Path(__file__).parent))
from generate_corpus import (
    generate_docx,
    generate_xlsx,
    generate_pptx,
    generate_html,
    generate_page_image,
    generate_region_image,
    generate_tiff_scan,
    ICDS_DIR,
    CORPUS_DIR,
    extract_page_text,
)


# ═══════════════════════════════════════════════════════════════════════
# SERIES 1: HSI Mechanical Requirements (DOCX, 4 versions)
# ═══════════════════════════════════════════════════════════════════════


def generate_hsi_mech_req_series():
    """4 versions of mechanical requirements, evolving over 18 months."""
    out = CORPUS_DIR / "hsi_sys_015g" / "series" / "mech_requirements"

    # v1: Initial draft — baseline requirements
    generate_docx(
        title="HESSI Spectrometer Mechanical Interface Requirements",
        sections=[
            ("Scope", "This document defines the mechanical interface requirements between the HESSI Spacecraft Bus and the Spectrometer instrument assembly. It establishes the physical constraints, mounting interface, mass allocation, and alignment requirements."),
            ("Interface Drawing", "The mechanical configuration of the Spectrometer is shown in the preliminary Spectrometer ICD Drawing. Final drawing to be released after CDR."),
            ("Mass Properties", "The Spectrometer assembly mass allocation is 50 kg maximum. Current best estimate is TBD pending component selection. Mass margin shall be maintained at 20% minimum through CDR."),
            ("Field of View", "The nine detectors must be aligned to be within 2mm of concentric to the field of view of each of the nine grid pairs on the imager. Alignment method TBD."),
            ("Mechanisms", "The Spectrometer contains the following mechanisms:\n- Cryocooler (free piston compressor)\n- Hi-Z Shutters (2x attenuators)\n- Cryostat Vacuum Valve\n\nForce limits for each mechanism are TBD pending vibration analysis."),
        ],
        output_path=out / "HSI_Mech_Requirements_v1.docx",
        author="UCB Mechanical Engineering",
        doc_number="HSI-MECH-REQ-001",
        revision="v1",
        date="2024-01-15",
    )

    # v2: Post-PDR — TBDs partially resolved, mass updated
    generate_docx(
        title="HESSI Spectrometer Mechanical Interface Requirements",
        sections=[
            ("Scope", "This document defines the mechanical interface requirements between the HESSI Spacecraft Bus and the Spectrometer instrument assembly. It establishes the physical constraints, mounting interface, mass allocation, and alignment requirements.\n\nChange from v1: Updated mass properties and alignment requirements based on PDR results."),
            ("Interface Drawing", "The mechanical configuration of the Spectrometer is shown in the Spectrometer ICD Drawing (HSI_SYS_014F). Drawing released 2024-03-01 as part of PDR documentation package."),
            ("Mass Properties", "The Spectrometer assembly mass allocation is 50 kg maximum.\n\nCurrent Best Estimate: 44.5 kg\nMargin: 11.3% (below 20% goal — under review)\n\nComponent breakdown:\n- Cryostat Assembly: 28.5 kg\n- Detector Array (9x): 4.2 kg\n- Cryocooler: 6.8 kg\n- Hi-Z Shutters: 1.06 kg\n- Thermal Hardware: 2.1 kg\n- Harnesses: 1.8 kg"),
            ("Field of View and Alignment", "The nine detectors must be aligned to be within 1mm of concentric to the field of view of each of the nine grid pairs on the imager. This alignment is achieved when installing the Spectrometer on the spacecraft by shimming at the imager interface points.\n\nAlignment tolerance tightened from 2mm to 1mm based on optical analysis presented at PDR."),
            ("Mechanisms", "The Spectrometer contains the following mechanisms:\n- Cryocooler: free piston, linear motion, He gas compressor. Residual operating forces shall not exceed TBR-UCB-102 newtons driven at 59 Hz.\n- Hi-Z Shutters (2x): moving mass 300g (thick) and 230g (thin). Motion of 60mm in approximately 0.5 seconds.\n- Cryostat Vacuum Valve: SMA-actuated one-shot valve, opened no sooner than 72 hours after launch."),
        ],
        output_path=out / "HSI_Mech_Requirements_v2.docx",
        author="UCB Mechanical Engineering",
        doc_number="HSI-MECH-REQ-001",
        revision="v2",
        date="2024-06-20",
    )

    # v3: Post-CDR — all TBDs resolved, final values
    generate_docx(
        title="HESSI Spectrometer Mechanical Interface Requirements",
        sections=[
            ("Scope", "This document defines the mechanical interface requirements between the HESSI Spacecraft Bus and the Spectrometer instrument assembly. It establishes the physical constraints, mounting interface, mass allocation, and alignment requirements.\n\nChange from v2: All TBRs resolved. Final values from qualification testing incorporated. Document approved for ICD baseline."),
            ("Interface Drawing", "The mechanical configuration of the Spectrometer is shown in the Spectrometer ICD Drawing (HSI_SYS_014F, Rev 3). Drawing updated 2024-09-15 incorporating CDR redlines."),
            ("Mass Properties", "The Spectrometer assembly mass allocation is 50 kg maximum.\n\nFinal Measured Mass: 45.2 kg (flight unit weigh)\nMargin: 9.6%\n\nComponent breakdown (measured):\n- Cryostat Assembly: 29.1 kg\n- Detector Array (9x): 4.3 kg\n- Cryocooler: 6.9 kg\n- Hi-Z Shutters: 1.08 kg\n- Thermal Hardware: 2.0 kg\n- Harnesses: 1.82 kg\n\nNote: Mass margin below 10% accepted per waiver MSE-2024-003."),
            ("Field of View and Alignment", "The nine detectors must be aligned to be within 1mm of concentric to the field of view of each of the nine grid pairs on the imager. This alignment is achieved when installing the Spectrometer on the spacecraft by shimming at the imager interface points.\n\nVerified during instrument-level alignment test (ref: HSI-ALN-RPT-001). Achieved alignment: 0.4mm RMS."),
            ("Mechanisms", "The Spectrometer contains the following mechanisms:\n- Cryocooler: free piston, linear motion, He gas compressor. Residual operating forces: 0.48 newtons at 59 Hz (measured during qualification vibration test, satisfies former TBR-UCB-102 requirement of 0.5N max).\n- Hi-Z Shutters (2x): moving mass 300g (thick) and 230g (thin). Measured actuation time: 0.47 seconds (thick), 0.44 seconds (thin).\n- Cryostat Vacuum Valve: SMA-actuated one-shot valve. Activation delay: 96 hours minimum post-launch (thermal settling requirement)."),
        ],
        output_path=out / "HSI_Mech_Requirements_v3.docx",
        author="UCB Mechanical Engineering",
        doc_number="HSI-MECH-REQ-001",
        revision="v3",
        date="2024-11-05",
    )

    # v4: Post-flight update — as-flown values
    generate_docx(
        title="HESSI Spectrometer Mechanical Interface Requirements",
        sections=[
            ("Scope", "This document defines the mechanical interface requirements between the HESSI Spacecraft Bus and the Spectrometer instrument assembly.\n\nChange from v3: Updated with as-flown data from first 6 months of operations. All requirements verified on-orbit."),
            ("Interface Drawing", "The mechanical configuration of the Spectrometer is shown in the Spectrometer ICD Drawing (HSI_SYS_014F, Rev 3). No changes from v3 — drawing represents as-built configuration."),
            ("Mass Properties", "The Spectrometer assembly mass allocation is 50 kg maximum.\n\nFinal Measured Mass: 45.2 kg (unchanged from v3)\nOn-orbit mass verification: confirmed via spacecraft momentum management data.\n\nAll mass values represent as-flown configuration."),
            ("Field of View and Alignment", "The nine detectors must be aligned to be within 1mm of concentric to the field of view of each of the nine grid pairs on the imager.\n\nOn-orbit verification: Alignment verified via star tracker cross-calibration during commissioning. Measured on-orbit alignment: 0.6mm RMS (within 1mm requirement). Slight degradation from ground measurement (0.4mm) attributed to launch shift — within predictions."),
            ("Mechanisms — On-Orbit Performance", "Cryocooler: Operating nominally at 59 Hz. Measured residual force: 0.42N (improved from ground test due to thermal settling). Zero vibration complaints from spacecraft bus.\n\nHi-Z Shutters: Both shutters actuated successfully during commissioning. Thick shutter: 0.48s actuation. Thin shutter: 0.45s. Both within spec.\n\nCryostat Vacuum Valve: Opened successfully at L+120 hours. Cryostat pressure: <1e-6 torr within 24 hours of valve opening."),
        ],
        output_path=out / "HSI_Mech_Requirements_v4.docx",
        author="UCB Mechanical Engineering",
        doc_number="HSI-MECH-REQ-001",
        revision="v4",
        date="2025-06-15",
    )

    print(f"  Series: HSI Mech Requirements (4 versions) → {out}")


# ═══════════════════════════════════════════════════════════════════════
# SERIES 2: HSI Power Budget (XLSX, 5 versions)
# ═══════════════════════════════════════════════════════════════════════


def generate_hsi_power_budget_series():
    """5 versions of the power budget spreadsheet, maturing over time."""
    out = CORPUS_DIR / "hsi_sys_015g" / "series" / "power_budget"

    # v1: Initial allocation
    generate_xlsx(
        title="HSI Spectrometer Power Budget",
        headers=["Mode", "Subsystem", "Voltage (V)", "Power (W)", "Status"],
        rows=[
            ["Science", "Detectors", "5.0", "5.0", "ESTIMATE"],
            ["Science", "Cryocooler", "28.0", "80.0", "ALLOCATION"],
            ["Science", "IDPU", "5.0", "12.0", "ESTIMATE"],
            ["Science", "Heaters", "28.0", "15.0", "ALLOCATION"],
            ["Eclipse", "Survival Heaters", "28.0", "15.0", "ALLOCATION"],
            ["Eclipse", "IDPU Standby", "5.0", "3.0", "ESTIMATE"],
        ],
        output_path=out / "Power_Budget_v1.xlsx",
        sheet_name="Power Budget",
        doc_ref="HSI_SYS_015G Section 4 (preliminary)",
        date="2024-01-20",
    )

    # v2: Post-PDR refinement
    generate_xlsx(
        title="HSI Spectrometer Power Budget",
        headers=["Mode", "Subsystem", "Voltage (V)", "Current (A)", "Power (W)", "Duty (%)", "Avg (W)", "Status"],
        rows=[
            ["Science", "Detectors", "5.0", "0.8", "4.0", "100", "4.0", "MEASURED"],
            ["Science", "Cryocooler", "28.0", "2.5", "70.0", "100", "70.0", "VENDOR DATA"],
            ["Science", "IDPU", "5.0", "2.0", "10.0", "100", "10.0", "MEASURED"],
            ["Science", "Heaters", "28.0", "0.54", "15.0", "30", "4.5", "CALCULATED"],
            ["Eclipse", "Survival Heaters", "28.0", "0.54", "15.0", "100", "15.0", "CALCULATED"],
            ["Eclipse", "IDPU Standby", "5.0", "0.5", "2.5", "100", "2.5", "ESTIMATE"],
            ["Safehold", "Essential Heaters", "28.0", "0.25", "7.0", "100", "7.0", "CALCULATED"],
        ],
        output_path=out / "Power_Budget_v2.xlsx",
        sheet_name="Power Budget",
        doc_ref="HSI_SYS_015G Section 4 (PDR update)",
        date="2024-05-15",
    )

    # v3: Post-CDR — vendor final values
    generate_xlsx(
        title="HSI Spectrometer Power Budget",
        headers=["Mode", "Subsystem", "Voltage (V)", "Current (A)", "Power (W)", "Duty (%)", "Avg (W)", "Status"],
        rows=[
            ["Science", "Detectors", "5.0", "0.82", "4.1", "100", "4.1", "QUAL TEST"],
            ["Science", "Cryocooler", "28.0", "2.45", "68.6", "100", "68.6", "QUAL TEST"],
            ["Science", "IDPU", "5.0", "1.95", "9.75", "100", "9.75", "QUAL TEST"],
            ["Science", "Heaters", "28.0", "0.50", "14.0", "35", "4.9", "THERMAL TEST"],
            ["Science", "Shutter Actuation", "28.0", "5.0", "140.0", "0.1", "0.14", "QUAL TEST"],
            ["Eclipse", "Survival Heaters", "28.0", "0.50", "14.0", "100", "14.0", "THERMAL TEST"],
            ["Eclipse", "IDPU Standby", "5.0", "0.48", "2.4", "100", "2.4", "MEASURED"],
            ["Safehold", "Essential Heaters", "28.0", "0.25", "7.0", "100", "7.0", "CALCULATED"],
        ],
        output_path=out / "Power_Budget_v3.xlsx",
        sheet_name="Power Budget",
        doc_ref="HSI_SYS_015G Section 4 (CDR baseline)",
        date="2024-10-05",
    )

    # v4: Pre-ship — flight unit measurements
    generate_xlsx(
        title="HSI Spectrometer Power Budget",
        headers=["Mode", "Subsystem", "Voltage (V)", "Current (A)", "Power (W)", "Duty (%)", "Avg (W)", "Status"],
        rows=[
            ["Science", "Detectors", "5.0", "0.80", "4.0", "100", "4.0", "FLIGHT MEAS"],
            ["Science", "Cryocooler", "28.0", "2.42", "67.8", "100", "67.8", "FLIGHT MEAS"],
            ["Science", "IDPU", "5.0", "1.92", "9.6", "100", "9.6", "FLIGHT MEAS"],
            ["Science", "Heaters", "28.0", "0.50", "14.0", "32", "4.5", "FLIGHT MEAS"],
            ["Science", "Shutter Actuation", "28.0", "4.8", "134.4", "0.1", "0.13", "FLIGHT MEAS"],
            ["Eclipse", "Survival Heaters", "28.0", "0.50", "14.0", "100", "14.0", "FLIGHT MEAS"],
            ["Eclipse", "IDPU Standby", "5.0", "0.47", "2.35", "100", "2.35", "FLIGHT MEAS"],
            ["Safehold", "Essential Heaters", "28.0", "0.25", "7.0", "100", "7.0", "FLIGHT MEAS"],
        ],
        output_path=out / "Power_Budget_v4.xlsx",
        sheet_name="Power Budget",
        doc_ref="HSI_SYS_015G Section 4 (pre-ship)",
        date="2025-02-20",
    )

    # v5: On-orbit verified
    generate_xlsx(
        title="HSI Spectrometer Power Budget — As-Flown",
        headers=["Mode", "Subsystem", "Voltage (V)", "Current (A)", "Power (W)", "Duty (%)", "Avg (W)", "Status", "On-Orbit Delta"],
        rows=[
            ["Science", "Detectors", "5.0", "0.79", "3.95", "100", "3.95", "ON-ORBIT", "-1.3%"],
            ["Science", "Cryocooler", "28.0", "2.38", "66.6", "100", "66.6", "ON-ORBIT", "-1.8%"],
            ["Science", "IDPU", "5.0", "1.90", "9.5", "100", "9.5", "ON-ORBIT", "-1.0%"],
            ["Science", "Heaters", "28.0", "0.48", "13.4", "28", "3.8", "ON-ORBIT", "-16%"],
            ["Science", "Shutter Actuation", "28.0", "4.6", "128.8", "0.1", "0.13", "ON-ORBIT", "-4.2%"],
            ["Eclipse", "Survival Heaters", "28.0", "0.48", "13.4", "100", "13.4", "ON-ORBIT", "-4.3%"],
            ["Eclipse", "IDPU Standby", "5.0", "0.46", "2.3", "100", "2.3", "ON-ORBIT", "-2.1%"],
            ["Safehold", "Essential Heaters", "28.0", "0.24", "6.7", "100", "6.7", "ON-ORBIT", "-4.3%"],
        ],
        output_path=out / "Power_Budget_v5.xlsx",
        sheet_name="Power Budget",
        doc_ref="HSI_SYS_015G Section 4 (on-orbit verified)",
        date="2025-08-10",
    )

    print(f"  Series: HSI Power Budget (5 versions) → {out}")


# ═══════════════════════════════════════════════════════════════════════
# SERIES 3: IDSS Seal Design Review (PPTX, 3 versions)
# ═══════════════════════════════════════════════════════════════════════


def generate_idss_seal_review_series():
    """3 versions of a design review presentation, evolving through reviews."""
    out = CORPUS_DIR / "idss_idd" / "series" / "seal_design_review"

    # v1: PDR — initial design concept
    generate_pptx(
        title="IDSS Docking Seal Interface Design",
        subtitle="Preliminary Design Review (PDR)",
        slides=[
            ("Design Requirements", "Seal must maintain cabin pressure across docking interface\nOperating temperature: -100°C to +100°C\nDesign life: 10 docking cycles minimum\nLeak rate: < 1.0 x 10^-4 scc/sec He at 14.7 psia"),
            ("Seal Configuration", "Dual-seal configuration with inter-seal pressure monitoring\nPrimary seal: silicone elastomer (Esterline ELA-SA-401)\nSecondary seal: fluorosilicone backup\nSeal groove geometry: dovetail cross-section"),
            ("Interface Geometry", "Seal diameter: 1524mm (60 inches)\nSeal cross-section: 12mm x 8mm\nGroove depth: 6.5mm\nCompression: 25% nominal"),
            ("Open Items", "TBD-SEAL-001: Final elastomer compound selection\nTBD-SEAL-002: Seal compression range verification\nTBD-SEAL-003: Low-temperature performance data\nTBD-SEAL-004: Radiation degradation assessment"),
            ("Schedule", "PDR: Complete\nMaterial qualification: Q3 2017\nSeal prototype test: Q4 2017\nCDR: Q1 2018"),
        ],
        output_path=out / "Seal_Design_Review_v1_PDR.pptx",
        date="2016-09-15",
        author="IDSS Seal Design Team",
    )

    # v2: CDR — design matured, most TBDs resolved
    generate_pptx(
        title="IDSS Docking Seal Interface Design",
        subtitle="Critical Design Review (CDR)",
        slides=[
            ("Design Requirements (unchanged)", "Seal must maintain cabin pressure across docking interface\nOperating temperature: -100°C to +100°C\nDesign life: 10 docking cycles minimum\nLeak rate: < 1.0 x 10^-4 scc/sec He at 14.7 psia"),
            ("Seal Configuration (final)", "Dual-seal configuration with inter-seal pressure monitoring\nPrimary seal: Esterline ELA-SA-401 (qualified)\nSecondary seal: Parker S0383-70 fluorosilicone\nSeal groove geometry: dovetail, 15° sidewall angle\nRetention: mechanical capture ring"),
            ("Qualification Test Results", "Thermal cycling: 50 cycles, -100°C to +100°C — PASS\nCompression set: 18% after 1000 hours at 100°C — PASS (req: <25%)\nLeak rate at -50°C: 3.2 x 10^-5 scc/sec — PASS\nLeak rate at +100°C: 7.8 x 10^-5 scc/sec — PASS\nDocking cycle test: 15 cycles completed, no degradation"),
            ("Resolved TBDs", "TBD-SEAL-001: RESOLVED — ELA-SA-401 selected and qualified\nTBD-SEAL-002: RESOLVED — compression range 20-30% verified\nTBD-SEAL-003: RESOLVED — leak rate meets spec to -80°C\nTBD-SEAL-004: OPEN — radiation test scheduled Q2 2018"),
            ("Remaining Risk", "Radiation degradation data pending (TBD-SEAL-004)\nMitigation: secondary seal provides redundancy\nLong-term on-orbit compression set unknown\nMitigation: seal replacement capability designed in"),
        ],
        output_path=out / "Seal_Design_Review_v2_CDR.pptx",
        date="2018-02-20",
        author="IDSS Seal Design Team",
    )

    # v3: Post-qualification — all TBDs resolved, flight ready
    generate_pptx(
        title="IDSS Docking Seal Interface Design",
        subtitle="Flight Readiness Review (FRR)",
        slides=[
            ("Design Status: FLIGHT READY", "All requirements verified by test\nAll TBDs resolved\nFlight seals manufactured and inspected\nAcceptance test complete\nShip review passed"),
            ("Final Qualification Summary", "Thermal cycling: 100 cycles completed (2x requirement)\nCompression set: 16% final (below 25% limit)\nLeak rate worst case: 8.1 x 10^-5 at +100°C (below 1.0 x 10^-4 limit)\nDocking cycle: 20 cycles (2x requirement)\nRadiation: 25 krad total dose, no measurable degradation\nAll margins positive"),
            ("All TBDs Resolved", "TBD-SEAL-001: CLOSED — ELA-SA-401 (PDR resolution)\nTBD-SEAL-002: CLOSED — 20-30% compression verified (PDR)\nTBD-SEAL-003: CLOSED — meets spec to -80°C (CDR)\nTBD-SEAL-004: CLOSED — 25 krad no degradation (this review)"),
            ("Flight Unit Status", "Lot acceptance test: PASS\nDimensional inspection: all within tolerance\nSurface finish: Ra 0.4 (requirement Ra 0.8)\nShelf life: 5 years from cure date (manufactured 2019-03)\nInstallation window: 2020-2024"),
            ("Lessons Learned", "Dovetail groove requires precision machining (±0.05mm)\nSeal installation tool critical for consistent compression\nInter-seal monitoring provides real-time health indication\nSecond source qualification recommended for production"),
        ],
        output_path=out / "Seal_Design_Review_v3_FRR.pptx",
        date="2019-11-10",
        author="IDSS Seal Design Team",
    )

    print(f"  Series: IDSS Seal Design Review (3 versions) → {out}")


# ═══════════════════════════════════════════════════════════════════════
# SERIES 4: HSI Thermal Limits (XLSX + HTML wiki, 3 versions)
# ═══════════════════════════════════════════════════════════════════════


def generate_hsi_thermal_series():
    """3 versions of thermal limits — evolving from prediction to on-orbit."""
    out = CORPUS_DIR / "hsi_sys_015g" / "series" / "thermal_limits"

    # v1: Analytical prediction
    generate_xlsx(
        title="Spectrometer Thermal Limits",
        headers=["Interface", "Parameter", "Min (°C)", "Max (°C)", "Basis", "Margin (°C)"],
        rows=[
            ["Bus Side", "Operating", "-10", "+40", "Analysis", "5"],
            ["Bus Side", "Survival", "-20", "+50", "Analysis", "10"],
            ["Spectrometer Side", "Operating", "-20", "+30", "Analysis", "5"],
            ["Spectrometer Side", "Survival", "-30", "+40", "Analysis", "10"],
            ["Detector Array", "Operating", "-198", "-190", "Vendor Spec", "2"],
            ["Cryocooler Reject", "Operating", "—", "+50", "Vendor Spec", "10"],
            ["Radiator Surface", "Operating", "-40", "+10", "Analysis", "5"],
        ],
        output_path=out / "Thermal_Limits_v1.xlsx",
        sheet_name="Thermal Limits",
        doc_ref="HSI_SYS_015G Table 3.3-1 (prediction)",
        date="2024-03-10",
    )

    # v2: Post-thermal-vacuum test
    generate_xlsx(
        title="Spectrometer Thermal Limits",
        headers=["Interface", "Parameter", "Min (°C)", "Max (°C)", "Basis", "Margin (°C)", "Test Result"],
        rows=[
            ["Bus Side", "Operating", "-10", "+40", "TV Test", "8", "-2°C to +32°C observed"],
            ["Bus Side", "Survival", "-20", "+50", "TV Test", "15", "-5°C to +35°C observed"],
            ["Spectrometer Side", "Operating", "-20", "+30", "TV Test", "7", "-13°C to +23°C observed"],
            ["Spectrometer Side", "Survival", "-30", "+40", "TV Test", "12", "-18°C to +28°C observed"],
            ["Detector Array", "Operating", "-198", "-190", "TV Test", "3", "-195°C achieved"],
            ["Cryocooler Reject", "Operating", "—", "+50", "TV Test", "12", "+38°C max observed"],
            ["Radiator Surface", "Operating", "-40", "+10", "TV Test", "8", "-32°C to +2°C observed"],
        ],
        output_path=out / "Thermal_Limits_v2.xlsx",
        sheet_name="Thermal Limits",
        doc_ref="HSI_SYS_015G Table 3.3-1 (post-TVT)",
        date="2024-11-20",
    )

    # v3: On-orbit verified
    generate_xlsx(
        title="Spectrometer Thermal Limits — On-Orbit Verified",
        headers=["Interface", "Parameter", "Min (°C)", "Max (°C)", "Basis", "Margin (°C)", "On-Orbit Obs", "Flight Delta"],
        rows=[
            ["Bus Side", "Operating", "-10", "+40", "Flight Data", "10", "-1°C to +30°C", "Better than TV"],
            ["Bus Side", "Survival", "-20", "+50", "Flight Data", "17", "-3°C to +33°C", "Better than TV"],
            ["Spectrometer Side", "Operating", "-20", "+30", "Flight Data", "9", "-11°C to +21°C", "Better than TV"],
            ["Spectrometer Side", "Survival", "-30", "+40", "Flight Data", "14", "-16°C to +26°C", "Better than TV"],
            ["Detector Array", "Operating", "-198", "-190", "Flight Data", "4", "-194°C steady", "Better than TV"],
            ["Cryocooler Reject", "Operating", "—", "+50", "Flight Data", "16", "+34°C max", "Better than TV"],
            ["Radiator Surface", "Operating", "-40", "+10", "Flight Data", "12", "-28°C to -2°C", "Colder (good)"],
        ],
        output_path=out / "Thermal_Limits_v3.xlsx",
        sheet_name="Thermal Limits",
        doc_ref="HSI_SYS_015G Table 3.3-1 (on-orbit verified)",
        date="2025-07-30",
    )

    print(f"  Series: HSI Thermal Limits (3 versions) → {out}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════


def main():
    print("Generating versioned document series...")
    print()

    generate_hsi_mech_req_series()
    generate_hsi_power_budget_series()
    generate_idss_seal_review_series()
    generate_hsi_thermal_series()

    print("\nDone. Series generated with version chains for lineage testing.")


if __name__ == "__main__":
    main()
