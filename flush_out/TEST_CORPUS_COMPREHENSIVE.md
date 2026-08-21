# Comprehensive Test Corpus — Multi-Format Document Lineage

**Purpose:** Build a realistic, multi-format document set that traces the full provenance chain for every section of our ICD corpus. The lineage view shows, for the currently-open ICD, a time-ordered series of upstream source documents (DOCX, PPTX, XLSX, images, HTML) per section — revealing what info updates what and when.

**Last updated:** 2026-08-21

---

## The Lineage View Concept

When a user opens `HSI_SYS_015G.pdf` (the primary ICD), a lineage panel shows:

```
┌─────────────────────────────────────────────────────────────────┐
│ 📋 HSI_SYS_015G — Source Lineage                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Section 2: Mechanical Interface                                  │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ ● 2024-03-15  HSI_Mech_Requirements_v1.docx   [DOCX]     │   │
│ │ ● 2024-06-22  Spectrometer_Mount_Drawing.png  [IMAGE]     │   │
│ │ ● 2024-09-10  HSI_Mech_Requirements_v2.docx   [DOCX]     │   │
│ │ ● 2025-01-08  Cryocooler_Assembly_Photo.jpg   [IMAGE]     │   │
│ │ ● 2025-04-20  HSI_Mass_Properties_v3.xlsx     [XLSX]      │   │
│ │ ★ 2025-07-01  HSI_SYS_015G.pdf (Rev G)       [ICD]       │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│ Section 3: Thermal Interface                                     │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ ● 2024-02-10  Thermal_Analysis_CDR.pptx       [PPTX]      │   │
│ │ ● 2024-05-30  Thermostat_Parameters.xlsx      [XLSX]      │   │
│ │ ● 2024-11-15  Thermal_Test_Report.docx        [DOCX]      │   │
│ │ ● 2025-03-22  Thermal_Limits_Update.xlsx      [XLSX]      │   │
│ │ ★ 2025-07-01  HSI_SYS_015G.pdf (Rev G)       [ICD]       │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│ Section 4: Electrical Interface                                  │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ ● 2024-01-20  Power_Budget_Baseline.xlsx      [XLSX]      │   │
│ │ ● 2024-04-15  Connector_Pinout_J1.tiff        [IMAGE]     │   │
│ │ ● 2024-07-10  Electrical_Design_Review.pptx   [PPTX]      │   │
│ │ ● 2024-10-05  Power_Budget_v2.xlsx            [XLSX]      │   │
│ │ ● 2025-02-18  Harness_Routing_Diagram.png     [IMAGE]     │   │
│ │ ● 2025-05-30  Confluence: "HSI Power ICD"     [HTML]      │   │
│ │ ★ 2025-07-01  HSI_SYS_015G.pdf (Rev G)       [ICD]       │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Each entry shows: date, filename, format badge, version if applicable.
The currently-open ICD (★) is always the terminal node in the timeline.
Stale items (source updated AFTER the ICD was published) get ⚠️ indicators.

---

## Current ICD Corpus

| Document | Pages | Program | Sections | Revisions Available |
|----------|-------|---------|----------|-------------------|
| HSI_SYS_015G.pdf | 8 | HESSI/RHESSI | Mech, Thermal, Electrical, I&T | Single (G) |
| HSI_SYS_001H.pdf | 23 | HESSI/RHESSI | Mech, Thermal, Electrical, Software, EMI | H, I |
| HSI_SYS_001I.pdf | 23 | HESSI/RHESSI | Same as 001H (next revision) | H, I |
| IDSS_IDD_RevA.pdf | 40 | ISS Docking | Docking system standard (early) | A, D, E, F, G |
| IDSS_IDD_RevD.pdf | 142 | ISS Docking | Full docking interface (formal) | A, D, E, F, G |
| IDSS_IDD_RevE.pdf | 142 | ISS Docking | Same (expanded) | A, D, E, F, G |
| IDSS_IDD_RevF.pdf | 70 | ISS Docking | Same (reorganized/condensed) | A, D, E, F, G |
| IDSS_IDD_RevG.pdf | 86 | ISS Docking | Same (latest) | A, D, E, F, G |
| 20130010957.pdf | 15 | TSAFE (ATC) | Data formats, conflict detection | Single |
| 20150010976.pdf | 35 | LVC (Simulation) | Architecture, interfaces | Single |
| NDS_IDD_RevC.pdf | 108 | NASA Docking | Docking system (precursor to IDSS) | Single (C) |
| ICESat2_ATL03.pdf | 188 | ICESat-2 | Geolocation data product spec | Single |

---

## Comprehensive Corpus Map

For each ICD, the following source documents form its lineage chain.
Each source has a realistic date, version, and format representing
the kind of artifact that would exist in a real engineering program.

### HSI_SYS_015G.pdf — Spacecraft to Spectrometer ICD

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | HSI_Program_Charter.docx | DOCX | 2023-08-15 | v1 | Program overview, team roles, scope |
| **1. Introduction** | HESSI_Mission_Overview.pptx | PPTX | 2023-11-20 | v1 | Mission briefing slides (10 slides) |
| **2. Mechanical** | HSI_Mech_Requirements_v1.docx | DOCX | 2024-03-15 | v1 | Initial mechanical interface requirements |
| **2. Mechanical** | Spectrometer_Mount_Drawing.png | PNG | 2024-06-22 | — | CAD export: spectrometer mounting interface |
| **2. Mechanical** | HSI_Mech_Requirements_v2.docx | DOCX | 2024-09-10 | v2 | Updated after CDR (mass margin changes) |
| **2. Mechanical** | Cryocooler_Assembly_Photo.jpg | JPG | 2025-01-08 | — | Hardware photo: cryocooler installed |
| **2. Mechanical** | HSI_Mass_Properties.xlsx | XLSX | 2025-04-20 | v3 | Mass budget: CBE, margin, allocation per component |
| **2.4 Cryocooler** | Cryocooler_Force_Test_Data.xlsx | XLSX | 2024-11-05 | v1 | Vibration test results (TBR-UCB-102 resolution data) |
| **2.4 Cryocooler** | Cryocooler_Diagram.png | PNG | 2024-07-15 | — | Block diagram: piston, compressor, counterbalance |
| **3. Thermal** | Thermal_Analysis_CDR.pptx | PPTX | 2024-02-10 | v1 | CDR thermal presentation (15 slides) |
| **3. Thermal** | Thermostat_Parameters.xlsx | XLSX | 2024-05-30 | v1 | Table 3.2.1-1 source data: thermostat characteristics |
| **3. Thermal** | Thermal_Test_Report.docx | DOCX | 2024-11-15 | v1 | Thermal vacuum test results |
| **3. Thermal** | Thermal_Limits_Update.xlsx | XLSX | 2025-03-22 | v2 | Updated Table 3.3-1 values post-test |
| **3. Thermal** | Heater_Circuit_Schematic.tiff | TIFF | 2024-08-20 | — | Scanned drawing: heater wiring diagram |
| **4. Electrical** | Power_Budget_Baseline.xlsx | XLSX | 2024-01-20 | v1 | Initial power allocation per subsystem |
| **4. Electrical** | Connector_Pinout_J1.tiff | TIFF | 2024-04-15 | — | Scanned: connector J1 pin assignment drawing |
| **4. Electrical** | Electrical_Design_Review.pptx | PPTX | 2024-07-10 | v1 | EDR presentation (12 slides) |
| **4. Electrical** | Power_Budget_v2.xlsx | XLSX | 2024-10-05 | v2 | Updated power budget after component selection |
| **4. Electrical** | Harness_Routing_Diagram.png | PNG | 2025-02-18 | — | Harness routing between S/C and spectrometer |
| **4. Electrical** | HSI_Power_ICD_Wiki.html | HTML | 2025-05-30 | — | Confluence page: living power interface spec |
| **5. I&T** | Integration_Procedure_v1.docx | DOCX | 2025-03-01 | v1 | Step-by-step integration procedure |
| **5. I&T** | Alignment_Verification_Photo.jpg | JPG | 2025-05-15 | — | Photo: spectrometer alignment verification |

### HSI_SYS_001H.pdf / 001I.pdf — Spacecraft to IDPU ICD

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | IDPU_System_Description.docx | DOCX | 2023-06-10 | v1 | IDPU subsystem overview |
| **2. Mechanical** | IDPU_Mounting_Envelope.png | PNG | 2023-09-20 | — | Mechanical envelope drawing |
| **2. Mechanical** | IDPU_Mass_Budget.xlsx | XLSX | 2024-02-14 | v2 | Mass properties table |
| **3. Thermal** | IDPU_Thermal_Model_Results.pptx | PPTX | 2024-04-10 | v1 | Thermal model predictions (8 slides) |
| **3. Thermal** | IDPU_Thermal_Limits.xlsx | XLSX | 2024-08-25 | v1 | Operating/survival temperature ranges |
| **4. Electrical** | IDPU_Power_Interface_v1.docx | DOCX | 2024-01-15 | v1 | Power bus requirements |
| **4. Electrical** | IDPU_Power_Interface_v2.docx | DOCX | 2024-07-20 | v2 | Updated after bus voltage change |
| **4. Electrical** | IDPU_Connector_Drawing.tiff | TIFF | 2024-03-10 | — | Connector pinout (scanned) |
| **4. Electrical** | IDPU_Signal_Timing.xlsx | XLSX | 2024-09-15 | v1 | Signal timing parameters |
| **5. Software** | Command_Dictionary_v3.xlsx | XLSX | 2025-01-10 | v3 | Command/telemetry definitions |
| **5. Software** | IDPU_FSW_ICD_Wiki.html | HTML | 2025-03-20 | — | Confluence: software interface living spec |
| **5. Software** | Command_Sequence_Diagram.png | PNG | 2024-11-05 | — | UML sequence diagram |
| **6. EMI/EMC** | EMI_Test_Report.docx | DOCX | 2025-02-28 | v1 | EMI qualification test results |
| **6. EMI/EMC** | EMI_Spectrum_Plot.png | PNG | 2025-02-28 | — | Radiated emissions spectrum graph |

### IDSS_IDD (RevA→D→E→F→G) — International Docking System Standard

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | IDSS_Program_Directive.docx | DOCX | 2010-06-15 | v1 | Original ISS partnership directive |
| **3.1 System Desc** | Docking_Mechanism_CAD_Export.png | PNG | 2011-03-20 | — | Docking mechanism geometry diagram |
| **3.1 System Desc** | Docking_Sequence_Animation_Frames.jpg | JPG | 2016-09-10 | — | Photo sequence: docking approach |
| **3.2 Mechanical** | Soft_Capture_Load_Analysis.xlsx | XLSX | 2015-08-20 | v2 | Structural load cases for soft capture |
| **3.2 Mechanical** | Hard_Dock_Requirements.docx | DOCX | 2016-02-10 | v3 | Hard dock interface requirements |
| **3.2 Mechanical** | Seal_Design_Review.pptx | PPTX | 2017-04-15 | v1 | Seal interface CDR (20 slides) |
| **3.2 Mechanical** | Docking_Ring_Photo.jpg | JPG | 2018-11-20 | — | Flight hardware photo |
| **3.3 Electrical** | Docking_Electrical_Schematic.tiff | TIFF | 2014-07-10 | — | Scanned: electrical interface drawing |
| **3.3 Electrical** | IDSS_Power_Cross_Strapping.xlsx | XLSX | 2019-05-15 | v4 | Power cross-strap configuration |
| **3.3 Electrical** | Connector_Mate_Demate_Procedure.docx | DOCX | 2020-01-20 | v2 | Connector handling procedure |
| **3.4 Avionics** | Avionics_Protocol_Spec.docx | DOCX | 2017-11-30 | v1 | Communication protocol definition |
| **3.4 Avionics** | Protocol_State_Machine.png | PNG | 2018-03-15 | — | State machine diagram |
| **3.4 Avionics** | Timing_Budget.xlsx | XLSX | 2021-06-10 | v3 | Communication timing budget |
| **3.5 Thermal** | Docking_Thermal_Model.pptx | PPTX | 2019-08-22 | v2 | Thermal predictions on-orbit |
| **3.5 Thermal** | On_Orbit_Thermal_Data.xlsx | XLSX | 2022-04-15 | v1 | Actual flight telemetry data |
| **General** | IDSS_Change_Log_Wiki.html | HTML | 2026-01-15 | — | Confluence: revision change tracking |
| **General** | Docking_Test_Facility_Photo.jpg | JPG | 2020-09-10 | — | Ground test facility photo |

### 20130010957.pdf — TSAFE (Traffic Safety Advisor)

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | TSAFE_Concept_Brief.pptx | PPTX | 2012-03-10 | v1 | Concept overview (8 slides) |
| **2. System Overview** | TSAFE_Architecture_Diagram.png | PNG | 2012-06-20 | — | System block diagram |
| **3. Data Formats** | TSAFE_Message_Spec.docx | DOCX | 2012-09-15 | v2 | Input/output message format definitions |
| **3. Data Formats** | Track_Update_Schema.xlsx | XLSX | 2012-11-10 | v1 | Field-by-field data format table |
| **3. Data Formats** | Radar_Interface_Diagram.png | PNG | 2013-01-05 | — | Data flow from radar to TSAFE |
| **4. Algorithms** | Conflict_Detection_Algorithm.docx | DOCX | 2013-02-20 | v1 | Algorithm description document |
| **4. Algorithms** | Trajectory_Prediction_Diagram.png | PNG | 2013-02-20 | — | Algorithm flow diagram |
| **5. Performance** | TSAFE_Test_Results.xlsx | XLSX | 2013-04-15 | v1 | Performance test matrix with results |
| **5. Performance** | Simulation_Results_Summary.pptx | PPTX | 2013-05-01 | v1 | Test campaign summary (12 slides) |

### 20150010976.pdf — LVC (Live Virtual Constructive) Architecture

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | LVC_Program_Overview.pptx | PPTX | 2014-02-15 | v1 | Program kickoff briefing |
| **2. Architecture** | LVC_System_Architecture.png | PNG | 2014-06-10 | — | High-level architecture diagram |
| **2. Architecture** | LVC_Component_Spec.docx | DOCX | 2014-09-20 | v2 | Component interface specifications |
| **3. Interfaces** | LVC_Data_Dictionary.xlsx | XLSX | 2014-11-15 | v1 | Interface data dictionary |
| **3. Interfaces** | Network_Topology_Diagram.png | PNG | 2015-01-10 | — | Network connectivity diagram |
| **3. Interfaces** | LVC_Protocol_Wiki.html | HTML | 2015-03-20 | — | Confluence: protocol specification |
| **4. Testing** | LVC_Integration_Test_Plan.docx | DOCX | 2015-05-15 | v1 | Integration test procedures |
| **4. Testing** | Test_Lab_Photo.jpg | JPG | 2015-06-01 | — | Test facility setup photo |

### NDS_IDD_RevC.pdf — NASA Docking System

| Section | Source Document | Format | Date | Version | Content |
|---------|----------------|--------|------|---------|---------|
| **1. Introduction** | NDS_Program_Requirements.docx | DOCX | 2010-01-15 | v1 | Top-level program requirements |
| **2. Mechanical** | NDS_Mechanical_Drawing.tiff | TIFF | 2010-08-20 | — | Scanned interface drawing (legacy) |
| **2. Mechanical** | NDS_Load_Cases.xlsx | XLSX | 2011-03-10 | v2 | Structural load analysis cases |
| **3. Electrical** | NDS_Electrical_Spec.docx | DOCX | 2011-06-15 | v1 | Electrical interface specification |
| **3. Electrical** | NDS_Wiring_Diagram.tiff | TIFF | 2011-06-15 | — | Scanned wiring diagram |
| **4. Avionics** | NDS_Protocol_Spec.docx | DOCX | 2012-01-20 | v2 | Communication protocol |
| **4. Avionics** | NDS_Timing_Analysis.xlsx | XLSX | 2012-04-15 | v1 | Protocol timing constraints |

---

## Format Distribution Summary

| Format | Count | Use Cases |
|--------|-------|-----------|
| **DOCX** | ~25 | Requirements, specs, procedures, test reports, meeting notes |
| **XLSX** | ~22 | Parameter budgets, test matrices, data dictionaries, timing |
| **PPTX** | ~12 | Design reviews, concept briefs, test summaries |
| **PNG** | ~16 | Block diagrams, architecture diagrams, state machines, plots |
| **JPG** | ~8 | Hardware photos, test facility photos, assembly photos |
| **TIFF** | ~8 | Scanned legacy drawings, wiring diagrams, pinouts |
| **HTML** | ~6 | Confluence wiki pages (living specs, change logs) |
| **Total** | **~97** | Diverse corpus across all 6 ICDs |

This gives each ICD between 8-18 upstream source documents, spanning 5-7 different formats, with realistic versioning and date progression.

---

## Document Generation Strategy

### Phase 1: Create from ICD Content (50 documents)

Extract real content from our existing ICD PDFs and reshape into source formats:

```python
# scripts/generate_corpus.py

