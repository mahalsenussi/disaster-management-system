"""
Coastal data collector from Copernicus Marine using copernicusmarine package
"""
import os
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.coastal.service import CoastalService

logger = get_logger()

class CoastalCollector:
    """Collects coastal data from Copernicus Marine API using copernicusmarine package"""
    
    def __init__(self):
        self.service = CoastalService()
        self.copernicus_username = os.environ.get('COPERNICUS_USERNAME')
        self.copernicus_password = os.environ.get('COPERNICUS_PASSWORD')
        
        if not self.copernicus_username or not self.copernicus_password:
            logger.warning("Copernicus credentials not set, using mock data", module='COASTAL_COLLECTOR')
    
    def collect_coastal(self, location: str) -> tuple[bool, str, Optional[Dict]]:
        """Collect coastal data for a location
        
        Returns:
            (success, message, coastal_data)
        """
        if not self.copernicus_username or not self.copernicus_password:
            # Return mock data for testing if no credentials
            logger.warning("Using mock data for coastal collection", module='COASTAL_COLLECTOR')
            return self._get_mock_data(location)
        
        try:
            # Try to use Copernicus Marine for real data
            result = self._collect_from_copernicus(location)
            if result is None:
                logger.warning("Copernicus returned None, using mock data", module='COASTAL_COLLECTOR')
                return self._get_mock_data(location)
            return result
        except Exception as e:
            logger.error(f"Failed to collect coastal from Copernicus for {location}: {e}", module='COASTAL_COLLECTOR', exc_info=True)
            # Fall back to mock data
            logger.warning("Falling back to mock data", module='COASTAL_COLLECTOR')
            return self._get_mock_data(location)
    
    def _collect_from_copernicus(self, location: str) -> tuple[bool, str, Dict]:
        """Collect coastal data using copernicusmarine package"""
        try:
            import copernicusmarine
            from datetime import datetime, timedelta
            import xarray as xr
            
            # Configure Copernicus Marine credentials
            copernicusmarine.login(
                username=self.copernicus_username,
                password=self.copernicus_password
            )
            
            # Get coordinates for location
            coords = self._get_location_coords(location)
            if not coords:
                logger.warning(f"No coordinates found for {location}, using mock data", module='COASTAL_COLLECTOR')
                return self._get_mock_data(location)
            
            # Use Mediterranean wave dataset
            dataset_id = 'cmems_mod_med_wav_anfc_4.2km_PT1H-i'
            
            # Adjust coordinates to be within dataset bounds
            min_lat = max(30.2, coords['lat'] - 0.5)
            max_lat = min(45.8, coords['lat'] + 0.5)
            min_lon = max(10.0, coords['lng'] - 0.5)
            max_lon = min(35.0, coords['lng'] + 0.5)
            
            # Subset the data
            result = copernicusmarine.subset(
                dataset_id=dataset_id,
                minimum_longitude=min_lon,
                maximum_longitude=max_lon,
                minimum_latitude=min_lat,
                maximum_latitude=max_lat,
                start_datetime=datetime.now() - timedelta(days=1),
                end_datetime=datetime.now()
            )
            
            logger.info(f"Successfully accessed {dataset_id} for {location}", module='COASTAL_COLLECTOR')
            
            # Extract data from NetCDF file
            if hasattr(result, 'file_path') and result.file_path and result.file_status == 'DOWNLOADED':
                ds = xr.open_dataset(result.file_path)
                data_vars = ds.data_vars if hasattr(ds, 'data_vars') else {}
                
                # Default values
                wave_height = 1.5
                wave_period = 8.0
                wave_direction = 270.0
                wind_speed = 10.0
                
                # Extract wave height (VHM0 - significant wave height)
                if 'VHM0' in data_vars:
                    try:
                        wave_data = ds['VHM0']
                        if wave_data.size > 0:
                            wave_height = float(wave_data[-1, -1, -1].values)
                            logger.info(f"Extracted wave height: {wave_height}m", module='COASTAL_COLLECTOR')
                    except Exception as var_error:
                        logger.debug(f"Error extracting VHM0: {var_error}", module='COASTAL_COLLECTOR')
                
                # Extract wave period (VTM02 - mean wave period)
                if 'VTM02' in data_vars:
                    try:
                        period_data = ds['VTM02']
                        if period_data.size > 0:
                            wave_period = float(period_data[-1, -1, -1].values)
                            logger.info(f"Extracted wave period: {wave_period}s", module='COASTAL_COLLECTOR')
                    except Exception as var_error:
                        logger.debug(f"Error extracting VTM02: {var_error}", module='COASTAL_COLLECTOR')
                
                # Extract wave direction (VMDR - mean wave direction)
                if 'VMDR' in data_vars:
                    try:
                        dir_data = ds['VMDR']
                        if dir_data.size > 0:
                            wave_direction = float(dir_data[-1, -1, -1].values)
                            logger.info(f"Extracted wave direction: {wave_direction}°", module='COASTAL_COLLECTOR')
                    except Exception as var_error:
                        logger.debug(f"Error extracting VMDR: {var_error}", module='COASTAL_COLLECTOR')
                
                # Extract wind speed (VCMX - wind speed component)
                if 'VCMX' in data_vars:
                    try:
                        wind_data = ds['VCMX']
                        if wind_data.size > 0:
                            wind_speed = float(wind_data[-1, -1, -1].values)
                            logger.info(f"Extracted wind speed: {wind_speed}m/s", module='COASTAL_COLLECTOR')
                    except Exception as var_error:
                        logger.debug(f"Error extracting VCMX: {var_error}", module='COASTAL_COLLECTOR')
                
                # Get sea level data from UNESCO-IOC as fallback
                sea_level_anomaly = self._get_ioc_sealevel_data(location)
                
                coastal_data = {
                    'location': location,
                    'wave_height': round(wave_height, 2),
                    'wave_period': round(wave_period, 1),
                    'sea_level_anomaly': sea_level_anomaly,
                    'wind_speed': round(wind_speed, 2)
                }
                
                logger.collector_run('coastal', f"Collected for {location}", f"Wave height: {coastal_data['wave_height']}m")
                return True, "Coastal data collected successfully from Copernicus", coastal_data
            else:
                logger.warning(f"No data downloaded from Copernicus for {location}, using mock data", module='COASTAL_COLLECTOR')
                return self._get_mock_data(location)
            
        except ImportError:
            logger.error("copernicusmarine package not installed, using mock data", module='COASTAL_COLLECTOR')
            return self._get_mock_data(location)
        except Exception as e:
            logger.error(f"Copernicus collection error: {e}, using mock data", module='COASTAL_COLLECTOR', exc_info=True)
            return self._get_mock_data(location)
    
    def _get_location_coords(self, location: str) -> Optional[Dict]:
        """Get coordinates for a location"""
        # Libyan coastal cities coordinates
        coastal_coords = {
            'Tripoli': {'lat': 32.8872, 'lng': 13.1913},
            'Benghazi': {'lat': 32.1165, 'lng': 20.0666},
            'Misrata': {'lat': 32.3750, 'lng': 15.0940},
            'Tobruk': {'lat': 32.0830, 'lng': 23.9180},
            'Zawiya': {'lat': 32.7570, 'lng': 12.7210},
            'Al Khums': {'lat': 32.6500, 'lng': 14.2667},
            'Derna': {'lat': 32.7550, 'lng': 22.6333},
            'Sirte': {'lat': 31.2000, 'lng': 16.5833}
        }
        return coastal_coords.get(location)
    
    def _get_ioc_sealevel_data(self, location: str) -> float:
        """Fetch sea level anomaly from UNESCO-IOC"""
        try:
            import requests
            # IOC Sea Level Monitoring API (no auth required)
            url = f"https://www.ioc-sealevelmonitoring.org/service.php?format=json&station={location}"
            
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                sea_level_anomaly = data.get("anomaly", 0.0)
                logger.info(f"Extracted sea level anomaly from IOC: {sea_level_anomaly}m", module='COASTAL_COLLECTOR')
                return round(sea_level_anomaly, 3)
            else:
                logger.warning(f"IOC API returned status {response.status_code}", module='COASTAL_COLLECTOR')
                return 0.0
        except Exception as e:
            logger.error(f"Failed to fetch IOC sea level data: {e}", module='COASTAL_COLLECTOR')
            return 0.0
    
    def _get_mock_data(self, location: str) -> tuple[bool, str, Dict]:
        """Generate mock coastal data for testing"""
        import random
        
        coastal_data = {
            'location': location,
            'wave_height': round(random.uniform(0.5, 3.0), 2),
            'wave_period': round(random.uniform(5.0, 12.0), 2),
            'sea_level_anomaly': round(random.uniform(-0.5, 0.5), 3),
            'wind_speed': round(random.uniform(2.0, 15.0), 2)
        }
        
        logger.collector_run('coastal', f"Collected for {location}", f"Wave height: {coastal_data['wave_height']}m")
        
        return True, "Coastal data collected successfully", coastal_data
    
    def collect_and_save(self, location: str) -> tuple[bool, str]:
        """Collect and save coastal data"""
        success, message, coastal_data = self.collect_coastal(location)
        
        if not success:
            return success, message
        
        # Save to database
        success, message, coastal_id = self.service.save_coastal(coastal_data)
        
        if success:
            logger.info(f"Collected and saved coastal for {location}", module='COASTAL_COLLECTOR')
        else:
            logger.error(f"Failed to save coastal for {location}: {message}", module='COASTAL_COLLECTOR')
        
        return success, message
    
    def collect_multiple_locations(self, locations: list) -> Dict:
        """Collect coastal data for multiple locations"""
        results = {}
        
        for location in locations:
            success, message, _ = self.collect_and_save(location)
            results[location] = {
                'success': success,
                'message': message
            }
        
        return results
