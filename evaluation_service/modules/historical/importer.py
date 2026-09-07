"""
Historical data importer for EM-DAT disaster data
"""
import csv
import os
from typing import Dict, List
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.historical.service import HistoricalService

logger = get_logger()

class HistoricalImporter:
    """Imports historical disaster data from EM-DAT CSV or Excel"""
    
    def __init__(self):
        self.service = HistoricalService()
    
    def import_from_excel(self, excel_path: str, limit: int = None) -> tuple[int, int]:
        """Import disasters from EM-DAT Excel file
        
        Returns:
            (success_count, error_count)
        """
        try:
            import openpyxl
        except ImportError:
            logger.error("openpyxl not installed. Install with: pip install openpyxl", module='HISTORICAL_IMPORTER')
            return 0, 0
        
        if not os.path.exists(excel_path):
            logger.error(f"Excel file not found: {excel_path}", module='HISTORICAL_IMPORTER')
            return 0, 0
        
        success_count = 0
        error_count = 0
        
        try:
            wb = openpyxl.load_workbook(excel_path)  # Don't use read_only mode for header detection
            sheet = wb.active
            
            # Get headers
            headers = list(sheet.iter_rows(max_row=1, values_only=True))[0]
            header_map = {h: i for i, h in enumerate(headers)}
            
            # Column indices
            idx_disaster_type = header_map.get('Disaster Type')
            idx_country = header_map.get('Country')
            idx_location = header_map.get('Location')
            idx_lat = header_map.get('Latitude')
            idx_lng = header_map.get('Longitude')
            idx_start_year = header_map.get('Start Year')
            idx_start_month = header_map.get('Start Month')
            idx_start_day = header_map.get('Start Day')
            idx_deaths = header_map.get('Total Deaths')
            idx_affected = header_map.get('Total Affected')
            idx_damage = header_map.get('Total Damage (\'000 US$)')
            
            logger.info(f"Column indices: lat={idx_lat}, lng={idx_lng}", module='HISTORICAL_IMPORTER')
            
            # Skip header row
            rows = list(sheet.iter_rows(min_row=2, values_only=True))
            if limit:
                rows = rows[:limit]
            
            for row in rows:
                try:
                    disaster_data = self._parse_excel_row(
                        row, idx_disaster_type, idx_country, idx_location,
                        idx_lat, idx_lng, idx_start_year, idx_start_month, idx_start_day,
                        idx_deaths, idx_affected, idx_damage
                    )
                    
                    # Only import if has coordinates
                    if disaster_data.get('lat') and disaster_data.get('lng'):
                        self.service.repository.save_disaster(disaster_data)
                        success_count += 1
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:  # Log first 5 errors only
                        logger.error(f"Failed to import row: {e}", module='HISTORICAL_IMPORTER')
            
            wb.close()
            logger.info(f"Imported {success_count} disasters from Excel, {error_count} errors", module='HISTORICAL_IMPORTER')
            
        except Exception as e:
            logger.error(f"Failed to import Excel: {e}", module='HISTORICAL_IMPORTER', exc_info=True)
        
        return success_count, error_count
    
    def _parse_excel_row(self, row, idx_type, idx_country, idx_location, idx_lat, idx_lng,
                         idx_year, idx_month, idx_day, idx_deaths, idx_affected, idx_damage) -> Dict:
        """Parse Excel row into disaster data"""
        # Build date from year/month/day
        year = row[idx_year] if idx_year is not None else None
        month = row[idx_month] if idx_month is not None else None
        day = row[idx_day] if idx_day is not None else None
        
        date_str = ''
        if year:
            date_str = f"{year}"
            if month:
                date_str += f"-{month:02d}"
                if day:
                    date_str += f"-{day:02d}"
        
        return {
            'disaster_type': row[idx_type] if idx_type is not None else 'Unknown',
            'country': row[idx_country] if idx_country is not None else 'Unknown',
            'location': row[idx_location] if idx_location is not None else '',
            'date': date_str,
            'deaths': self._parse_int(row[idx_deaths] if idx_deaths is not None else 0),
            'affected': self._parse_int(row[idx_affected] if idx_affected is not None else 0),
            'damage_usd': self._parse_float(row[idx_damage] if idx_damage is not None else 0) * 1000,  # Convert from '000 US$ to US$
            'description': '',
            'lat': self._parse_float(row[idx_lat] if idx_lat is not None else None),
            'lng': self._parse_float(row[idx_lng] if idx_lng is not None else None)
        }
    
    def import_from_csv(self, csv_path: str) -> tuple[int, int]:
        """Import disasters from CSV file
        
        Returns:
            (success_count, error_count)
        """
        if not os.path.exists(csv_path):
            logger.error(f"CSV file not found: {csv_path}", module='HISTORICAL_IMPORTER')
            return 0, 0
        
        success_count = 0
        error_count = 0
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        disaster_data = self._parse_row(row)
                        self.service.repository.save_disaster(disaster_data)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to import row: {e}", module='HISTORICAL_IMPORTER')
                        error_count += 1
            
            logger.info(f"Imported {success_count} disasters, {error_count} errors", module='HISTORICAL_IMPORTER')
            
        except Exception as e:
            logger.error(f"Failed to import CSV: {e}", module='HISTORICAL_IMPORTER', exc_info=True)
        
        return success_count, error_count
    
    def _parse_row(self, row: Dict) -> Dict:
        """Parse CSV row into disaster data"""
        return {
            'disaster_type': row.get('Disaster Type', 'Unknown'),
            'country': row.get('Country', 'Unknown'),
            'location': row.get('Location', ''),
            'date': row.get('Date', ''),
            'deaths': self._parse_int(row.get('Total Deaths', 0)),
            'affected': self._parse_int(row.get('Total Affected', 0)),
            'damage_usd': self._parse_float(row.get('Total Damage (USD)', 0)),
            'description': row.get('Description', '')
        }
    
    def _parse_int(self, value) -> int:
        """Parse integer value"""
        try:
            return int(float(value)) if value else 0
        except (ValueError, TypeError):
            return 0
    
    def _parse_float(self, value) -> float:
        """Parse float value"""
        try:
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def import_sample_data(self) -> tuple[int, int]:
        """Import sample historical data for Libya"""
        sample_data = [
            {
                'disaster_type': 'Flood',
                'country': 'Libya',
                'location': 'Tripoli',
                'date': '2019-01-15',
                'deaths': 5,
                'affected': 1000,
                'damage_usd': 500000,
                'description': 'Flash floods in Tripoli due to heavy rainfall',
                'lat': 32.8872,
                'lng': 13.1913
            },
            {
                'disaster_type': 'Storm',
                'country': 'Libya',
                'location': 'Benghazi',
                'date': '2018-11-20',
                'deaths': 3,
                'affected': 500,
                'damage_usd': 200000,
                'description': 'Severe storm causing damage to infrastructure',
                'lat': 32.1165,
                'lng': 20.0667
            },
            {
                'disaster_type': 'Drought',
                'country': 'Libya',
                'location': 'Southern Region',
                'date': '2017-06-01',
                'deaths': 0,
                'affected': 50000,
                'damage_usd': 1000000,
                'description': 'Severe drought affecting agricultural areas',
                'lat': 27.0167,
                'lng': 14.4333
            },
            {
                'disaster_type': 'Flood',
                'country': 'Libya',
                'location': 'Derna',
                'date': '2023-09-10',
                'deaths': 4300,
                'affected': 20000,
                'damage_usd': 50000000,
                'description': 'Devastating flash floods in Derna after Storm Daniel',
                'lat': 32.7556,
                'lng': 22.6333
            },
            {
                'disaster_type': 'Storm',
                'country': 'Libya',
                'location': 'Misrata',
                'date': '2020-01-05',
                'deaths': 2,
                'affected': 300,
                'damage_usd': 150000,
                'description': 'Heavy storm causing coastal flooding',
                'lat': 32.3753,
                'lng': 15.0927
            }
        ]
        
        success_count = 0
        for data in sample_data:
            try:
                self.service.repository.save_disaster(data)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to import sample data: {e}", module='HISTORICAL_IMPORTER')
        
        logger.info(f"Imported {success_count} sample disasters", module='HISTORICAL_IMPORTER')
        return success_count, 0
