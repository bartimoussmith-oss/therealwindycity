#!/usr/bin/env python3
import sqlite3

DB_NAME = "cheyenne_watchdog.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public_comment_battles (
            battle_id TEXT PRIMARY KEY,
            meeting_date DATE,
            forum TEXT,
            agenda_item TEXT,
            subject TEXT,
            miller_position TEXT,
            statutory_hooks TEXT,
            council_response TEXT,
            outcome_status TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS veracity_contradictions (
            contradiction_id TEXT PRIMARY KEY,
            topic TEXT,
            speaker_denial TEXT,
            date_denial DATE,
            quote_denial TEXT,
            speaker_validation TEXT,
            date_validation DATE,
            quote_validation TEXT,
            contradiction_type TEXT,
            significance TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS voucher_forensics (
            item_id TEXT PRIMARY KEY,
            check_date DATE,
            vendor TEXT,
            amount REAL,
            department TEXT,
            description TEXT,
            miller_claim TEXT,
            audit_status TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS environmental_zones (
            zone_id TEXT PRIMARY KEY,
            zone_name TEXT,
            geographic_scope TEXT,
            contaminants TEXT,
            exposure_pathway TEXT,
            remediation_status TEXT,
            development_friction_ratio TEXT
        )
    """)

    battles = [
        ("B-2026-01-12", "2026-01-12", "City Council", "Ordinance 2nd Reading", "Chapter 1.28 Inspection Warrants", "Opposed fishing expeditions to 'discover' violations.", "W.S. § 35-7-1046, W.S. § 5-6-101, Camara v. Municipal Court", "Vote postponed to review substitute text.", "Won: Council voted 6-4 to strike 'discover' and 'determine'."),
        ("B-2026-04-13", "2026-04-13", "City Council", "Resolution", "Reed Ave $5M Spend vs. Lead Infrastructure", "Fix the Lead First platform: Prioritize public health over aesthetics.", "BOPU Lead & Copper Rule compliance records", "Mayor claimed city can do both; Emmens disputed active poisoning.", "Ongoing: Exposed West Edge spending imbalance."),
        ("B-2026-04-20", "2026-04-20", "City Council", "Annexation Hearing", "Cox Ranch 1,260-Acre Annexation / First Amendment Gag Order", "Opposed viewpoint discrimination; developers heard while taxpayers gagged.", "U.S. Const. Amend. I, W.S. § 15-1-404/405", "Testimony repeatedly cut off with Points of Order.", "Formal Notice of constitutional violation placed on permanent record."),
        ("B-2026-05-11", "2026-05-11", "City Council", "Items #9, #22, #29A, #31A, #38", "Sweetgrass PUD, DDA Budget, BNSF, Story Blvd, AVI Modification", "Exposed DDA reserve depletion, AVI sole-sourcing, and 65:1 dev-to-cleanup ratio.", "W.S. § 15-1-404, Municipal Purchasing Code", "Councilman Wolf accused speaker of being a 'ChatGPT robot'.", "Voucher citations verified 100% accurate on amounts."),
        ("B-2026-08-24-A", "2026-08-24", "City Council", "Item 6A", "Capital City Hospitality Retail Liquor Transfer (3501 E Lincolnway)", "Exposed 2-year temporal collapse in application packet.", "W.S. § 12-4-104(d), W.S. § 12-4-201", "Hearing closed without substantive rebuttal; moved to Finance.", "Pending: Administrative record challenged for non-compliance."),
        ("B-2026-08-24-B", "2026-08-24", "City Council", "Item 9A", "School Resource Officer (SRO) MOU (Contract #149959)", "Demanded SROs enforce citation notice duties to maximize diversion.", "W.S. § 14-6-206(c), NASRO Triad Model", "Council adopted substitute clarifying 75/25 salary split.", "Directives established for diversion over municipal prosecution."),
        ("B-2026-08-24-C", "2026-08-24", "City Council", "Items 10a, 9f, 12a, 5", "DDA Staff Shift, Comp Plan Rollover, Aug 10 Minutes Walk-On", "Challenged unagendized declaratory judgment motion following executive session.", "W.S. § 16-4-405(a)(iii), W.S. § 15-1-409(c), W.S. § 22-23-1005", "Minutes captured motion but omitted executive session provenance.", "Documented 60-day statutory bar clock expiring September 16, 2026.")
    ]
    cur.executemany("INSERT OR REPLACE INTO public_comment_battles VALUES (?,?,?,?,?,?,?,?,?)", battles)

    contradictions = [
        ("V-01", "Governance Gap Post-BP Zoning", "Mayor Patrick Collins", "2026-04-13", "Claimed absence of future public process was 'factually incorrect'.", "Director Connor White", "2026-04-13", "Confirmed: 'There is no public process. No mailed notice. No discussion.'", "Direct Same-Meeting Denial-to-Validation", "Proves administrative elimination of public participation."),
        ("V-02", "Data Center Causation Behind Annexation", "Dr. Emmons (Chair)", "2026-05-17", "Restricted citizen speech stating hearing was 'not about data centers.'", "Councilman Wolf", "2026-05-17", "Confirmed: 'It is an indisputable fact it is about a data center.'", "Pretextual Speech Suppression", "Confirms procedural gag was based on false pretense."),
        ("V-03", "Storey Blvd Retaining Wall Origin", "Tom Cobb (City Engineer)", "2026-05-11", "Claimed landowner refused fill, necessitating $124,920 concrete wall.", "Rodney Stone (Owner)", "2026-05-11", "Public testimony: 'We do not want that wall. We never have.'", "Direct Eyewitness Reversal", "Exposes staff misrepresentation to justify construction line item."),
        ("V-04", "AVI Engineering Sole-Source Circumvention", "Mayor Patrick Collins", "2026-05-11", "Denied 'slush fund' characterization; defended contract as routine.", "Councilman Leborn & Mayor Collins", "2026-05-11", "Leborn admitted $74,500 was chosen to evade $75k threshold; Collins admitted funding came from 'siphoning salaries'.", "Administrative Circumvention Admission", "Validates ghost-salary and threshold evasion claims."),
        ("V-05", "Municipal Lead Water Pipe Risk", "Dr. Emmens", "2026-04-13", "Stated 'It's not there' regarding city water line contamination.", "Mayor Patrick Collins", "2025-12-22", "Conceded: 'We have some in our community... replacement could cost $100M-$200M.'", "Intra-Administration Reversal", "Exposes denial of public health hazard previously confirmed.")
    ]
    cur.executemany("INSERT OR REPLACE INTO veracity_contradictions VALUES (?,?,?,?,?,?,?,?,?,?)", contradictions)

    vouchers = [
        ("V-01", "2026-05-01", "Far Out Productions", 40000.00, "Parks & Rec", "Thanks for the Memories Concert", "Concert spend during fiscal constraints", "CONFIRMED EXACT"),
        ("V-01", "2026-05-01", "Far Out Productions", 40000.00, "Parks & Rec", "Thanks for the Memories Concert", "Concert spend during fiscal constraints", "CONFIRMED EXACT"),
        ("V-02", "2026-05-01", "Lotus Engineering", 12292.50, "Planning", "Climate Action Plan Consulting", "Discretionary consulting expenditure", "CONFIRMED EXACT"),
        ("V-03", "2026-05-01", "Rock Solid SST", 4448.00, "Police", "Firearm Suppressors", "Discretionary hardware expenditure", "CONFIRMED EXACT"),
        ("V-04", "2026-05-01", "Amazon.com", 833.40, "Various", "Amazon Flags and Banners", "Discretionary administrative spend", "CONFIRMED EXACT"),
        ("V-05", "2026-05-01", "PEAC Solutions", 979.20, "IT", "Copier Lease", "Recurring equipment lease", "CONFIRMED EXACT"),
        ("V-06", "2026-05-01", "ALSCO", 627.03, "Sanitation", "Uniform Laundry & Cleaning", "Operational laundry fees", "CONFIRMED EXACT")
    ]
    cur.executemany("INSERT OR REPLACE INTO voucher_forensics VALUES (?,?,?,?,?,?,?,?)", vouchers)

    env = [
        ("ZONE-1", "West Edge Brownfields", "Lower Capitol Basin (35 acres)", "PAHs, Petroleum, Heavy Metals, Mercury", "Floodplain leaching, rail run-off", "28 properties confirmed Phase II contamination", "135:1 Dev-to-Remediation Ratio"),
        ("ZONE-2", "Frontier Refinery Corridor", "Morrie Ave & Holiday Park sewers", "H2S, Ammonia, Volatile Organic Vapors", "Active vapor intrusion into public parks", "Active odor incidents documented by DEQ", "Critical Public Health Exposure"),
        ("ZONE-3", "UPRR Rail Yard Corridor", "Southern perimeter of West Edge", "Petroleum, heavy metals, unmapped solvents", "Groundwater migration, particulate dust", "Restricted access; unassessed liability", "Unmitigated Municipal Risk"),
        ("ZONE-4", "Atlas D Missile Site 4", "16 mi west / Borie Well Field", "Trichloroethylene (TCE)", "Deep bedrock aquifer infiltration (10-mile plume)", "Permanent carbon filtration required", "Critical Drinking Water Buffer Contamination")
    ]
    cur.executemany("INSERT OR REPLACE INTO environmental_zones VALUES (?,?,?,?,?,?,?)", env)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
