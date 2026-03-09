from __future__ import annotations

from datetime import datetime

from fire_uav.services.targets.target_tracker import (
    TargetObservation,
    TargetTrackState,
    TargetTracker,
)


def test_tracker_moves_confirmed_target_to_in_orbit_and_orbited() -> None:
    tracker = TargetTracker(
        match_radius_m=30.0,
        suppression_radius_m=60.0,
        suppression_ttl_s=180.0,
        stable_frames_n=1,
    )
    now = datetime.utcnow()
    updates = tracker.update(
        [TargetObservation(class_label="1", lat=56.0, lon=92.9, timestamp=now, confidence=0.8)]
    )
    assert updates and updates[0].should_confirm is True
    track_id = updates[0].track.track_id
    assert tracker._tracks[track_id].state == TargetTrackState.CONFIRMED

    assert tracker.mark_in_orbit(track_id) is True
    assert tracker._tracks[track_id].state == TargetTrackState.IN_ORBIT

    assert tracker.mark_orbited(track_id) is True
    assert tracker._tracks[track_id].state == TargetTrackState.ORBITED