def generate_all():
    """Generate the full test corpus from existing ICD Document IRs."""
    
    # DOCX: Extract section text into Word documents
    generate_requirements_docx("HSI_SYS_015G", sections=[2], 
                               output="HSI_Mech_Requirements_v2.docx",
                               date="2024-09-10", version="v2")
    
    # XLSX: Extract tables into spreadsheets  
    generate_parameter_xlsx("HSI_SYS_015G", page=7, table_zone=(250, 350),
                           output="Thermostat_Parameters.xlsx",
                           date="2024-05-30", version="v1")
    
    # PPTX: Create slide decks from section headings + key content
    generate_review_pptx("HSI_SYS_015G", sections=[3],
                        output="Thermal_Analysis_CDR.pptx", 
                        date="2024-02-10", slides=15)
    
    # PNG: Extract/render page regions as diagrams
    generate_diagram_png("HSI_SYS_015G", page=5, region=(50, 200, 550, 400),
                        output="Spectrometer_Mount_Drawing.png",
                        date="2024-06-22")
    
    # HTML: Generate Confluence-style wiki pages
    generate_wiki_html("HSI_SYS_015G", sections=[4],
                      output="HSI_Power_ICD_Wiki.html",
                      date="2025-05-30")
```

### Phase 2: Supplementary Real Files (20 documents)

- Hardware photos: NASA Image Gallery (public domain)
- Scanned drawings: Generate TIFF from PDF page renders + noise/skew
- Additional NTRS downloads (presentations available as PDF, convert select pages)

### Phase 3: Synthetic Artifacts (27 documents)

- Create realistic metadata (author, date, revision, size)
- JPG photos: public domain spacecraft/hardware images from NASA
- TIFF scans: render existing PDF pages at 300dpi with slight rotation + paper texture
- Meeting notes: templated DOCX with dates and action items

---

## Lineage Metadata Schema

Each corpus document carries metadata that the lineage system uses:

```json
{
  "filename": "Thermostat_Parameters.xlsx",
  "format": "xlsx",
  "created_date": "2024-05-30",
  "version": "v1",
  "author": "UCB Thermal Team",
  "source_connector": "sharepoint",
  "target_icd": "HSI_SYS_015G",
  "target_section": "3.2",
  "target_section_title": "Spectrometer Power Dissipation",
  "target_pages": [7],
  "link_type": "derived_from",
  "superseded_by": "Thermal_Limits_Update.xlsx",
  "description": "Source data for Table 3.2.1-1 (thermostat characteristics)"
}
```

This metadata is stored in a `corpus_manifest.json` that:
1. Seeds the mock Confluence/SharePoint servers with correct file trees
2. Pre-populates the lineage database for testing
3. Defines the expected timeline ordering per ICD section

---

## Corpus Directory Layout

```
test_corpus/
├── corpus_manifest.json           # All metadata, lineage links, timeline ordering
├── generate_corpus.py             # Script to regenerate from ICD IRs
├── download_public_sources.py     # Fetch NASA photos, NTRS docs
│
├── hsi_sys_015g/                  # Sources for HSI Spectrometer ICD
│   ├── docx/
│   │   ├── HSI_Program_Charter.docx
│   │   ├── HSI_Mech_Requirements_v1.docx
│   │   ├── HSI_Mech_Requirements_v2.docx
│   │   ├── Thermal_Test_Report.docx
│   │   └── Integration_Procedure_v1.docx
│   ├── xlsx/
│   │   ├── HSI_Mass_Properties.xlsx
│   │   ├── Cryocooler_Force_Test_Data.xlsx
│   │   ├── Thermostat_Parameters.xlsx
│   │   ├── Thermal_Limits_Update.xlsx
│   │   ├── Power_Budget_Baseline.xlsx
│   │   └── Power_Budget_v2.xlsx
│   ├── pptx/
│   │   ├── HESSI_Mission_Overview.pptx
│   │   ├── Thermal_Analysis_CDR.pptx
│   │   └── Electrical_Design_Review.pptx
│   ├── images/
│   │   ├── Spectrometer_Mount_Drawing.png
│   │   ├── Cryocooler_Assembly_Photo.jpg
│   │   ├── Cryocooler_Diagram.png
│   │   ├── Heater_Circuit_Schematic.tiff
│   │   ├── Connector_Pinout_J1.tiff
│   │   ├── Harness_Routing_Diagram.png
│   │   └── Alignment_Verification_Photo.jpg
│   └── html/
│       └── HSI_Power_ICD_Wiki.html
│
├── hsi_sys_001/                   # Sources for HSI IDPU ICD (H + I revisions)
│   ├── docx/ ...
│   ├── xlsx/ ...
│   ├── pptx/ ...
│   ├── images/ ...
│   └── html/ ...
│
├── idss_idd/                      # Sources for IDSS (A→D→E→F→G)
│   ├── docx/ ...
│   ├── xlsx/ ...
│   ├── pptx/ ...
│   ├── images/ ...
│   └── html/ ...
│
├── tsafe/                         # Sources for 20130010957 (TSAFE)
│   ├── docx/ ...
│   ├── xlsx/ ...
│   ├── pptx/ ...
│   └── images/ ...
│
├── lvc/                           # Sources for 20150010976 (LVC)
│   ├── docx/ ...
│   ├── xlsx/ ...
│   ├── pptx/ ...
│   ├── images/ ...
│   └── html/ ...
│
└── nds_idd/                       # Sources for NDS_IDD_RevC
    ├── docx/ ...
    ├── xlsx/ ...
    └── images/ ...
