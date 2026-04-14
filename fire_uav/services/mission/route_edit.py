from __future__ import annotations

import math
from typing import Sequence

from fire_uav.module_core.geometry import haversine_m


def dedupe_path(points: Sequence[tuple[float, float]], *, threshold_m: float = 1.0) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for lat, lon in points:
        point = (float(lat), float(lon))
        if deduped and haversine_m(deduped[-1], point) <= threshold_m:
            continue
        deduped.append(point)
    return deduped


def split_route_for_edit(
    path: Sequence[tuple[float, float]],
    anchor: tuple[float, float],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    clean_path = dedupe_path(path)
    anchor_point = (float(anchor[0]), float(anchor[1]))
    if len(clean_path) < 2:
        return [], [anchor_point, anchor_point]

    nearest_wp_idx = 0
    nearest_wp_dist = float("inf")
    for idx, waypoint in enumerate(clean_path):
        distance = haversine_m(anchor_point, waypoint)
        if distance < nearest_wp_dist:
            nearest_wp_idx = idx
            nearest_wp_dist = distance

    nearest_seg_idx = 0
    nearest_seg_dist = float("inf")
    for idx in range(len(clean_path) - 1):
        distance = _point_to_segment_distance_m(anchor_point, clean_path[idx], clean_path[idx + 1])
        if distance < nearest_seg_dist:
            nearest_seg_idx = idx
            nearest_seg_dist = distance

    split_idx = nearest_wp_idx
    if nearest_seg_dist <= nearest_wp_dist:
        split_idx = nearest_seg_idx + 1

    split_idx = max(1, min(split_idx, len(clean_path) - 1))
    locked_prefix = dedupe_path([*clean_path[:split_idx], anchor_point])
    editable_tail = dedupe_path([anchor_point, *clean_path[split_idx:]])
    if len(editable_tail) < 2:
        editable_tail = [anchor_point, anchor_point]
    return locked_prefix, editable_tail


def _point_to_segment_distance_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    lat0_rad = math.radians((point[0] + start[0] + end[0]) / 3.0)
    point_xy = _project_local_m(point, lat0_rad)
    start_xy = _project_local_m(start, lat0_rad)
    end_xy = _project_local_m(end, lat0_rad)

    seg_x = end_xy[0] - start_xy[0]
    seg_y = end_xy[1] - start_xy[1]
    seg_len_sq = seg_x * seg_x + seg_y * seg_y
    if seg_len_sq <= 1e-9:
        return math.hypot(point_xy[0] - start_xy[0], point_xy[1] - start_xy[1])

    rel_x = point_xy[0] - start_xy[0]
    rel_y = point_xy[1] - start_xy[1]
    t = (rel_x * seg_x + rel_y * seg_y) / seg_len_sq
    t = max(0.0, min(1.0, t))
    proj_x = start_xy[0] + (seg_x * t)
    proj_y = start_xy[1] + (seg_y * t)
    return math.hypot(point_xy[0] - proj_x, point_xy[1] - proj_y)


def _project_local_m(point: tuple[float, float], lat0_rad: float) -> tuple[float, float]:
    earth_radius_m = 6371000.0
    lat_rad = math.radians(point[0])
    lon_rad = math.radians(point[1])
    x = earth_radius_m * lon_rad * math.cos(lat0_rad)
    y = earth_radius_m * lat_rad
    return x, y


__all__ = ["dedupe_path", "split_route_for_edit"]
