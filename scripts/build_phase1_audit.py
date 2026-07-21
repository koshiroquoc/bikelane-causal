"""Build the Phase 1 feasibility artifacts without estimating treatment effects."""

from __future__ import annotations

import heapq
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from shapely import union_all


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

TRACKER_URL = (
    "https://www.chicago.gov/city/en/sites/complete-streets-chicago/home/"
    "bike-program/planned-bike-projects.html"
)
GEOMETRY_URL = "https://data.cityofchicago.org/resource/hvv9-38ut.geojson"


def norm(value: object) -> str:
    text = str(value).upper().replace("&", " AND ")
    text = text.replace("BALBOA", "BALBO")
    text = re.sub(r"DR\.? MARTIN LUTHER KING JR\.?", "MLK", text)
    text = re.sub(r"MARTIN LUTHER KING JR\.?", "MLK", text)
    text = re.sub(r"\b(N|S|E|W)\b", " ", text)
    text = re.sub(
        r"\b(STREET|ST|AVENUE|AVE|BOULEVARD|BLVD|ROAD|RD|DRIVE|DR|PLACE|PL|"
        r"PARKWAY|PKWY|TERRACE|TER)\b",
        " ",
        text,
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(*parts: object) -> str:
    return "_".join(
        re.sub(r"[^A-Z0-9]+", "_", str(part).upper()).strip("_") for part in parts
    )


def load_candidates() -> pd.DataFrame:
    frames = []
    for year in (2024, 2025):
        frame = pd.read_csv(REFERENCE / f"cdot_candidates_{year}.csv")
        frame["source_row"] = frame.apply(
            lambda r: f"{r.street}|{r.from_street}|{r.to_street}|{year}", axis=1
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


CONSOLIDATION_GROUPS = {
    "16TH_CENTRAL_PARK_KEDZIE_2024": {
        "keys": {"16th|Central Park|Homan|2024", "16th|Spaulding|Kedzie|2024"},
        "street": "16th",
        "from_street": "Central Park",
        "to_street": "Kedzie",
    },
    "HALSTED_59TH_PERSHING_2024": {
        "keys": {"Halsted|59th|47th|2024", "Halsted|47th|Pershing|2024"},
        "street": "Halsted",
        "from_street": "59th",
        "to_street": "Pershing",
    },
    "HOMAN_ROOSEVELT_HARRISON_2024": {
        "keys": {
            "Homan|Arthington|Lexington|2024",
            "Homan|Flournoy|Harrison|2024",
            "Homan|Roosevelt|Greenshaw|2024",
        },
        "street": "Homan",
        "from_street": "Roosevelt",
        "to_street": "Harrison",
    },
    "JACKSON_OAKLEY_OGDEN_2024": {
        "keys": {"Jackson|Oakley|Hoyne|2024", "Jackson|Damen|Ogden|2024"},
        "street": "Jackson",
        "from_street": "Oakley",
        "to_street": "Ogden",
    },
}


def consolidate_corridors(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    combine_keys = set().union(
        *(group["keys"] for group in CONSOLIDATION_GROUPS.values())
    )
    records: list[dict] = []
    source_rows: dict[str, list[dict]] = {}

    for _, row in raw[~raw.source_row.isin(combine_keys)].iterrows():
        cid = slug(row.street, row.from_street, row.to_street, row.installation_year)
        source_rows[cid] = [row.to_dict()]
        records.append(
            {
                "corridor_id": cid,
                "street": row.street,
                "from_street": row.from_street,
                "to_street": row.to_street,
                "facility": row.facility,
                "treatment_variant": (
                    "new_protected"
                    if row.facility == "Protected Bike Lane"
                    else "protection_upgrade"
                ),
                "installation_year": int(row.installation_year),
                "length_miles": float(row.length_miles),
                "segment_count": 1,
                "source_segments": row.source_row,
            }
        )

    for cid, definition in CONSOLIDATION_GROUPS.items():
        combined = raw[raw.source_row.isin(definition["keys"])].copy()
        if len(combined) != len(definition["keys"]):
            raise ValueError(f"Missing source rows for consolidation {cid}")
        source_rows[cid] = combined.to_dict("records")
        facilities = sorted(combined.facility.unique())
        facility = facilities[0] if len(facilities) == 1 else ";".join(facilities)
        records.append(
            {
                "corridor_id": cid,
                "street": definition["street"],
                "from_street": definition["from_street"],
                "to_street": definition["to_street"],
                "facility": facility,
                "treatment_variant": (
                    "new_protected"
                    if facility == "Protected Bike Lane"
                    else "protection_upgrade"
                ),
                "installation_year": 2024,
                "length_miles": float(combined.length_miles.sum()),
                "segment_count": len(combined),
                "source_segments": ";".join(combined.source_row),
            }
        )

    corridors = pd.DataFrame(records).sort_values(
        ["installation_year", "street", "from_street"]
    )
    return corridors.reset_index(drop=True), source_rows


PROVENANCE = {
    "24TH_MARSHALL_CALIFORNIA_2024": {
        "completion_month": "2024-08",
        "title": "Complete Streets upgrades on 24th largely finished",
        "url": "https://chi.streetsblog.org/2024/08/26/so-far-the-complete-streets-upgrades-on-24th-in-little-village-are-going-swimmingly-in-a-bad-way",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "Source reports concrete curb separation installed in early August 2024; use August as the first verified usable month.",
    },
    "CLARK_GRAND_OAK_2024": {
        "completion_month": "2024-07",
        "title": "Riding Chicago's new Clark Street protected lane",
        "url": "https://chi.streetsblog.org/2024/07/06/how-im-feeling-now-about-clark-street-riding-on-chicagos-new-all-green-protected-brat-lane",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "The full corridor was rideable in early July; remaining finish work continued into late July/early August. The transition month is excluded from estimation.",
    },
    "DOUGLAS_INDEPENDENCE_SACRAMENTO_2024": {
        "completion_month": "2024-10",
        "title": "CDOT added concrete protection to Douglas and Franklin",
        "url": "https://chi.streetsblog.org/2024/10/15/enthusiasm-for-curbs-cdot-has-added-concrete-protection-to-west-sides-douglas-and-franklin-boulevards",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "First verified usable month is October 2024; this is a concrete upgrade of a previously delineated protected lane.",
    },
    "FRANKLIN_CENTRAL_PARK_SACRAMENTO_2024": {
        "completion_month": "2024-10",
        "title": "CDOT added concrete protection to Douglas and Franklin",
        "url": "https://chi.streetsblog.org/2024/10/15/enthusiasm-for-curbs-cdot-has-added-concrete-protection-to-west-sides-douglas-and-franklin-boulevards",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "First verified usable month is October 2024; this is a concrete upgrade of an existing protected lane.",
    },
    "GRAND_CHICAGO_DAMEN_2024": {
        "completion_month": "2024-07",
        "title": "CDOT ribbon cutting for Grand Avenue protected lanes",
        "url": "https://chi.streetsblog.org/2024/07/18/this-is-grand-cdot-cuts-ribbon-on-new-protected-bike-lanes-on-a-key-west-side-diagonal-street",
        "corroborating": "https://nwnachicago.org/project__grand_avenue.php",
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "Ribbon cutting occurred on 2024-07-18; July is the verified usable month and is excluded as transition.",
    },
    "HALSTED_ROOSEVELT_VAN_BUREN_2024": {
        "completion_month": "2024-11",
        "title": "Halsted Street bicycle-lane project roadwork",
        "url": "https://today.uic.edu/halsted-street-bicycle-lane-project-roadwork/",
        "corroborating": "https://www.reddit.com/r/chibike/comments/1h3ff14/finally_protected_bike_lane_on_halstead_by_uic/",
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "UIC announced work beginning 2024-10-29; dated rider evidence verifies barriers by 2024-11-30.",
    },
    "MILWAUKEE_CALIFORNIA_LOGAN_2024": {
        "completion_month": "2024-12",
        "title": "New Milwaukee protected lanes ready to ride",
        "url": "https://chi.streetsblog.org/2024/12/05/take-a-virtual-ride-on-the-new-parking-to-pbl-conversion-on-milwaukee-between-kedzie-and-california",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "Article reports CDOT announced the segment ready on 2024-12-04.",
    },
    "WABASH_ROOSEVELT_BALBOA_2024": {
        "completion_month": "2024-12",
        "title": "Bike Lane Fest 2024 documents new Wabash PBLs",
        "url": "https://chi.streetsblog.org/2025/01/02/part-4-of-sbcs-bike-lane-fest-2024-west-side",
        "corroborating": "https://www.reddit.com/r/chibike/comments/1fslnxq/s_loop_wabash_bike_lanes_finally_getting_barriers/",
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "Official tracker confirms a 2024 installation; construction was documented in fall and the completed facility was verified by year-end. December is a conservative first-verified month, not a claimed opening date.",
    },
    "BELMONT_MILWAUKEE_KIMBALL_2025": {
        "completion_month": "2025-08",
        "title": "Belmont protected bike lanes completed",
        "url": "https://chi.streetsblog.org/2025/08/29/eyes-on-the-street-take-a-virtual-ride-on-the-nifty-new-protected-bike-lanes-on-belmont-between-milwaukee-and-kimball",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "fallback_short_post",
        "notes": "Outside the preferred 12-post-month window; retain only for a 9/9 fallback design.",
    },
}


BIKE_LANE_FEST_IDS = {
    "16TH_CENTRAL_PARK_KEDZIE_2024",
    "CANAL_ROOSEVELT_TAYLOR_2024",
    "DAMEN_17TH_14TH_2024",
    "HARRISON_ASHLAND_HALSTED_2024",
    "HOMAN_ROOSEVELT_HARRISON_2024",
    "JACKSON_OAKLEY_OGDEN_2024",
    "KEELER_HARRISON_CONGRESS_2024",
    "PAULINA_CONGRESS_WARREN_2024",
    "TAYLOR_MORGAN_CANAL_2024",
}

for corridor_id in BIKE_LANE_FEST_IDS:
    PROVENANCE[corridor_id] = {
        "completion_month": "2024-12",
        "title": "Bike Lane Fest 2024 field audit of newly installed facilities",
        "url": "https://chi.streetsblog.org/2025/01/02/part-4-of-sbcs-bike-lane-fest-2024-west-side",
        "corroborating": TRACKER_URL,
        "confidence": "medium",
        "status": "primary_candidate",
        "notes": "CDOT lists the project as installed in 2024 and a field audit completed on 2024-12-28/2025-01-01 documents the facility. December is the conservative first verified usable month, not a claimed opening month; timing sensitivity is required.",
    }


PRIMARY_IDS = [
    "24TH_MARSHALL_CALIFORNIA_2024",
    "CLARK_GRAND_OAK_2024",
    "DOUGLAS_INDEPENDENCE_SACRAMENTO_2024",
    "FRANKLIN_CENTRAL_PARK_SACRAMENTO_2024",
    "GRAND_CHICAGO_DAMEN_2024",
    "HALSTED_ROOSEVELT_VAN_BUREN_2024",
    "MILWAUKEE_CALIFORNIA_LOGAN_2024",
    "WABASH_ROOSEVELT_BALBOA_2024",
] + sorted(BIKE_LANE_FEST_IDS)


MANUAL_ROUTE_SELECTORS = {
    "24TH_MARSHALL_CALIFORNIA_2024": [("24TH", "MARSHALL", "CALIFORNIA")],
    "CLARK_GRAND_OAK_2024": [("CLARK", "GRAND", "OAK")],
    "DOUGLAS_INDEPENDENCE_SACRAMENTO_2024": [("DOUGLAS", "RIDGEWAY", "SACRAMENTO")],
    "FRANKLIN_CENTRAL_PARK_SACRAMENTO_2024": [("FRANKLIN", "CENTRAL PARK", "SACRAMENTO")],
    "GRAND_CHICAGO_DAMEN_2024": [("GRAND", "CHICAGO", "DAMEN")],
    "HALSTED_ROOSEVELT_VAN_BUREN_2024": [
        ("HALSTED", "ROOSEVELT", "HARRISON"),
        ("HALSTED", "HARRISON", "VAN BUREN"),
    ],
    "MILWAUKEE_CALIFORNIA_LOGAN_2024": [
        ("MILWAUKEE", "CALIFORNIA", "SACRAMENTO"),
        ("MILWAUKEE", "SACRAMENTO", "LOGAN"),
    ],
    "WABASH_ROOSEVELT_BALBOA_2024": [("WABASH", "ROOSEVELT", "BALBO")],
}


def shortest_street_path(group: pd.DataFrame, start: str, goal: str) -> list[int]:
    adjacency: dict[str, list[tuple[float, str, int]]] = defaultdict(list)
    for idx, row in group.iterrows():
        a, b = row.f_norm, row.t_norm
        weight = float(row.mi_ctrline)
        adjacency[a].append((weight, b, idx))
        adjacency[b].append((weight, a, idx))
    if start not in adjacency or goal not in adjacency:
        return []
    queue: list[tuple[float, str, list[int]]] = [(0.0, start, [])]
    best = {start: 0.0}
    while queue:
        distance, node, path = heapq.heappop(queue)
        if node == goal:
            return path
        if distance > best.get(node, math.inf):
            continue
        for weight, nxt, idx in adjacency[node]:
            proposal = distance + weight
            if proposal < best.get(nxt, math.inf):
                best[nxt] = proposal
                heapq.heappush(queue, (proposal, nxt, path + [idx]))
    return []


def match_segment(routes: gpd.GeoDataFrame, segment: dict) -> tuple[list[int], str]:
    group = routes[routes.street_norm == norm(segment["street"])]
    if group.empty:
        return [], "no_street_match"
    path = shortest_street_path(
        group, norm(segment["from_street"]), norm(segment["to_street"])
    )
    if path:
        return path, "endpoint_path"
    expected = float(segment["length_miles"])
    scored = group.assign(
        relative_length_error=(group.mi_ctrline.astype(float) - expected).abs()
        / max(expected, 0.05)
    ).sort_values("relative_length_error")
    best = scored.iloc[0]
    if float(best.relative_length_error) <= 0.25:
        return [int(best.name)], "length_fallback"
    return [], "no_reliable_match"


def build_geometries(
    corridors: pd.DataFrame, source_rows: dict[str, list[dict]]
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    routes = gpd.read_file(REFERENCE / "chicago_bike_routes_current.geojson")
    routes["street_norm"] = routes.street.map(norm)
    routes["f_norm"] = routes.f_street.map(norm)
    routes["t_norm"] = routes.t_street.map(norm)

    geometries = []
    audits = []
    for row in corridors.itertuples(index=False):
        selected: list[int] = []
        methods: list[str] = []
        if row.corridor_id in MANUAL_ROUTE_SELECTORS:
            for street, from_street, to_street in MANUAL_ROUTE_SELECTORS[row.corridor_id]:
                mask = (
                    (routes.street_norm == norm(street))
                    & (
                        (
                            (routes.f_norm == norm(from_street))
                            & (routes.t_norm == norm(to_street))
                        )
                        | (
                            (routes.f_norm == norm(to_street))
                            & (routes.t_norm == norm(from_street))
                        )
                    )
                )
                hits = routes.index[mask].tolist()
                if len(hits) != 1:
                    raise ValueError(
                        f"Manual selector for {row.corridor_id} returned {len(hits)} rows"
                    )
                selected.extend(hits)
            methods.append("manual_endpoint_verified")
        else:
            for segment in source_rows[row.corridor_id]:
                hits, method = match_segment(routes, segment)
                selected.extend(hits)
                methods.append(method)

        selected = list(dict.fromkeys(selected))
        geometry = union_all(routes.loc[selected].geometry.tolist()) if selected else None
        geometry_miles = (
            float(routes.loc[selected].mi_ctrline.astype(float).sum()) if selected else np.nan
        )
        length_error = (
            abs(geometry_miles - row.length_miles) / row.length_miles
            if selected and row.length_miles > 0
            else np.nan
        )
        status = (
            "verified_primary"
            if row.corridor_id in PRIMARY_IDS and selected and length_error <= 0.25
            else "primary_geometry_problem"
            if row.corridor_id in PRIMARY_IDS
            else "matched"
            if selected and length_error <= 0.25
            else "approximate"
            if selected
            else "unmatched"
        )
        geometries.append(geometry)
        audits.append(
            {
                "corridor_id": row.corridor_id,
                "geometry_match_status": status,
                "match_method": ";".join(methods),
                "matched_route_features": len(selected),
                "tracker_length_miles": row.length_miles,
                "geometry_length_miles": round(geometry_miles, 4)
                if selected
                else np.nan,
                "relative_length_error": round(length_error, 4)
                if selected
                else np.nan,
            }
        )

    geo = gpd.GeoDataFrame(corridors.copy(), geometry=geometries, crs=routes.crs)
    return geo, pd.DataFrame(audits)


def build_inventory(corridors: pd.DataFrame, geometry_audit: pd.DataFrame) -> pd.DataFrame:
    records = []
    for row in corridors.itertuples(index=False):
        source = PROVENANCE.get(row.corridor_id)
        if source is None:
            source = {
                "completion_month": "",
                "title": f"CDOT Planned Bike Projects — {row.installation_year} (year only)",
                "url": TRACKER_URL,
                "corroborating": "",
                "confidence": "low",
                "status": "date_research_needed",
                "notes": "Official tracker confirms installation year but does not identify a usable month; excluded from the primary sample pending stronger provenance.",
            }
        completion = source["completion_month"]
        first_post = (
            str(pd.Period(completion, freq="M") + 1) if completion else ""
        )
        records.append(
            {
                "corridor_id": row.corridor_id,
                "street": row.street,
                "from_street": row.from_street,
                "to_street": row.to_street,
                "lane_type": row.facility,
                "treatment_variant": row.treatment_variant,
                "installation_year": row.installation_year,
                "length_miles": round(row.length_miles, 2),
                "completion_month": completion,
                "first_post_month": first_post,
                "date_source_title": source["title"],
                "date_source_url": source["url"],
                "corroborating_source_url": source["corroborating"],
                "geometry_source_url": GEOMETRY_URL,
                "date_confidence": source["confidence"],
                "inventory_status": source["status"],
                "primary_eligible": row.corridor_id in PRIMARY_IDS,
                "notes": source["notes"],
            }
        )
    inventory = pd.DataFrame(records).merge(
        geometry_audit[["corridor_id", "geometry_match_status"]],
        on="corridor_id",
        how="left",
    )
    return inventory


def period_range(center: str) -> tuple[list[str], list[str]]:
    completion = pd.Period(center, freq="M")
    pre = [str(completion - i) for i in range(12, 0, -1)]
    post = [str(completion + i) for i in range(1, 13)]
    return pre, post


def build_station_audit(
    primary_geo: gpd.GeoDataFrame,
    all_geo: gpd.GeoDataFrame,
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    stations = pd.read_parquet(ROOT / "data" / "input" / "station_master.parquet")
    panel = pd.read_parquet(ROOT / "data" / "input" / "station_month_panel.parquet")
    station_geo = gpd.GeoDataFrame(
        stations.copy(),
        geometry=gpd.points_from_xy(stations.lng, stations.lat),
        crs="EPSG:4326",
    ).to_crs("EPSG:26916")
    primary_m = primary_geo.to_crs("EPSG:26916")
    all_matched_m = all_geo[all_geo.geometry.notna()].to_crs("EPSG:26916")

    primary_distances = pd.DataFrame(
        {
            cid: station_geo.geometry.distance(geom)
            for cid, geom in zip(primary_m.corridor_id, primary_m.geometry)
        },
        index=station_geo.index,
    )
    nearest_id = primary_distances.idxmin(axis=1)
    nearest_distance = primary_distances.min(axis=1)
    all_candidate_distance = pd.concat(
        [station_geo.geometry.distance(geom) for geom in all_matched_m.geometry], axis=1
    ).min(axis=1)
    within_primary_count = (primary_distances <= 300).sum(axis=1)
    completion_map = inventory.set_index("corridor_id").completion_month.to_dict()
    assigned_id = []
    overlapping_different_month = []
    for idx in primary_distances.index:
        nearby = primary_distances.columns[primary_distances.loc[idx] <= 300].tolist()
        if not nearby:
            assigned_id.append(nearest_id.loc[idx])
            overlapping_different_month.append(False)
            continue
        nearby = sorted(
            nearby,
            key=lambda cid: (
                pd.Period(completion_map[cid], freq="M"),
                primary_distances.loc[idx, cid],
            ),
        )
        assigned_id.append(nearby[0])
        overlapping_different_month.append(
            len({completion_map[cid] for cid in nearby}) > 1
        )

    assignment = np.select(
        [
            nearest_distance <= 300,
            nearest_distance <= 800,
            all_candidate_distance <= 800,
        ],
        ["treated", "donut", "candidate_corridor_exclusion"],
        default="control_candidate",
    )

    observed = panel.groupby("station_id").month.agg(lambda x: set(x.astype(str)))
    required_observed = []
    pre_observed = []
    post_observed = []
    for station_id, cid in zip(station_geo.station_id, assigned_id):
        pre, post = period_range(completion_map[cid])
        months = observed.get(station_id, set())
        pre_count = sum(month in months for month in pre)
        post_count = sum(month in months for month in post)
        pre_observed.append(pre_count)
        post_observed.append(post_count)
        required_observed.append(pre_count == 12 and post_count == 12)

    name_id_counts = stations.groupby("name").station_id.nunique()
    possible_alias = stations.name.map(name_id_counts).fillna(1).gt(1)
    station_audit = pd.DataFrame(
        {
            "station_id": station_geo.station_id,
            "name": station_geo.name,
            "lat": station_geo.lat,
            "lng": station_geo.lng,
            "nearest_primary_corridor": nearest_id,
            "assigned_primary_corridor": assigned_id,
            "distance_to_primary_m": nearest_distance.round(1),
            "distance_to_any_2024_2025_candidate_m": all_candidate_distance.round(1),
            "assignment": assignment,
            "overlapping_primary_corridors": within_primary_count,
            "overlap_has_different_completion_month": overlapping_different_month,
            "pre_months_observed": pre_observed,
            "post_months_observed": post_observed,
            "stable_12_pre_12_post": required_observed,
            "possible_same_name_id_alias": possible_alias,
        }
    )
    station_audit["primary_analysis_eligible"] = (
        (station_audit.assignment == "treated")
        & station_audit.stable_12_pre_12_post
    )

    panel = panel.assign(month_period=pd.PeriodIndex(panel.month, freq="M"))
    pretrend_rows = []
    for corridor in primary_geo.corridor_id:
        completion = completion_map[corridor]
        pre, _ = period_range(completion)
        treated_ids = station_audit.loc[
            station_audit.primary_analysis_eligible
            & (station_audit.assigned_primary_corridor == corridor)
            ,
            "station_id",
        ]
        local_mask = (
            (station_audit.assignment == "control_candidate")
            & (primary_distances[corridor] > 800)
            & (primary_distances[corridor] <= 3000)
        )
        local_ids = station_audit.loc[local_mask, "station_id"]
        local_complete = [
            sid for sid in local_ids if all(month in observed.get(sid, set()) for month in pre)
        ]

        subset = panel[panel.month.astype(str).isin(pre)].copy()
        treated_month = (
            subset[subset.station_id.isin(treated_ids)]
            .groupby("month")
            .total_trips.mean()
            .reindex(pre)
        )
        control_month = (
            subset[subset.station_id.isin(local_complete)]
            .groupby("month")
            .total_trips.mean()
            .reindex(pre)
        )
        x = np.arange(12)
        treated_slope = (
            np.polyfit(x, np.log1p(treated_month), 1)[0]
            if treated_month.notna().all() and len(treated_ids) > 0
            else np.nan
        )
        control_slope = (
            np.polyfit(x, np.log1p(control_month), 1)[0]
            if control_month.notna().all() and len(local_complete) > 0
            else np.nan
        )
        pretrend_rows.append(
            {
                "corridor_id": corridor,
                "stable_treated_stations": len(treated_ids),
                "complete_local_controls_0_8_to_3km": len(local_complete),
                "treated_pretrend_pct_per_month": round(100 * treated_slope, 3),
                "control_pretrend_pct_per_month": round(100 * control_slope, 3),
                "pretrend_gap_pct_points_per_month": round(
                    100 * (treated_slope - control_slope), 3
                ),
            }
        )

    pretrends = pd.DataFrame(pretrend_rows)
    summary = {
        "stations_total": int(len(station_audit)),
        "treated_stations": int((station_audit.assignment == "treated").sum()),
        "stable_treated_stations": int(
            station_audit.primary_analysis_eligible.sum()
        ),
        "donut_stations": int((station_audit.assignment == "donut").sum()),
        "candidate_corridor_exclusions": int(
            (station_audit.assignment == "candidate_corridor_exclusion").sum()
        ),
        "control_candidates": int(
            (station_audit.assignment == "control_candidate").sum()
        ),
        "multi_exposure_treated": int((within_primary_count > 1).sum()),
        "multi_exposure_different_month": int(sum(overlapping_different_month)),
        "possible_same_name_id_aliases": int(possible_alias.sum()),
        "primary_station_alias_flags": int(
            (
                station_audit.primary_analysis_eligible
                & station_audit.possible_same_name_id_alias
            ).sum()
        ),
    }
    return station_audit, pretrends, summary


def power_audit(station_audit: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    panel = pd.read_parquet(ROOT / "data" / "input" / "station_month_panel.parquet")
    month_counts = panel.groupby("station_id").month.nunique()
    full_ids = month_counts[month_counts == 36].index
    balanced = panel[panel.station_id.isin(full_ids)].copy()
    balanced["log_trips"] = np.log1p(balanced.total_trips)
    balanced["residual"] = (
        balanced.log_trips
        - balanced.groupby("station_id").log_trips.transform("mean")
        - balanced.groupby("month").log_trips.transform("mean")
        + balanced.log_trips.mean()
    )
    sigma = float(balanced.residual.std(ddof=1))
    ar1_values = []
    for _, group in balanced.sort_values("month").groupby("station_id"):
        if group.residual.std() > 0:
            ar1_values.append(group.residual.autocorr(1))
    rho = float(np.nanmedian(ar1_values))
    rho_for_design = min(max(rho, 0.0), 0.8)

    treated_counts = (
        station_audit[
            station_audit.primary_analysis_eligible
        ]
        .groupby("assigned_primary_corridor")
        .size()
    )
    k = int((treated_counts > 0).sum())
    mean_m = max(float(treated_counts[treated_counts > 0].mean()), 1.0)
    multiplier = stats.t.ppf(0.975, k - 1) + stats.norm.ppf(0.80)
    rows = []
    for icc in (0.10, 0.30, 0.50):
        design_effect = 1 + (mean_m - 1) * icc
        se = sigma * math.sqrt(
            (1 / 12 + 1 / 12)
            * ((1 + rho_for_design) / (1 - rho_for_design))
            * design_effect
            / (k * mean_m)
        )
        mde_log = multiplier * se
        rows.append(
            {
                "assumed_within_corridor_icc": icc,
                "mde_log_points": round(mde_log, 4),
                "mde_percent": round(100 * math.expm1(mde_log), 1),
            }
        )
    details = {
        "balanced_stations_used": int(len(full_ids)),
        "two_way_fe_residual_sd_log1p": round(sigma, 4),
        "median_station_ar1": round(rho, 4),
        "design_ar1_capped": round(rho_for_design, 4),
        "independent_corridors": k,
        "mean_stable_treated_stations_per_corridor": round(mean_m, 2),
        "pre_months": 12,
        "post_months": 12,
        "power": 0.80,
        "alpha_two_sided": 0.05,
    }
    return pd.DataFrame(rows), details


def make_map(
    all_geo: gpd.GeoDataFrame,
    primary_geo: gpd.GeoDataFrame,
    station_audit: pd.DataFrame,
) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    stations = gpd.GeoDataFrame(
        station_audit.copy(),
        geometry=gpd.points_from_xy(station_audit.lng, station_audit.lat),
        crs="EPSG:4326",
    )
    fig, ax = plt.subplots(figsize=(10, 12))
    matched = all_geo[all_geo.geometry.notna()]
    matched.plot(ax=ax, color="#cbd5e1", linewidth=0.7, alpha=0.55)
    colors = {
        "control_candidate": "#94a3b8",
        "candidate_corridor_exclusion": "#fbbf24",
        "donut": "#fb923c",
        "treated": "#0f766e",
    }
    sizes = {
        "control_candidate": 3,
        "candidate_corridor_exclusion": 5,
        "donut": 8,
        "treated": 15,
    }
    for label in colors:
        subset = stations[stations.assignment == label]
        subset.plot(
            ax=ax,
            color=colors[label],
            markersize=sizes[label],
            alpha=0.75,
            label=label.replace("_", " "),
        )
    primary_geo.plot(ax=ax, color="#7c3aed", linewidth=3.0, label="primary corridor")
    ax.set_title("Phase 1 preliminary station assignment", fontsize=16, weight="bold")
    ax.set_axis_off()
    ax.legend(loc="lower left", frameon=True, fontsize=8)
    fig.text(
        0.01,
        0.01,
        "Treated ≤300 m; donut 300–800 m; candidate exclusions are near another 2024–2025 corridor.",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "phase1_treatment_control_map.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    raw = load_candidates()
    corridors, source_rows = consolidate_corridors(raw)
    all_geo, geometry_audit = build_geometries(corridors, source_rows)
    inventory = build_inventory(corridors, geometry_audit)
    primary_geo = all_geo[all_geo.corridor_id.isin(PRIMARY_IDS)].copy()
    primary_geo["_order"] = primary_geo.corridor_id.map(
        {cid: i for i, cid in enumerate(PRIMARY_IDS)}
    )
    primary_geo = primary_geo.sort_values("_order").drop(columns="_order")

    station_audit, pretrends, station_summary = build_station_audit(
        primary_geo, all_geo, inventory
    )
    stable_counts_for_inventory = (
        station_audit[station_audit.primary_analysis_eligible]
        .groupby("assigned_primary_corridor")
        .size()
    )
    inventory["stable_treated_stations"] = (
        inventory.corridor_id.map(stable_counts_for_inventory).fillna(0).astype(int)
    )
    inventory["primary_eligible"] = (
        inventory.corridor_id.isin(PRIMARY_IDS)
        & (inventory.stable_treated_stations > 0)
        & (inventory.geometry_match_status == "verified_primary")
    )
    inventory.loc[
        inventory.corridor_id.isin(PRIMARY_IDS)
        & (inventory.stable_treated_stations == 0),
        "inventory_status",
    ] = "excluded_no_stable_station_within_300m"
    inventory.loc[
        inventory.primary_eligible, "inventory_status"
    ] = "primary_ready_phase2"
    mde, power_details = power_audit(station_audit)
    make_map(all_geo, primary_geo, station_audit)

    corridors_out = corridors.merge(geometry_audit, on="corridor_id", how="left")
    corridors_out.to_csv(REFERENCE / "corridor_candidates.csv", index=False)
    all_geo[all_geo.geometry.notna()].to_file(
        REFERENCE / "corridor_candidates.geojson", driver="GeoJSON"
    )
    inventory.to_csv(REFERENCE / "treatment_inventory.csv", index=False)
    station_audit.to_csv(REFERENCE / "preliminary_station_assignment.csv", index=False)
    geometry_audit.to_csv(REPORTS / "geometry_audit.csv", index=False)
    pretrends.to_csv(REPORTS / "pretrend_screen.csv", index=False)
    mde.to_csv(REPORTS / "power_audit.csv", index=False)

    treated_counts = (
        station_audit[
            station_audit.primary_analysis_eligible
        ]
        .groupby("assigned_primary_corridor")
        .size()
        .reindex(PRIMARY_IDS, fill_value=0)
    )
    max_share = (
        float(treated_counts.max() / treated_counts.sum()) if treated_counts.sum() else 1.0
    )
    summary = {
        "source_segments": int(len(raw)),
        "independent_candidate_corridors": int(len(corridors)),
        "candidate_geometries_matched": int(all_geo.geometry.notna().sum()),
        "primary_corridors": len(PRIMARY_IDS),
        "usable_primary_corridors": int((treated_counts > 0).sum()),
        "primary_date_confidence": inventory[
            inventory.corridor_id.isin(PRIMARY_IDS)
        ].date_confidence.value_counts().to_dict(),
        **station_summary,
        "stable_treated_by_corridor": treated_counts.to_dict(),
        "largest_corridor_station_share": round(max_share, 4),
        "minimum_complete_local_controls": int(
            pretrends.complete_local_controls_0_8_to_3km.min()
        ),
        "median_abs_pretrend_gap_pct_points_per_month": round(
            float(pretrends.pretrend_gap_pct_points_per_month.abs().median()), 3
        ),
        "power_inputs": power_details,
        "mde_percent_range": [float(mde.mde_percent.min()), float(mde.mde_percent.max())],
    }
    (REPORTS / "phase1_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    assert summary["source_segments"] == 52
    assert summary["independent_candidate_corridors"] == 47
    assert summary["usable_primary_corridors"] >= 8
    assert summary["stable_treated_stations"] >= 20
    assert summary["largest_corridor_station_share"] <= 0.30
    assert summary["minimum_complete_local_controls"] >= 10
    assert inventory.loc[inventory.primary_eligible, "completion_month"].notna().all()
    assert (
        inventory.loc[inventory.primary_eligible, "geometry_match_status"]
        == "verified_primary"
    ).all()
    assert not corridors_out.corridor_id.duplicated().any()
    assert not inventory.corridor_id.duplicated().any()
    assert not station_audit.station_id.duplicated().any()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