```

---

## Mock Server Seeding

The `corpus_manifest.json` drives how mock servers present the files:

### Confluence Mock

Documents with `source_connector: "confluence"` are served as pages:
- DOCX files → served as page body (HTML rendered) + downloadable attachment
- HTML files → served directly as page body content
- All other formats → served as page attachments

**Space structure:**
```
Space: HESSI Engineering (HSI)
├── Page: "HSI Power Interface Spec" → HSI_Power_ICD_Wiki.html
├── Page: "Mechanical Requirements" → HSI_Mech_Requirements_v2.docx (attachment)
├── Page: "Thermal Test Report" → Thermal_Test_Report.docx (attachment)
└── Page: "Design Reviews"
    ├── Attachment: Thermal_Analysis_CDR.pptx
    └── Attachment: Electrical_Design_Review.pptx

Space: IDSS Program
├── Page: "IDSS Change Log" → IDSS_Change_Log_Wiki.html
├── Page: "Requirements"
│   ├── Attachment: Hard_Dock_Requirements.docx
│   └── Attachment: Avionics_Protocol_Spec.docx
└── Page: "Design Artifacts"
    └── Attachment: Seal_Design_Review.pptx
```

### SharePoint Mock

Documents with `source_connector: "sharepoint"` are served as drive items:
- Organized by document library → folder → file
- Version history populated from version field

**Drive structure:**
```
Site: Engineering Documents
├── Library: Interface Data
│   ├── HSI_Mass_Properties.xlsx (v1, v2, v3)
│   ├── Power_Budget_Baseline.xlsx (v1)
│   ├── Power_Budget_v2.xlsx (v2)
│   ├── Thermostat_Parameters.xlsx (v1)
│   └── Thermal_Limits_Update.xlsx (v2)
├── Library: Drawings
│   ├── Spectrometer_Mount_Drawing.png
│   ├── Cryocooler_Diagram.png
│   ├── Connector_Pinout_J1.tiff
│   └── Harness_Routing_Diagram.png
└── Library: Photos
    ├── Cryocooler_Assembly_Photo.jpg
    ├── Docking_Ring_Photo.jpg
    └── Alignment_Verification_Photo.jpg
```

---

## Validation Criteria

The corpus is complete when:

1. **Every ICD section has ≥2 upstream sources** in different formats
2. **Every format type has ≥5 files** across the corpus
3. **Timeline ordering is realistic** (requirements → design → test → ICD)
4. **Version chains exist** (v1 → v2 → v3 for key documents)
5. **Both mock servers can serve the full tree** without gaps
6. **Import pipeline converts every format** to searchable Document IR
7. **Lineage view shows correct time ordering** per section
8. **Search returns results across all imported formats**
9. **Images are non-trivial** (actual diagrams/photos, not blank placeholders)
10. **Dates span a realistic program lifecycle** (2-3 years per ICD)
