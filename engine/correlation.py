# -*- coding: utf-8 -*-
"""
OCEANIX — Core Attribution Engine
Calculates spatial and temporal correlation scores between oil spill
polygons and AIS vessel trajectories.
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

def compute_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    import math
    R = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class AttributionEngine:
    """
    Ranks vessel candidates based on how well their historical trajectory
    correlates with an observed oil spill.
    """
    
    def __init__(self):
        # Weights for the final score
        self.w_spatial = 0.40
        self.w_temporal = 0.30
        self.w_trajectory = 0.20
        self.w_anomaly = 0.10

    def rank_candidates(self, 
                       spill_centroid: Tuple[float, float], # (lat, lon)
                       spill_time: datetime,
                       candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes a list of vessel candidates with their historical tracks
        and returns a ranked list with correlation scores.
        """
        results = []
        
        for vessel in candidates:
            # 1. Spatial Score (How close did they get to the spill centroid?)
            min_dist = self._calculate_min_distance(vessel['track'], spill_centroid)
            spatial_score = max(0, 100 - (min_dist * 2)) # Drops to 0 at 50km
            
            # 2. Temporal Score (Were they there at the right time?)
            # Assuming oil spreads, we look for vessels present 1 to 24 hours BEFORE detection
            time_diff_hours = self._calculate_time_alignment(vessel['track'], spill_centroid, spill_time)
            temporal_score = self._score_time_diff(time_diff_hours)
            
            # 3. Trajectory Alignment (Does the vessel's path match the slick's shape?)
            trajectory_score = 70.0 # Placeholder: requires polygon intersection logic
            
            # 4. AIS Anomaly Score (Did they turn off AIS near the spill?)
            anomaly_score = self._detect_ais_gaps(vessel['track'])
            
            # Final Weighted Score
            total_score = (
                (spatial_score * self.w_spatial) +
                (temporal_score * self.w_temporal) +
                (trajectory_score * self.w_trajectory) +
                (anomaly_score * self.w_anomaly)
            )
            
            results.append({
                "mmsi": vessel.get("mmsi"),
                "name": vessel.get("name"),
                "type": vessel.get("vessel_type"),
                "total_score": round(total_score, 1),
                "metrics": {
                    "min_distance_km": round(min_dist, 2),
                    "time_alignment_score": round(temporal_score, 1),
                    "trajectory_score": round(trajectory_score, 1),
                    "anomaly_score": round(anomaly_score, 1)
                }
            })
            
        # Sort descending by total score
        results.sort(key=lambda x: x["total_score"], reverse=True)
        
        # Assign ranks
        for idx, res in enumerate(results):
            res["rank"] = idx + 1
            
        return results

    def _calculate_min_distance(self, track: List[Dict], centroid: Tuple[float, float]) -> float:
        if not track:
            return 999.9
        
        min_d = float('inf')
        for point in track:
            # Assuming point has 'lat', 'lon'
            d = compute_distance_km(point['lat'], point['lon'], centroid[0], centroid[1])
            if d < min_d:
                min_d = d
        return min_d

    def _calculate_time_alignment(self, track: List[Dict], centroid: Tuple[float, float], spill_time: datetime) -> float:
        """Find the time the vessel was closest to the centroid, and compare to spill detection time."""
        if not track:
            return 999.9
            
        closest_point = min(track, key=lambda p: compute_distance_km(p['lat'], p['lon'], centroid[0], centroid[1]))
        
        # Assuming closest_point['timestamp'] is a datetime object
        if 'timestamp' in closest_point and isinstance(closest_point['timestamp'], datetime):
            diff = (spill_time - closest_point['timestamp']).total_seconds() / 3600.0
            return diff
        return 999.9
        
    def _score_time_diff(self, diff_hours: float) -> float:
        """
        Ideal time is ~2-12 hours before detection.
        If it's after detection (negative), score is 0.
        If it's way before, score decays.
        """
        if diff_hours < 0:
            return 0.0
        if 2 <= diff_hours <= 12:
            return 100.0
        if diff_hours < 2:
            return 80.0
        # Decay after 12 hours
        score = 100.0 - ((diff_hours - 12) * 2)
        return max(0.0, score)

    def _detect_ais_gaps(self, track: List[Dict]) -> float:
        """Detect suspicious gaps in AIS transmission."""
        if len(track) < 2:
            return 0.0
            
        max_gap = 0.0
        # Assuming sorted by timestamp
        for i in range(1, len(track)):
            t1 = track[i-1].get('timestamp')
            t2 = track[i].get('timestamp')
            if t1 and t2:
                gap = (t2 - t1).total_seconds() / 3600.0
                if gap > max_gap:
                    max_gap = gap
                    
        # Gap > 4 hours is highly suspicious (score goes UP for anomalies)
        if max_gap > 4.0:
            return 100.0
        if max_gap > 2.0:
            return 60.0
        return 20.0 # Normal transmission
