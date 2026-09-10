# -*- coding: utf-8 -*-
# core/constants.py – PipeAgent v5.0
"""
PipeAgent — Piping Execution Operating System
Global Constants, Enumerations & Default Values
═══════════════════════════════════════════════
All piping site constants referenced across 30+ workspace modules.
Based on ASME B31.3, ASME Section IX, API 570, API 598, AWS D1.1.
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════
#  1. APPLICATION BRANDING & IDENTITY
# ═══════════════════════════════════════════════════════════

APP_NAME = "PipeAgent"
APP_VERSION = "5.0"
APP_CODENAME = "Titan"
ORG_NAME = "Piping Execution Systems"
BRAND_TAGLINE = "Know What's Next. Control What Matters."
PRODUCT_POSITIONING = "Piping Execution Operating System"

# ═══════════════════════════════════════════════════════════
#  2. PIPING DESIGN CODES & STANDARDS
# ═══════════════════════════════════════════════════════════

PIPING_CODES = [
    "ASME B31.3 (Process Piping)",
    "ASME B31.1 (Power Piping)",
    "ASME B31.4 (Liquid Transportation)",
    "ASME B31.8 (Gas Transmission & Distribution)",
    "ASME B31.12 (Hydrogen Piping & Pipelines)",
    "ASME B31.9 (Building Services Piping)",
    "API 1104 (Welding of Pipelines)",
    "API 570 (Piping Inspection Code)",
    "EN 13480 (Metallic Industrial Piping)",
    "ISO 15649 (Petroleum & Natural Gas Piping)",
]

# ═══════════════════════════════════════════════════════════
#  3. WELDING (ASME Section IX / AWS D1.1)
# ═══════════════════════════════════════════════════════════

WELDING_PROCESSES = [
    "GTAW (TIG)",
    "SMAW (Stick)",
    "GTAW + SMAW",
    "FCAW (Flux Cored)",
    "GMAW (MIG/MAG)",
    "SAW (Submerged Arc)",
    "PAW (Plasma Arc)",
    "GTAW + FCAW",
    "EGW (Electro-Gas)",
    "ESW (Electro-Slag)",
    "OAW (Oxy-Acetylene)",
]

WELDING_POSITIONS = [
    "1G (Flat)",
    "2G (Horizontal)",
    "3G (Vertical Up)",
    "4G (Overhead)",
    "5G (Multiple Fixed)",
    "6G (Inclined 45°)",
    "6GR (With Restriction Ring)",
    "1G Rot (Rotating)",
    "2G Fixed",
    "6G Fixed",
    "1F / 2F / 3F / 4F (Fillet)",
    "All Positions (1G–6G)",
]

WELD_TYPES = ["Shop", "Field", "Tie-in", "Repair", "Golden"]

JOINT_TYPES = [
    "Butt Weld (BW)",
    "Socket Weld (SW)",
    "Fillet Weld (FW)",
    "Branch / Olet",
    "Saddle",
    "Flange (WN/SO/Blind)",
    "Threaded Seal Weld",
]

WELD_STATUSES = [
    "Pending",
    "Fitup Complete",
    "Welded",
    "Visual Pass",
    "Visual Reject",
    "NDT Pending",
    "NDT Complete",
    "Accepted",
    "Rejected",
    "Repaired",
    "PWHT Done",
]

# ═══════════════════════════════════════════════════════════
#  4. NDT / NDE (Non-Destructive Testing)
# ═══════════════════════════════════════════════════════════

NDT_METHODS = [
    "RT (Radiography)",
    "UT (Ultrasonic)",
    "PT (Liquid Penetrant)",
    "MT (Magnetic Particle)",
    "VT (Visual Testing)",
    "HT (Hardness Testing)",
    "PAUT (Phased Array UT)",
    "TOFD (Time of Flight Diffraction)",
    "PMI (Positive Material ID)",
    "ECT (Eddy Current)",
    "AE (Acoustic Emission)",
    "Leak Test (Bubble / Helium)",
]

NDT_RESULTS = [
    "Pass",
    "Fail",
    "Accepted",
    "Rejected",
    "Pending",
    "Pending Film Review",
    "Repair",
    "Concession",
    "N/A",
]

# ═══════════════════════════════════════════════════════════
#  5. SPOOLING & FABRICATION
# ═══════════════════════════════════════════════════════════

SPOOL_STATUSES = [
    "Draft",
    "In Fabrication",
    "Fitting / Fit-up",
    "Welded",
    "NDT Complete",
    "PWHT Done",
    "Hydro Tested",
    "Painted / Coated",
    "Released to Site",
    "Installed",
    "On Hold",
]

# ═══════════════════════════════════════════════════════════
#  6. PIPE SUPPORTS & RESTRAINTS
# ═══════════════════════════════════════════════════════════

SUPPORT_TYPES = [
    "Shoe / Rest (Sliding)",
    "Guide (Lateral / Axial)",
    "Line Stop / Anchor",
    "Variable Spring Hanger",
    "Constant Spring Hanger",
    "Rigid Strut / Rod",
    "Trunnion / Dummy Leg",
    "U-Bolt / Pipe Clamp",
    "Saddle Support",
    "Snubber / Shock Absorber",
    "Sway Brace",
    "Special Engineered",
]

SUPPORT_STATUSES = [
    "Engineering / MTO",
    "In Fabrication",
    "Fabricated (Shop)",
    "Delivered to Site",
    "Installed",
    "QC Inspected",
    "Accepted",
    "On Hold / Punch",
]

# ═══════════════════════════════════════════════════════════
#  7. VALVES & IN-LINE ITEMS (API 598 / ISO 5208)
# ═══════════════════════════════════════════════════════════

VALVE_TYPES = [
    "Gate Valve",
    "Globe Valve",
    "Ball Valve",
    "Check Valve (Swing)",
    "Check Valve (Piston)",
    "Check Valve (Wafer)",
    "Butterfly Valve",
    "Plug Valve",
    "Knife Gate Valve",
    "Needle Valve",
    "Diaphragm Valve",
    "Control Valve",
    "Pressure Safety Valve (PSV)",
    "Pressure Relief Valve (PRV)",
    "Rupture Disc",
]

VALVE_RATINGS = [
    "150# (PN 20)",
    "300# (PN 50)",
    "600# (PN 100)",
    "900# (PN 150)",
    "1500# (PN 250)",
    "2500# (PN 420)",
    "API 5000",
    "API 10000",
    "PN 16",
    "PN 25",
    "PN 40",
]

VALVE_STATUSES = [
    "Received at Yard",
    "Workshop Tested (Passed)",
    "Test Failed / Overhaul",
    "Released for Erection",
    "Installed on Line",
    "Torqued & Boxed-Up",
    "Preserved / Inactive",
]

VALVE_END_CONNECTIONS = [
    "Flanged (RF)",
    "Flanged (RTJ)",
    "Butt-Weld (BW)",
    "Socket-Weld (SW)",
    "Threaded (NPT)",
    "Wafer / Lug",
    "Union End",
]

# ═══════════════════════════════════════════════════════════
#  8. MATERIALS & METALLURGY (ASTM / API / EN)
# ═══════════════════════════════════════════════════════════

PIPE_MATERIALS = [
    # Carbon Steels
    "ASTM A106 Gr.A", "ASTM A106 Gr.B", "ASTM A106 Gr.C",
    "ASTM A53 Gr.B", "ASTM A333 Gr.1", "ASTM A333 Gr.6",
    "ASTM A672", "API 5L Gr.B", "API 5L X42", "API 5L X52",
    "API 5L X60", "API 5L X65", "API 5L X70",
    # Low Alloy Cr-Mo Steels
    "ASTM A335 P5", "ASTM A335 P9", "ASTM A335 P11",
    "ASTM A335 P22", "ASTM A335 P91", "ASTM A335 P92",
    # Austenitic Stainless Steels
    "ASTM A312 TP304", "ASTM A312 TP304L",
    "ASTM A312 TP316", "ASTM A312 TP316L",
    "ASTM A312 TP321", "ASTM A312 TP347",
    "ASTM A358 TP304", "ASTM A358 TP316",
    # Duplex & Super Duplex
    "ASTM A790 S31803 (2205)", "ASTM A790 S32750 (2507)",
    "ASTM A928 S31803",
    # Nickel Alloys
    "ASTM B444 N06625 (Inconel 625)",
    "ASTM B622 N08825 (Incoloy 825)",
    "ASTM B677 N08904 (904L)",
    # Copper-Nickel
    "ASTM B466 C70600 (CuNi 90/10)",
    "ASTM B466 C71500 (CuNi 70/30)",
    # Titanium
    "ASTM B338 Gr.2 (Titanium)",
    # HDPE / Non-Metallic
    "HDPE PE100", "GRE / GRP (FRP)", "PVC / CPVC",
]

MATERIAL_TYPES = [
    "Pipe", "Elbow 90°", "Elbow 45°", "Tee (Equal)", "Tee (Reducing)",
    "Reducer (Concentric)", "Reducer (Eccentric)", "Cap", "Stub End",
    "Flange (WN)", "Flange (SO)", "Flange (Blind)", "Flange (Lap Joint)",
    "Olet (Weldolet)", "Olet (Sockolet)", "Olet (Thredolet)",
    "Valve", "Gasket", "Stud Bolt & Nuts", "Pipe Support Steel",
]

P_NUMBERS = [
    "P-No 1 (Carbon Steels)",
    "P-No 3 (Low Alloy Cr-Mo ≤3%)",
    "P-No 4 (1.25Cr-0.5Mo)",
    "P-No 5A/5B (2.25Cr-1Mo / 5Cr)",
    "P-No 7 (Ferritic SS 405/410)",
    "P-No 8 (Austenitic SS 304/316)",
    "P-No 9A/9B (Nickel Steels 9%Ni)",
    "P-No 10C/10H (Duplex / Super Duplex SS)",
    "P-No 34 (Cu-Ni Alloys)",
    "P-No 41-49 (Nickel Alloys)",
    "P-No 51-53 (Titanium Alloys)",
    "P-No 61-62 (Zirconium Alloys)",
]

# ═══════════════════════════════════════════════════════════
#  9. FLUID SERVICES & LINE CLASSIFICATION (ASME B31.3)
# ═══════════════════════════════════════════════════════════

FLUID_CODES = [
    "HC", "LPG", "NG", "FG", "H2", "N2", "O2", "IA", "PA", "SA",
    "CW", "HW", "DM", "FW", "SW", "WW", "BW", "CT", "H2S",
    "CR", "PR", "SL", "FO", "DO", "JP", "GL", "AM", "CL", "SF",
    "UT", "SS", "CS", "HS", "MS", "LS", "EX", "VG", "FL", "DR",
]

FLUID_SERVICES = [
    "Category D (Non-Flammable, Non-Toxic)",
    "Category M (Highly Toxic)",
    "High Pressure (P > 150 bar)",
    "High Temperature (T > 425°C)",
    "Normal Fluid Service",
    "Severe Cyclic Conditions",
    "Cryogenic Service (T < -29°C)",
    "Hydrogen Service (NACE MR0175)",
    "Sour Service (NACE MR0175 / ISO 15156)",
    "Caustic Service",
    "Oxygen Service",
    "Steam Service",
]

FLUID_SERVICE_DESCRIPTIONS = {
    "Category D": "Non-flammable, non-toxic, P ≤ 150 psi, T between -29°C and 186°C",
    "Category M": "Toxic fluid where a single exposure can produce serious irreversible harm",
    "High Pressure": "Design pressure exceeds flange rating or 150 bar(g)",
    "Normal": "Standard fluid service not falling into D, M, HP, or HT categories",
}

# ═══════════════════════════════════════════════════════════
#  10. DOCUMENT CONTROL & ENGINEERING DRAWINGS
# ═══════════════════════════════════════════════════════════

DOCUMENT_TYPES = [
    "P&ID", "PFD", "Line List", "Isometric Drawing", "GA Drawing",
    "Plot Plan", "Equipment Layout", "Pipe Support Standard",
    "Stress Analysis Report", "Material Specification",
    "WPS / PQR", "NDT Procedure", "ITP", "Test Package",
    "Data Sheet", "Vendor Drawing", "As-Built Drawing",
    "MTO / BOQ", "Painting Specification", "Insulation Specification",
]

DOCUMENT_STATUSES = [
    "Draft",
    "Internal Review",
    "Issued for Review (IFR)",
    "Issued for Approval (IFA)",
    "Issued for Construction (IFC)",
    "Approved",
    "Approved with Comments",
    "Rejected",
    "As-Built",
    "Superseded",
    "Cancelled",
]

# ═══════════════════════════════════════════════════════════
#  11. QA/QC — PUNCH LIST, NCR, ITP
# ═══════════════════════════════════════════════════════════

PUNCH_CATEGORIES = ["A", "B", "C"]
PUNCH_CATEGORY_DESC = {
    "A": "Pre-Test (Critical – must clear before Hydro Test)",
    "B": "Pre-Commissioning (must clear before Start-up)",
    "C": "Pre-Handover (Cosmetic / Minor – clear before MC Certificate)",
}

NCR_DISPOSITIONS = [
    "Use-As-Is (Engineering Concession)",
    "Repair (In-Situ)",
    "Rework (Full Replacement)",
    "Reject (Scrap)",
    "Return to Vendor (RTV)",
]

NCR_STATUSES = ["Open", "Under Review", "Dispositioned", "Closed", "Cancelled"]

NCR_ITEM_TYPES = [
    "Weld", "Spool", "Material", "Pipe Support", "Valve", "Flange",
    "Pipe", "Fitting", "Gasket", "Instrument", "Coating", "Insulation",
]

ITP_INSPECTION_TYPES = [
    "Hold Point (H)",
    "Witness Point (W)",
    "Review Point (R)",
    "Surveillance (S)",
]

ITP_STATUSES = [
    "Pending Inspection",
    "Completed / Cleared",
    "Waived",
]

# ═══════════════════════════════════════════════════════════
#  12. TESTING & PRE-COMMISSIONING
# ═══════════════════════════════════════════════════════════

TEST_MEDIUMS = [
    "Demineralized Water (Hydro)",
    "Inhibited Service Water",
    "Nitrogen Gas (Pneumatic)",
    "Dry Plant Air (Pneumatic)",
    "Water + Glycol (Winterization)",
    "Steam",
    "Helium Tracer Mix",
    "Other",
]

TEST_PACKAGE_STATUSES = [
    "Planned / Boundaries Draft",
    "Pre-Test Punch Clearance",
    "Ready for Test",
    "Filling & Pressurization",
    "Under Pressure Hold",
    "Passed / Accepted",
    "Depressurized & Draining",
    "Reinstated & Boxed-Up",
    "Failed / Leaking",
    "Cancelled",
]

HANDOVER_STATUSES = [
    "In Progress",
    "Ready for Review",
    "Accepted",
    "Punch Listed",
    "Rejected",
    "Transferred to Commissioning",
]

# ═══════════════════════════════════════════════════════════
#  13. FINISHING — PAINTING, INSULATION, PWHT, TORQUE
# ═══════════════════════════════════════════════════════════

SURFACE_PREP_GRADES = [
    "Sa 1 (Light Blast)",
    "Sa 2 (Commercial Blast)",
    "Sa 2.5 (Near-White Metal)",
    "Sa 3 (White Metal)",
    "St 2 (Hand Tool)",
    "St 3 (Power Tool)",
    "WJ-1 to WJ-4 (Water Jetting)",
]

INSULATION_TYPES = [
    "Hot Insulation",
    "Cold Insulation",
    "Personnel Protection",
    "Acoustic Insulation",
    "CUI Prevention",
    "Fire Protection",
    "Heat Tracing (Electric/Steam)",
]

INSULATION_MATERIALS = [
    "Rockwool / Mineral Wool",
    "Calcium Silicate",
    "PUF / PIR (Polyurethane)",
    "Aerogel (Pyrogel / Cryogel)",
    "Glass Wool / Fiberglass",
    "Perlite",
    "Cellular Glass (Foamglas)",
    "Calcium Carbonate",
    "Phenolic Foam",
    "Elastomeric (Armaflex)",
]

PWHT_METHODS = [
    "Electrical Resistance (Ceramic Pads)",
    "Gas Firing (Local Flame)",
    "Induction Heating",
    "Furnace (Full Body)",
    "Internal Firing",
]

PWHT_RESULTS = ["Accept", "Reject", "Pending", "Concession"]

TORQUE_METHODS = [
    "Manual Torque Wrench",
    "Hydraulic Torque Wrench",
    "Hydraulic Tensioner",
    "Pneumatic Torque Tool",
    "Direct Tension Indicator (DTI)",
    "Ultrasonic Bolt Measurement",
]

REINST_ITEM_TYPES = [
    "Gasket Replacement",
    "Spade / Blind Removal",
    "Orifice Plate Installation",
    "Control Valve Re-installation",
    "Safety / Relief Valve Re-installation",
    "Instrument Re-connection",
    "Strainer / Filter Element",
    "Check Valve Re-installation",
    "Spectacle Blind Swapped",
    "Steam Trap Re-installation",
]

# ═══════════════════════════════════════════════════════════
#  14. SITE OPERATIONS & WORK FRONT MANAGEMENT
# ═══════════════════════════════════════════════════════════

PRIORITY_LEVELS = ["Low", "Normal", "High", "Urgent"]

RFI_STATUSES = ["Open", "Answered", "Closed", "Cancelled"]
RFI_PRIORITIES = ["Low", "Normal", "High", "Urgent"]

WORK_FRONT_ACTIVITIES = [
    "Material Handling",
    "Fit-up",
    "Welding",
    "NDT",
    "Repair",
    "Pipe Erection",
    "Support Installation",
    "Spool Installation",
    "Valve Installation",
    "Line Check / Walkdown",
    "Pressure Test",
    "Flushing / Blowing",
    "Punch Clearance",
    "Painting / Insulation",
    "Documentation / Dossier",
    "Scaffolding",
    "Rigging & Lifting",
    "Tie-in / Hot Tap",
]

WORK_FRONT_STATUSES = [
    "Planned", "Ready", "Assigned", "In Progress",
    "Waiting", "Completed", "Blocked",
]

READINESS_CONSTRAINTS = [
    "Ready", "Material", "Drawing/ISO", "Access", "Permit",
    "Equipment", "Manpower", "QC/NDT", "Scaffolding", "Blocked",
]

RESOURCE_STATUSES = ["Available", "Busy", "Standby", "Maintenance", "Unavailable"]

# ═══════════════════════════════════════════════════════════
#  15. PROCUREMENT & MATERIAL TRACKING
# ═══════════════════════════════════════════════════════════

PROCUREMENT_STATUSES = [
    "MTO Issued",
    "RFQ Sent",
    "PO Placed",
    "In Manufacturing",
    "Ready for Shipment",
    "In Transit",
    "Received at Yard",
    "QC Inspected",
    "Released to Fabrication",
    "Issued to Site",
]

UNITS_OF_MEASUREMENT = [
    "EA (Pieces)", "M (Meters)", "FT (Feet)", "KG", "MT (Metric Tons)",
    "SET", "LOT", "DIA-INCH", "DIA-MM", "LM (Linear Meters)",
]

# ═══════════════════════════════════════════════════════════
#  16. WELDER QUALIFICATION (ASME IX / AWS D1.1)
# ═══════════════════════════════════════════════════════════

QUALIFICATION_POSITIONS = [
    "1G (Flat)", "2G (Horizontal)", "3G (Vertical Up)",
    "4G (Overhead)", "5G (Multiple Fixed)", "6G (Inclined 45°)",
    "6GR (With Restriction Ring)", "1F / 2F / 3F / 4F (Fillet)",
    "All Positions (1G to 6G)",
]

WELDER_QUALIFICATION_STATUSES = [
    "Active / Valid",
    "Expiring (≤30 Days)",
    "Expired",
    "Deactivated",
    "Suspended",
]

# ═══════════════════════════════════════════════════════════
#  17. COLOR PALETTE & UI CONSTANTS
# ═══════════════════════════════════════════════════════════

STATUS_COLORS = {
    "Accepted":  "#10b981",
    "Passed":    "#10b981",
    "Completed": "#10b981",
    "Active":    "#3b82f6",
    "Pending":   "#f59e0b",
    "Waiting":   "#f59e0b",
    "Rejected":  "#ef4444",
    "Failed":    "#ef4444",
    "Expired":   "#ef4444",
    "Blocked":   "#ef4444",
    "Cancelled": "#6b7280",
    "Draft":     "#6b7280",
    "Open":      "#f59e0b",
    "Closed":    "#10b981",
}

# ═══════════════════════════════════════════════════════════
#  18. MISCELLANEOUS & LOOKUP TABLES
# ═══════════════════════════════════════════════════════════

PIPE_SCHEDULES = [
    "SCH 5S", "SCH 10", "SCH 10S", "SCH 20", "SCH 30",
    "SCH 40", "SCH 40S", "STD", "SCH 60", "SCH 80",
    "SCH 80S", "XS", "SCH 100", "SCH 120", "SCH 140",
    "SCH 160", "XXS",
]

NOMINAL_PIPE_SIZES = [
    '1/2"', '3/4"', '1"', '1-1/4"', '1-1/2"', '2"', '2-1/2"',
    '3"', '4"', '5"', '6"', '8"', '10"', '12"', '14"', '16"',
    '18"', '20"', '22"', '24"', '26"', '28"', '30"', '32"',
    '34"', '36"', '40"', '42"', '48"', '52"', '56"', '60"',
]

FLANGE_FACING_TYPES = [
    "Raised Face (RF)",
    "Flat Face (FF)",
    "Ring Type Joint (RTJ)",
    "Tongue & Groove (T&G)",
    "Male & Female (M&F)",
]

GASKET_TYPES = [
    "Spiral Wound (SS316/Graphite)",
    "Spiral Wound (SS304/PTFE)",
    "Ring Joint (R-Type)",
    "Ring Joint (RX-Type)",
    "Ring Joint (BX-Type)",
    "Flat Non-Asbestos",
    "PTFE Envelope",
    "Kammprofile",
    "Metal Jacketed",
    "Rubber (EPDM/NBR)",
]