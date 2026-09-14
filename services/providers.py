from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

class SatelliteDataProvider(ABC):
    """Abstract interface for satellite data providers (e.g., Copernicus Data Space)."""

    @abstractmethod
    def search_scenes(self, 
                      bbox: List[float], 
                      start_time: datetime, 
                      end_time: datetime, 
                      platform: str = "Sentinel-1") -> List[Dict[str, Any]]:
        """
        Search for available satellite scenes in a given bounding box and time range.
        bbox format: [min_lon, min_lat, max_lon, max_lat]
        """
        pass

    @abstractmethod
    def get_scene_metadata(self, scene_id: str) -> Dict[str, Any]:
        """Get detailed metadata for a specific scene."""
        pass
        
    @abstractmethod
    def download_scene(self, scene_id: str, output_dir: str) -> str:
        """
        Download the scene product to the given output directory.
        Returns the path to the downloaded file/folder.
        """
        pass


class AISProvider(ABC):
    """Abstract interface for AIS data providers (e.g., Global Fishing Watch, MarineTraffic)."""

    @abstractmethod
    def get_vessel_info(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """Get static vessel information by MMSI."""
        pass

    @abstractmethod
    def get_vessel_track(self, 
                         mmsi: str, 
                         start_time: datetime, 
                         end_time: datetime) -> List[Dict[str, Any]]:
        """Get historical AIS positions for a specific vessel."""
        pass
        
    @abstractmethod
    def search_vessels_in_area(self, 
                               bbox: List[float], 
                               start_time: datetime, 
                               end_time: datetime) -> List[Dict[str, Any]]:
        """
        Find all vessels that were present in a specific area during a specific time window.
        This is crucial for the correlation engine.
        """
        pass
